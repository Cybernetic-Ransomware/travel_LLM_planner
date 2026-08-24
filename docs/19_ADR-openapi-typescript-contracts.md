# ADR-19: Generate SvelteKit REST contracts from FastAPI's OpenAPI schema

## Context
`apps/frontend/src/lib/types/{gmaps,optimizer,orchestrator,trips}.ts` hand-duplicated every REST DTO the
backend exposes. After ADR-15/16/17/18 this hand copy was demonstrably stale: `SkippedPlace.reason` was a
5-value closed union while the backend already emitted 9 distinct strings (`TRANSFER_WINDOW_INFEASIBLE`,
`CAPACITY_EXCEEDED`, `PRE_TRANSFER_WINDOW_INFEASIBLE`, `PRE_TRANSFER_CAPACITY_EXCEEDED` were missing), and
`MultiDayTripOut` was explicitly commented as "intentionally minimal" — missing `multi_day_request`/
`multi_day_response` entirely, even though `MultiDayTripDetailOut` (`src/trips/models.py`) already carried
them in full. `OptimizeResponse`/`DayPlan` were also missing `travel_to_end_s` (added by ADR-16/17) —
discovered only once generated types made its absence a hard type error (see Technical Considerations).

`docs/frontend-roadmap.md` had carried a bare, unspecified "Types from OpenAPI" line item since ADR-14. ADR-18
explicitly flagged the risk this ADR resolves: *"OpenAPI schema for the trips endpoints becomes additive
(`oneOf` + `discriminator`); no OpenAPI-codegen tooling was found in this repo... any future generated client
would need regeneration."*

## Decision
FastAPI/Pydantic (`src.main:app`) becomes the canonical source of REST contracts. `app.openapi()` is exported
as a committed `openapi.json` snapshot (repo root); `openapi-typescript` generates a committed
`apps/frontend/src/lib/types/generated/api.ts` from it; the four existing hand-written type files become thin
alias/refinement layers over the generated file. A dedicated CI job fails when the tracked artifacts drift
from a fresh regeneration. No HTTP client is generated — `apiFetch()`/`backendFetch()` (`apps/frontend/src/lib/
api/`, `src/lib/server/backend.ts`) are unchanged.

## Rationale
### Evaluation of Alternatives
- **`@hey-api/openapi-ts`, Orval, Kubb** — rejected: all default to generating a runtime HTTP client/SDK on
  top of types, which this branch explicitly does not want (`apiFetch`/`backendFetch` already own networking,
  auth, timeouts, error handling). `openapi-typescript` is the only evaluated tool that is types-only by
  default with zero runtime footprint.
- **`openapi-zod-client`/`openapi-zod-ts`** — rejected: depends on Zodios, whose maintenance has stopped;
  unsuitable for new adoption regardless of feature fit.
- **Live-server generation (`GET /openapi.json` against a running instance)** — rejected. `app.openapi()` was
  verified to run with zero side effects and zero required env vars (see Technical Considerations); spinning up
  Mongo/uvicorn just to fetch what a plain Python import already gives for free would be strictly worse.
- **Ephemeral (uncommitted) `openapi.json`** — rejected. A committed snapshot gives reviewers a clean,
  structured diff of exactly what the backend contract changed, decoupled from the generated TypeScript's own
  (differently-formatted) diff — and enables a two-level drift check (backend → snapshot, snapshot → TS)
  instead of one opaque one.
- **Relying on `openapi-typescript`'s own `--check` flag for the generated-TS drift check** — rejected. The
  generation pipeline always runs Prettier as a mandatory post-process step (see Formatting below); `--check`
  compares the generator's raw, unformatted output against the tracked (Prettier-formatted) file, which would
  report drift on every run regardless of whether the contract actually changed. The `check-frontend-types`
  recipe instead regenerates to a temp file, formats it identically to the real pipeline, and hash-compares.

### Technical Considerations
- **`app.openapi()` has no import-time side effects.** All external clients (Mongo, Google Places/Routes, the
  LangGraph orchestrator) are constructed inside FastAPI's `lifespan()` (`src/config/lifespan.py`), never
  triggered by a plain import. `Settings` (`src/config/config.py`) defaults every field, so `Settings()`
  succeeds with zero env vars. Verified directly: two independent cold-start processes produced byte-identical
  JSON — the schema is deterministic and safe to diff/commit.
- **The trips discriminated union needed a real backend fix, not just a TypeScript-side workaround.**
  `SaveTripRequest` uses a callable Pydantic `Discriminator` (`src/trips/models.py`); `TripSummaryOut`/
  `TripDetailOut` use `Field(discriminator="plan_type")`. Both response variants declare
  `plan_type: Literal[...] = "..."` — a default, never `Field(...)`-required — so it was absent from the
  schema's `required` array. `openapi-typescript` therefore generated `plan_type?: 'SINGLE_DAY'` (optional),
  which silently breaks TypeScript discriminated-union narrowing: in
  `if (trip.plan_type === 'MULTI_DAY') {...} else {...}`, the `else` branch cannot exclude `MultiDayTripOut`,
  because a structurally valid `Multi` value with `plan_type` omitted would still satisfy `!== 'MULTI_DAY'`.
  Fixed with `ConfigDict(json_schema_serialization_defaults_required=True)` on `TripSummaryOutBase`/
  `TripDetailOutBase` (`src/trips/models.py`) — makes `plan_type` (and `updated_at`) required in the
  *serialization*-mode schema only, leaving the *validation*-mode (request) schema, and therefore legacy
  payloads without `plan_type`, unaffected. Verified directly against the generated schema:
  `SingleDaySaveTripRequest`/`MultiDaySaveTripRequest.required` do not include `plan_type`;
  `Single/MultiDayTripSummaryOut`/`Single/MultiDayTripDetailOut.required` do.
