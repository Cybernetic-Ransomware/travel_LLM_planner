# ADR-20: Confirmation-gated AI editing of persisted multi-day trips

## Context
After ADR-18 a user can save a `MULTI_DAY` trip, but the only way to change one is to re-run the
`/optimizer` form and `PUT /core/trips/{id}` with a full body. The chat orchestrator's trip tools
(`list_saved_trips`, `get_trip_details`) are read-only; its write tools (`update_visit_hours`,
`skip_place`, `add_place`) mutate the **global `Place` library**, not a trip.

Research also confirmed a real scoping hole in the existing write path. The `allowed_place_ids` guard
lives only in a per-invocation `config["configurable"]` entry set by the router on turn 1. It is never
checkpointed and the resume path never rebuilds it. Under production `interrupt_before=["tools"]` a
write tool executes **only on resume**, so `_extract_allowed(config)` is `[]` and the old
`if allowed and place_id not in allowed` check is skipped — an empty scope meant *unrestricted*.

This ADR adds the first safe, durable, confirmation-gated workflow for editing a saved `MULTI_DAY`
trip through chat, and closes the scoping hole for every write tool.

## Decision
1. **Server-derived trip context.** `ChatRequest` gains `trip_id`. When set, the router loads the trip
   via `TripsManager`, ignores client `place_ids`, derives the allowed place-id set from the persisted
   `MultiDayRequest.places`, renders a bounded trip-context system prompt, and binds the thread. The
   client is never authoritative for trip contents, plan type, allowed places, or revision.
2. **One batch tool.** `edit_multi_day_trip(operations: list[TripEditOperation])` — no LLM-visible
   `trip_id` — is the only chat write path for a trip: one proposal → one
   `interrupt_before=["tools_write"]` → one confirmation → one load → one `optimize_trip` → one
   compare-and-set persist. An interrupted write turn must carry **exactly one** write tool call; two
   or more is fail-closed with no armed scope and no proposal.
3. **Scope in a dedicated side collection.** `TripSessionStateStore` over
   `orchestrator_thread_trip_state` holds one document per `thread_id` with the binding (kind
   `"trip"` or `"place_selection"`, trip id, name, revision, allowed place ids) and a single `pending`
   snapshot. The router `arm_pending`s the snapshot at the interrupt; the write tool
   `consume_pending`s it once on resume (atomic clear of the `pending` field — the document stays).
   Scope is never re-derived from the confirmation request body, and is cleared on every normal turn
   and on `resume_confirmed: false`. All four write tools resolve scope this way; the legacy
   `allowed_place_ids`-in-`configurable` fail-open is **removed** — an empty/missing selection now
   denies, and `update_visit_hours` / `skip_place` / `add_place` are refused in an active trip
   context (redirected to `edit_multi_day_trip`).
4. **Bidirectional optimistic concurrency.** A persistent integer `revision` on the trip document
   plus an `expected_revision` request-body field. One unified `TripsManager.update()` serves both
   the chat editor and `PUT /core/trips/{id}`:
   `find_one_and_update({_id, revision == expected_revision}, {$set: request+response, $inc: {revision: 1}})`.
   Missing token on an otherwise valid update → 428; mismatch → 409; legacy documents without the
   field count as revision 0. Neither direction (stale UI PUT after a chat edit, stale chat edit
   after a UI PUT) can lose an update.
5. **Re-optimize-before-persist coherence.** The mutated `MultiDayRequest` and a fresh
   `MultiDayResponse` from the same `optimize_trip` run are written in one atomic `$set`. Any failure
   in validate / mutate / optimize / persist ⇒ zero writes.
6. **Split tool stage.** `tools_read = ToolNode(read_tools)` (no interrupt) and
   `tools_write = ToolNode(all_tools)` (interrupt when checkpointed). `_after_chatbot` routes to
   `tools_write` when ≥1 write call is present, so a mixed read+write batch resolves after one
   confirmation without invalid-tool errors; read-only turns never pay a confirmation round-trip.
7. **Structured refresh signal.** A `{"trip_updated": {trip_id, revision, plan_type, name}}` SSE
   event is emitted from an `AgentState.last_trip_update` echo channel on the resume turn. A shared
   `inspect_pending_write_interrupt` helper runs after both `_stream_sse` and `_stream_sse_resume`,
   guaranteeing a `tool_proposal` or a fail-closed `error` for every write interrupt, including a
   re-interrupt after an earlier tool ran. `/trips/[id]` registers `depends('app:trip:<id>')`; the
   chat client calls a scoped `invalidate(...)`, epoch- and `trip_id`-guarded.

## Rationale
### Evaluation of Alternatives
- **Scope in an `AgentState` channel / checkpoint** — rejected: it is a security control, would be
  checkpointed and inherited across turns, and a stale scope from an earlier proposal could be read
  back. Violates ADR-10.
- **Scope re-injected into `configurable` from the confirmation request** — rejected: it trusts the
  confirm request body; the client could retarget the trip or widen the id set.
- **Scope in `CheckpointMetadata` / in the pending `AIMessage.tool_calls` args** — rejected: the
  metadata blob is owned by LangGraph, and rewriting the pending message is fragile surgery with no
  gain over a dedicated side collection.
