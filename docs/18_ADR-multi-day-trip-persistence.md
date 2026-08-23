# ADR-18: Multi-day trip persistence — discriminated `Trip` model

## Context
`src/trips/` persisted only single-day trips: `SaveTripRequest` wrapped a single
`OptimizeRequest`/`OptimizeResponse` pair, and `TripsManager` strictly `model_validate()`d
those two types on every read. Meanwhile `src/optimizer/solver/models.py` already had a
complete multi-day data model (`MultiDayRequest`, `MultiDayResponse`, `DayPlan`,
`DayRouteSegment`, `TransferSegment`, built under ADR-15/16/17) that nothing in `src/trips/`
or `src/orchestrator/` referenced at all. Multi-day trips the optimizer could already produce
were lost the moment the browser refreshed — there was no way to save or reload them.

Existing Mongo documents in the `trips` collection predate this change and have no
`plan_type`/`schema_version` field at all.

## Decision
Generalize `Trip` into one persisted-plan model discriminated by
`plan_type: Literal["SINGLE_DAY", "MULTI_DAY"]`, rather than adding a parallel `src/journeys/`
module or a new endpoint family. The 5 existing CRUD endpoints under `/api/v1/core/trips` are
unchanged. A stored document with no `plan_type` key is legacy and is treated as `SINGLE_DAY`
at read time — permanently, with no migration script.

## Rationale
### Evaluation of Alternatives
- **Separate `src/journeys/` module + new endpoint family** — rejected. Would force users to
  understand two persisted-trip concepts (`Trip` vs `Journey`) and duplicate the list/detail/
  CRUD machinery that already exists and works.
- **Full generic Mongo migration framework** — rejected as disproportionate. "Absence of
  `plan_type` means legacy `SINGLE_DAY`" is a sufficient, permanent inference rule; no
  documents need to be rewritten.
- **Denormalizing accommodations/transfers/dates as extra top-level fields** — rejected as a
  dual source of truth. The persisted `MultiDayRequest` alone is sufficient to reconstruct
  everything; only a derived, read-time-computed date range is needed for cheap listing (see
  Technical Considerations).

### Technical Considerations
- **Request-side discriminator**: `SaveTripRequest` uses a **callable Pydantic `Discriminator`**
  (not `Field(discriminator="plan_type")`), because the existing frontend payload omits the
  tag entirely. The callable infers `SINGLE_DAY` by default and `MULTI_DAY` from the presence
  of a `multi_day_request`/`multi_day_response` key, so both old and new clients validate
  against one union with no request version bump.
- **Hybrid-payload rejection**: both `SingleDaySaveTripRequest` and `MultiDaySaveTripRequest`
  set `model_config = ConfigDict(extra="forbid")`. Once the discriminator selects a branch,
  any leftover key belonging to the *other* variant becomes a validation error instead of
  being silently dropped — a payload cannot be ambiguously half-single/half-multi.
- **Response-side discriminator**: `TripSummaryOut`/`TripDetailOut` use plain
  `Field(discriminator="plan_type")`, since these are always constructed server-side with the
  tag explicitly set — the "tag might be absent" problem does not exist on output.
- **Cheap listing preserved**: `TripsManager.list_all()` uses an explicit Mongo projection
  (`name`, `date`, `plan_type`, `created_at`, `multi_day_request.days.date`) so a multi-day
  document's full `MultiDayRequest`/`MultiDayResponse` — every `DayPlan`, `RouteStep`,
  `route_segments`, transfer, skipped place — never leaves Mongo just to render a name and a
  date range. `MultiDayTripSummaryOut` deliberately has no `transport_mode` field, since that
  is not in the projection; it exists only on `MultiDayTripDetailOut`, which does the full
  `MultiDayRequest.model_validate()`.
- **Update conflict**: `TripsManager.update()` raises `TripPlanTypeConflictError`
  (`HTTPException`, 409, in `src/core/exceptions.py`) when a `PUT`'s inferred `plan_type`
  differs from the stored document's, following the existing precedent of
  `InvalidHourRangeError` (raised from `src/gmaps/storage.py`) — a custom exception subclass
  raised from the manager/storage layer, caught automatically by ADR-07's global handler. The
  existing-document lookup happens *before* the plan-type comparison, so a syntactically valid
  but nonexistent `ObjectId` still resolves to `None` (404), not a 409 or a crash.
- **Orchestrator dispatch**: `src/orchestrator/tools.py` branches with
  `getattr(trip, "plan_type", "SINGLE_DAY")`, not `isinstance`, so both real Pydantic responses
  and the existing `MagicMock`-based test fixtures behave correctly on the single-day path
  without fixture changes. The multi-day text renderer looks up `DayRouteSegment.kind`
  (`PRE_TRANSFER`/`POST_TRANSFER`) in a dict rather than indexing `route_segments[0]`/`[1]`
  positionally, because `MultiDayResponse` is accepted directly from the client at the
  persistence endpoint — Pydantic does not enforce "exactly two segments, PRE first," only the
  solver's current output shape happens to look that way.

### Integration with Existing Environment
- `SingleDayTripSummaryOut`/`SingleDayTripDetailOut` keep every field name/type from the old
  `TripSummaryOut`/`TripDetailOut` unchanged — only `plan_type` is additive, so existing API
  consumers (including the hand-written SvelteKit frontend) are unaffected beyond one new key.
- The frontend gained a minimal read-only compatibility tail: `apps/frontend/src/lib/types/trips.ts`
  mirrors the discriminated union, the `/trips` list branches card rendering on `plan_type`,
  and `/trips/[id]` renders a minimal read-only summary for `MULTI_DAY` trips (name, date
  range, day count, transport mode) without attempting to read any single-day-only field. The
  "Open in optimizer" action is hidden for `MULTI_DAY` trips, since `/optimizer` only
  understands `OptimizeRequest`. No multi-day planning/editing UI was built.

### Future Potential
`schema_version: int` is written on every new/updated document but not yet branched on —
reserved for future schema evolution without being a migration framework today. A future slice
can build a full multi-day itinerary UI and multi-day `/optimizer` support on top of this
persistence layer without further backend schema changes.

## Consequences
### Positive Outcomes
- Multi-day trips produced by the optimizer can now be saved and reloaded losslessly
  (accommodations, transfers, day preferences, PRE/POST route segments, transfer segments,
  unassigned/skipped places all round-trip through Mongo).
- Legacy single-day documents and API consumers keep working with zero migration and zero
  breaking response-shape changes.

### Challenges & Mitigation
- OpenAPI schema for the trips endpoints becomes additive (`oneOf` + `discriminator`); no
  OpenAPI-codegen tooling was found in this repo, so this is assessed as low-risk, but any
  future generated client would need regeneration.
- `PUT` gains a new possible 409 status when a caller attempts to change a trip's `plan_type`;
  this is a deliberate, documented restriction, not an oversight.

## Status
`Accepted` — scoped to `src/trips/`, `src/core/exceptions.py`, `src/orchestrator/tools.py`, and
the minimal frontend compatibility tail listed above.