- **`openapi-typescript` is invoked with `--default-non-nullable false`, overriding its own default (`true`).**
  The default behavior treats *any* field with a `default` as non-optional in the emitted type, regardless of
  the schema's `required` array — verified empirically: even `SingleDaySaveTripRequest.plan_type` (deliberately
  *not* touched by the fix above) came out required under the default, which broke real call sites
  (`SaveTripForm.svelte`, `routes/optimizer/+page.svelte` construct request objects without `plan_type`).
  Passing `--default-non-nullable false` makes the generated TypeScript track the schema's `required` array
  exactly — nothing more, nothing less — so the request/response asymmetry above comes from Pydantic's schema,
  not from a generator-specific heuristic that a future flag change or generator swap could silently undo.
  Side effect (accepted, and itself contract-accurate): fields like `RouteStep.wait_min`, `OptimizeResponse.
  travel_to_end_s`, `DayConfig.day_start_hour` become optional in TypeScript, matching that the backend
  genuinely accepts their omission.
- **`openapi-typescript` requires `typescript@^5.x`; `apps/frontend` pins `^6.0.2`.** `openapi-typescript@
  7.13.0` declares `typescript@^5.x`, while `apps/frontend` uses TypeScript 6 — outside the tool's declared peer
  contract. Rather than loosen `apps/frontend`'s peer-dependency strictness for the whole app (`--legacy-
  peer-deps`/`.npmrc`) because of one dev-only codegen tool, `openapi-typescript` is isolated in its own
  package, **`tools/openapi-codegen/`**, pinned to `typescript@5.9.3` (latest 5.x), so both dependency trees stay
  within their declared peer contracts. This is purely a workaround for the current upstream peer contract, not
  an architectural preference — when `openapi-typescript` bumps its
  peer range to include TypeScript 6, folding it back into `apps/frontend`'s own devDependencies is a
  reasonable follow-up, not required by this ADR.
- **Cross-package Prettier formatting is cwd-sensitive.** `prettier --config apps/frontend/.prettierrc --write
  <file-outside-apps/frontend>` fails to resolve the config's `prettier-plugin-svelte`/`prettier-plugin-
  tailwindcss` plugins when invoked from outside `apps/frontend` (`npx --prefix` only selects which
  `node_modules` supplies the `prettier` binary, not the process's cwd, and plugin resolution is cwd-relative).
  The `check-frontend-types` recipe changes into `apps/frontend` before formatting a temp-directory copy, then
  returns.
- **`-Input`/`-Output` schema splitting is real but type-specific, not universal.** Pydantic/FastAPI emits
  separate validation/serialization schemas for models reachable both as a request body and nested in a
  response (`MultiDayRequest`, `MultiDayResponse`, `DayPlan` — because `MultiDayTripDetailOut` nests
  `multi_day_request`/`multi_day_response`). `OptimizeRequest`/`OptimizeResponse`/`RouteStep`/`SkippedPlace`
  do not split, despite an analogous reachability pattern. The alias layer never guesses which suffix to use:
  types that are a literal top-level request/response body of an endpoint AND reachable in another context are
  derived from `paths[...]['<method>']['requestBody'|'responses'][<status>]['content']['application/json']`,
  which resolves to the correct variant automatically; everything else uses `components['schemas'][...]`
  directly.

### Integration with Existing Environment
- The four hand-written type files (`gmaps.ts`, `optimizer.ts`, `orchestrator.ts`, `trips.ts`) keep their
  location and their existing export names (`TripOut`, `SingleDayTripOut`, `MultiDayTripOut`,
  `TransportModeNoTransit`, etc.) — only their bodies change, from copied field lists to aliases into
  `generated/api.ts`. `apps/frontend/src/lib/types/index.ts` (the barrel) is untouched, so none of the 40+
  consumer files needed an import path change.
- `TransportModeNoTransit` — the one field where the backend's `model_validator` (rejecting `TRANSIT` on
  `MultiDayRequest`) has no OpenAPI representation — stays a handwritten refinement, but derived:
  `Exclude<TransportMode, 'TRANSIT'>`, not a re-typed copy of the enum.
- `SSEEvent`/`ToolProposal` (`orchestrator.ts`) stay entirely handwritten: `POST /api/v1/core/orchestrator/chat`
  returns a bare `StreamingResponse` with no `response_model`, so OpenAPI describes its `200` response as an
  untyped `application/json: {}` — actively misleading about both content-type and shape. `OrchestratorStatus`
  became a real generated contract via a small, behavior-neutral addition: `GET /status` previously returned
  `-> dict`; it now returns `-> OrchestratorStatusOut` (`src/orchestrator/models.py`), a Pydantic model with the
  same three fields (`ready`, `provider`, `model`) it already produced.
- `FastAPI()` gained `title="Travel Planner API"` (`src/main.py`) — previously defaulted to `"FastAPI"` in
  `info.title`, cosmetic but load-bearing for the generated file being self-explanatory.
- `SkippedPlace.reason` is generated as plain `string` (the backend field is `str`, not `Literal`) — the
  previously-stale 5-value closed union is gone. Any UI-facing "known reasons" lookup remains a separate,
  frontend-only helper with a fallback for unknown values, not a re-tightened backend-mirroring type.
- Two independent npm packages participate in generation — `tools/openapi-codegen` (generator only) and
  `apps/frontend` (Prettier formatting only, using its own existing `^3.8.1` devDependency) — with no
  workspace/monorepo linking between them. `apps/astro-frontend/` was inventoried (a smaller, separately
  hand-maintained DTO copy, ~7 files) but is out of scope for this branch.

### Future Potential
This branch's stated acceptance test: `feat/multi-day-planner-ui` can import complete `MultiDayRequest`,
`MultiDayResponse`, `AccommodationStay`, `TransferBlock`, `DayPlan`, `TransferSegment`,
`MultiDaySaveTripRequest`, `MultiDayTripDetailOut` (now with `multi_day_request`/`multi_day_response`) without
re-deriving their shapes by hand. `docs/frontend-roadmap.md`'s "Types from OpenAPI" line item is satisfied and
removed.

## Consequences
### Positive Outcomes
- Every REST DTO the frontend consumes now round-trips from a single, deterministic backend source; the two
  concrete drift bugs this ADR opened with (`SkippedPlace.reason`, `MultiDayTripOut`) are fixed as a direct
  consequence of generation, not by manually patching the hand-written files.
- `contract-drift.yml` makes future drift a CI failure instead of a silent, discovered-months-later gap.
- Regenerating types requires no manual TypeScript authorship — `just frontend-types` is the single canonical
  command; `just check-frontend-types` is the non-mutating verification used identically locally and in CI.

### Challenges & Mitigation
- Generated types are strictly less precise than the runtime validators in several named ways: naive
  wall-clock time is a plain `string`; cross-field `model_validator`s (day-bound ordering, `TRANSIT` exclusion,
  transfer/anchor conflicts) have no static representation; `PlacePatch.skipped`'s omit-vs-explicit-`null`
  distinction collapses to `skipped?: boolean | null` in TypeScript; `ErrorResponse` (the real runtime error
  body shape from `src/core/middleware.py`) is invisible to OpenAPI entirely, since no route wires it via
  `responses=`. None of these are fixed by this ADR — they are named limitations, not solved problems.
  Generation gives a wire-shape source of truth, not a reproduction of backend validation.
- `tools/openapi-codegen`'s isolation from `apps/frontend`'s TypeScript version is a workaround for a current
  upstream peer-dependency gap, not a permanent architectural split — revisit when `openapi-typescript` supports
  TypeScript 6 natively.
- `SaveTripRequest`'s callable `Discriminator` has no OpenAPI `discriminator` keyword representation (`oneOf`
  only) — TypeScript narrowing on the request side still works structurally (distinct `plan_type` literals per
  branch), but a codegen tool that specifically looks for `discriminator.mapping` would not build the same
  union unaided. Not an issue in practice here, since the alias layer builds the union explicitly.

## Status
`Accepted` — scoped to `apps/frontend/src/lib/types/`, `tools/openapi-codegen/`, `scripts/export_openapi.py`,
`openapi.json`, `.github/workflows/contract-drift.yml`, `justfile`, and the three named behavior-neutral
backend changes (`src/main.py` title, `src/orchestrator/{router,models}.py` `OrchestratorStatusOut`,
`src/trips/models.py` `json_schema_serialization_defaults_required`). `apps/astro-frontend/` is out of scope.

## Non-goals
- **A generated HTTP client.** `apiFetch()`/`backendFetch()` are unchanged; only the types they're parameterized
  with come from `generated/api.ts`.
- **Multi-day planner UI, accommodations/transfer forms, itinerary renderer, multi-day save workflow.** This
  ADR only prepares the contracts `feat/multi-day-planner-ui` will consume.
- **Fixing the `ErrorResponse`/422 OpenAPI mismatch.** Would require wiring `responses={422: {"model":
  ErrorResponse}, 500: {...}}` across every route — a larger, separate change.
- **Migrating `SkippedPlace.reason` or any other plain-`str` backend field to `Literal`/enum purely for
  TypeScript's benefit.**
- **A shared types package between `apps/frontend` and `apps/astro-frontend`.** Astro's duplication is
  inventoried, not addressed.
- **Consolidating `frontend.yml`/`sveltekit-ci.yml`'s pre-existing overlap**, or any general CI cleanup beyond
  the new `contract-drift.yml` job.