- **Keeping the legacy fail-open guard** (`if allowed and place_id not in allowed`) — rejected: it
  leaves writes unrestricted whenever the scope is empty, which is exactly the state on the resume
  turn under production HITL.
- **Per-operation tools** — rejected: N interrupts, N confirmations, N `optimize_trip` runs, N
  revision bumps, and an inconsistent intermediate persisted state that the next operation chases.
- **`ToolProposal[]` / several write calls per turn** — rejected: the frontend `pendingProposal` is
  singular; multi-step intent is represented by `operations[]` inside one `edit_multi_day_trip`.
- **CAS on `updated_at` or an `If-Match` header** — rejected: `updated_at` is nullable `str` with
  second resolution (an unsafe token); there is no header-precondition precedent in this repo and
  `openapi-typescript` models request headers worse than body fields.
- **One-directional CAS (chat only)** — rejected: a stale UI `PUT` after a chat edit would still
  clobber. `expected_revision` is required on both write paths.
- **Per-operation re-resolution of `stay_index`** — rejected: a selector would shift after an earlier
  op in the same batch added/removed a stay. All `stay_index` values are resolved once against the
  PRE-BATCH order (sorted by `check_in_date`); remove+update or update+update of the same stay is a
  hard conflict, not last-wins.
- **Multi-document Mongo transaction** — rejected: unnecessary for a single-collection,
  single-document `$set` + `$inc`; it would also force the integration conftest onto `--replSet`.
- **A permanent `id` on `AccommodationStay`** — rejected: it breaks the object-identity contract of
  ADR-15 and would require migrating every persisted embedded `accommodations[]`. Accommodation ops
  use the deterministic pre-batch `[stay N]` selector instead.

### Technical Considerations
`optimize_trip` and the ADR-15/16/17 resolvers are reused unchanged. The domain edit service lives in
a new `src/trips/editing/` package (trips already depends on optimizer; optimizer must not depend on
trips; `src/orchestrator/` is `ty`-excluded). `apply_operations` mutates a `deepcopy` of
`request.model_dump()` and constructs the model exactly once at the end, so every
`@model_validator` re-runs and a half-applied batch never yields a partial model. Transfers orphaned
by an accommodation edit are reconciled (dropped) once per batch; a transfer *added* in the batch on
a non-transition day is left for `validate_transfers_on_transition_days` to reject.

### Integration with Existing Environment
- **Amends ADR-10.** Every session-scoped write tool that passes through the HITL interrupt carries
  its scope in `TripSessionStateStore` (snapshot at interrupt, single-use consume on resume), not in
  per-invocation `configurable`. The legacy fail-open is removed; the router always binds a scope on
  a normal turn (`bind_trip` or `bind_place_selection`).
- **Amends ADR-18.** `revision` joins `schema_version` as a persisted field and is now actively used;
  `expected_revision` is a request-body field; one `update()` with a CAS `$inc` serves `PUT` and the
  chat editor. The response contract gains `revision`, the request `expected_revision` (ADR-19
  regeneration); a new 428 `MissingExpectedRevisionError` and 409 `TripConcurrencyConflictError`.
- **ADR-09 untouched.** A new non-checkpoint collection with a unique `thread_id` index and a TTL
  `expires_at` index is added to `MongoDBManager._create_indexes`.
- **ADR-04 / conftest untouched.** No replica set required — the write is a single-document
  compare-and-set.
- **Frontend.** `ChatState` gains a monotonic `contextEpoch` and a per-stream `AbortController`; the
  chat session resets on every trip-context switch (no magic rebind); a real
  `cancelPendingChatTool` POST replaces the previously inert abandoned generator.

### Future Potential
`revision` is the concurrency token and the foundation for a future revision-history / revert branch,
but this ADR adds no history, audit log, or undo. A `SingleDayEditOperation` union and a
`plan_type`-branch in the tool can extend the same service to SINGLE_DAY trips without touching the
multi-day path; a `POST /core/trips/{id}/edit` REST endpoint can reuse `MultiDayTripEditor` directly.

## Consequences
### Positive Outcomes
- One confirmation, one optimizer run, one atomic persist for a multi-step trip change.
- Write scope survives the HITL boundary and cannot be retargeted or widened by the client.
- Lost updates are impossible in either UI↔chat direction.
- Read-only chat is unchanged and no longer pays a confirmation round-trip.

### Challenges & Mitigation
- **Accommodation ops are the most complex surface.** Mitigated by fail-closed validation
  (`ValidationError` ⇒ zero persistence), a wide `apply`/`reconcile` unit suite, and the option to
  cut accommodation ops to a follow-up without touching the rest (the union is additive).
- **`Command(update=...)` / `InjectedToolCallId` version sensitivity.** Verified against the pinned
  `langgraph` 1.1.3 / `langchain-core` 1.4.0; documented string + `aget_state` fallback if a bump
  regresses them.
- **Legacy place-edit workflow becomes fail-closed.** If the router failed to bind a
  `place_selection` scope, `update_visit_hours` / `skip_place` would deny rather than act. Mitigated
  by always binding on a normal turn plus a dedicated interrupt→resume test.
- **No trip ownership** is a pre-existing gap this branch does not introduce or fix; noted, out of
  scope.

## Status
`Accepted` — applies to the orchestrator chat write path and the trips persistence layer.
