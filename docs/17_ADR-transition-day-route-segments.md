# ADR-17: Transition-day route segments — sightseeing on both sides of a transfer

## Context
ADR-16 gave a transition day a real, time-consuming `TransferBlock` and modeled the
segment after it: checkout → transfer → check-in → post-transfer sightseeing. It
deliberately left the origin-city side of the day unmodeled — a place closer to the
origin accommodation than the destination was rejected outright as
`TRANSFER_DAY_GEOGRAPHY_MISMATCH`, and ADR-16 named "pre-transfer sightseeing" an
explicit, deferred non-goal.

That gap is real: a traveller does not vanish from Tokyo the instant a transfer is
scheduled. A morning at Tokyo Tower before an 11:00 train to Kyoto is a legitimate,
common itinerary shape, and the previous model actively penalized it — a place the
solver could easily have scheduled was instead surfaced as a hard rejection. This ADR
removes that restriction: a transition day now runs two independent single-day solver
passes, one anchored at the origin accommodation before the transfer (PRE) and one
anchored at the destination after it (POST), and exposes both in the response.

## Decision
1. **`DayRouteSegment` and `DayPlan.route_segments` are new, additive response types.**
   `DayRouteSegment` (`kind: "PRE_TRANSFER" | "POST_TRANSFER"`, `steps`,
   `total_travel_time_s`, `total_visit_time_min`, `total_wait_min`, `travel_to_end_s`,
   `skipped`) is a self-contained single-day route, identical in shape to what a
   consumer already gets from `OptimizeResponse`. `DayPlan.route_segments: list[
   DayRouteSegment] = []` is populated **only** for a day with a resolved
   `TransferBlock`; ordinary days and transition days without a transfer leave it
   empty, exactly as before this ADR.
2. **The contract is unconditional: exactly two segments, always, in a fixed order.**
   Whenever `DayPlan.transfer is not None`, `route_segments` contains precisely
   `[PRE_TRANSFER, POST_TRANSFER]` — never zero, never one. This holds for a zero
   admission budget on either side, an empty bucket on either side, and a
   transfer-only day where both are empty. A segment with nothing to show is
   represented structurally (`steps=[]`, all totals `0`), not by omitting it — an
   earlier draft of this decision made segment presence conditional on budget being
   positive, but that reintroduces exactly the guessing game route_segments exists to
   remove: a client would have to branch on `kind` instead of a fixed position, and
   "why is there only one segment today" becomes a question with no single answer.
   The solver itself is still never invoked with an empty `place_ids` list — the
   segment's emptiness is structural, the underlying `optimize_route` call is simply
   skipped.
3. **`route_segments` is the authoritative full-day view for a transition day;
   `DayPlan`'s top-level `steps`/`total_travel_time_s`/`total_visit_time_min`/
   `total_wait_min`/`travel_to_end_s` are a compatibility projection of exactly the
   `POST_TRANSFER` segment**, unchanged in meaning from ADR-16. Both representations
   are built from the same `DayRouteSegment` object — `DayPlan.steps =
   route_segments[1].steps`, and likewise for every other projected field — never
   from two independent computations. A client that only knows the pre-ADR-17 shape
   keeps getting exactly what it got before; a client that wants the origin-city side
   reads `route_segments[0]`.
4. **PRE anchors are the origin accommodation, door-to-door, unchanged from ADR-16's
   transfer model.** `START = END = origin accommodation`. No station/airport
   endpoint, no additional leg — the PRE segment starts and ends at the same
   coordinates the `TransferBlock`'s origin already refers to.
5. **PRE window: `configured_day_start → pre_end_s`, where `pre_end_s =
   min(transfer.departure_time, configured_day_end, check_out_by or
   transfer.departure_time)`.** `DayConfig.day_end` bounds PRE sightseeing
   independently of the transfer's own departure time — a transfer scheduled after
   the configured day end (e.g. a late-evening train) remains a legal, unvalidated
   fixed block in this slice, but it does not pull sightseeing past the hours the
   caller actually configured. `check_out_by`, when set, is a further, conservative
   upper bound on PRE — not a claim that sightseeing after checkout is physically
   impossible. This slice does not model luggage storage or post-checkout logistics;
   a traveller could legitimately check out, sightsee, and return for their bags
   before the transfer, but nothing here represents that, so the conservative
   boundary is used instead of pretending the model is more complete than it is.
6. **POST window is unchanged from ADR-16**: `effective_post_start = max(
   transfer.arrival_time, destination.check_in_from or configured_day_start,
   configured_day_start)`, `post_end = configured_day_end`, `START = END =
   destination accommodation`. Minute precision, `NaiveTime`, the no-viable-window
   branch, and the ADR-15 safety policy for a transition day without a `TransferBlock`
   are all unchanged.
7. **`_resolve_segment_end_bound_fields` safely encodes an arbitrary resolved end
   bound as an `OptimizeRequest`-legal `(day_end_hour, day_end_time)` pair.**
   `OptimizeRequest.validate_day_end_time_semantics` rejects `day_end_hour == 24`
   combined with any explicit `day_end_time` — `day_end_hour == 24` is the only way
   to express midnight, and it cannot disagree with a separately-supplied clock time.
   Building the PRE request by naively forwarding `cfg.day_end_hour` alongside a
   freshly computed `day_end_time = seconds_to_time(pre_end_s)` breaks exactly this
   rule whenever the caller's `DayConfig` used `day_end_hour == 24` — a legal request
   ("09:00 until midnight, transfer at 11:00") would fail with an internal
   `ValidationError`. The helper picks `(24, None)` when the resolved bound is
   midnight and `(23, <explicit time>)` otherwise — `23` is an inert placeholder,
   since `resolve_day_bound_s` always prefers the explicit time when one is given.
   The POST request needs no such helper: it forwards `cfg.day_end_hour`/
   `cfg.day_end_time` unchanged, exactly as before this ADR, because it never
   invents a new end-of-day value independent of what the caller already supplied
   and validated on `DayConfig`.
8. **`TransitionSide` (`ORIGIN` / `DESTINATION` / `NO_COORDINATES`) replaces the
   binary eligibility check from ADR-16.** Same nearest-of-two-accommodations
   haversine heuristic, same `<` comparison — `dist_to_destination < dist_to_origin →
   DESTINATION`, otherwise `ORIGIN` (a dead-even tie resolves to `ORIGIN`, preserving
   the exact pre-existing comparison rather than introducing a new branch).
   `TRANSFER_DAY_GEOGRAPHY_MISMATCH` is retired: an origin-side place is now a valid
   PRE candidate, not a rejection. No `AMBIGUOUS` tier or distance threshold is
   introduced — ADR-16 already named this heuristic a deliberate simplification
   sufficient for clearly-separated cities, and this ADR does not change that scope.
9. **Pinned places choose a segment by geography, not by user selection** — pinning
   still only selects the day. `ORIGIN` → PRE bucket, `DESTINATION` → POST bucket,
   `NO_COORDINATES` → explicit `DayPlan.skipped` entry (reason `NO_COORDINATES`,
   unchanged), consuming no segment budget. A pinned place is never moved to the
   other segment automatically, and — as before this ADR — is never rejected purely
   by the segment's visit-duration admission budget; only geography and missing
   coordinates can keep it out of a bucket. If its assigned segment ends up with a
   zero admission budget, it surfaces as `PRE_TRANSFER_WINDOW_INFEASIBLE` or
   `TRANSFER_WINDOW_INFEASIBLE` (POST, unchanged name) rather than silently vanishing
   or being force-packed into the other side.
10. **Flexible/auto places filter admissible `(day, side)` candidates first, then
    rank only among those** — the same fix ADR-16 already made for the single-budget
    case, now applied per side. Each transition day offers two independent capacity
    pools (`pre_visit_budget_min`, `post_visit_budget_min`), each with its own
    running fill; an ordinary day keeps today's single ranking-only pool, unaffected.
11. **Two independent calls to the existing `optimize_route()`, not two solvers.**
    `engine.py`, `service.py`, and the matrix layer are unmodified — `nn_from_start`/
    `two_opt`/`schedule_route` were already fully parameterized by start/end anchor
    and time window, and `get_matrix()` already fetches anchor legs fresh, never
    cached, so a PRE call (origin anchor) and a POST call (destination anchor) cannot
    cross-contaminate each other's matrix cache entries. This is **not** a claim that
    the two calls are fully time-safe in every sense: the real-place-to-real-place
    matrix cache is keyed by `(origin_id, dest_id, transport_mode)` with no
    `departure_time`/date dimension, and a stale cached entry (within its TTL) could
    still be reused regardless of which day or segment requested it. That limitation
    predates this ADR and is not fixed here — it is named explicitly rather than
    implied away by the "safe against cross-contamination" claim above.
12. **Segment budgets are hard visit-duration admission ceilings, exactly like ADR-16's
    single `visit_budget_min`** — `pre_visit_budget_min = max(0, (pre_end_s -
    configured_day_start) // 60)`, `post_visit_budget_min = max(0, (configured_day_end
    - effective_post_start) // 60)`. Both bound only the *sum of `visit_duration_min`*
    for their side, never travel or waiting time, and never guarantee feasibility —
    the single-day solver remains the sole source of truth for whether a bucketed
    place's visit is actually reachable. This remains scoped to transition days;
    ordinary days keep the unconstrained ranking-only heuristic.
13. **`DayPlan.skipped` remains a compatibility aggregate, now merging three sources**
    instead of two: side-unresolved rejections (`NO_COORDINATES` pinned places),
    PRE-side outcomes (solver skips or `PRE_TRANSFER_WINDOW_INFEASIBLE`), and
    POST-side outcomes (solver skips or `TRANSFER_WINDOW_INFEASIBLE`, unchanged name).
    The same `place_id` legitimately appears in both `DayPlan.skipped` (the aggregate)
    and the relevant `route_segments[i].skipped` (the detailed, segment-scoped view)
    — this is intentional duplication of one outcome, not two conflicting ones. The
    invariant this ADR guarantees is not "each place_id appears exactly once in the
    JSON" but that **every place has exactly one outcome** — visited in PRE, visited
    in POST, skipped with one reason, or globally unassigned — and never a
    contradictory pair (e.g. present in some segment's `steps` and also in
    `DayPlan.skipped`/`unassigned`).
14. **New skip/unassigned reasons are added only for PRE; existing POST-side reason
    strings are not renamed.** `CAPACITY_EXCEEDED` and `TRANSFER_WINDOW_INFEASIBLE`
    keep their exact ADR-16 meaning and are emitted only from the POST-side branch,
    unchanged. `PRE_TRANSFER_CAPACITY_EXCEEDED` and `PRE_TRANSFER_WINDOW_INFEASIBLE`
    are new, PRE-only reasons. Renaming the POST strings to a symmetrical
    `POST_TRANSFER_*` form was considered and rejected: those exact strings are
    already a shipped API contract from ADR-16, and the segment a skip belongs to is
    already structurally recoverable from which `route_segments[i]` it appears in —
    a prefix on the string itself would be redundant, not clarifying.
    `TRANSFER_DAY_GEOGRAPHY_MISMATCH` is no longer emitted (see decision 8).

## Rationale
### Evaluation of Alternatives
- **Flat `pre_transfer_*` fields on `DayPlan`** (steps/totals/travel_to_end_s each
  duplicated with a `pre_transfer_` prefix) — rejected: five new top-level fields for
  one segment, with no path to a future multi-transfer day without another wave of
  fields. `DayRouteSegment` as a list gives the same information with one new type
  and one new field, and already generalizes to more than two segments.
- **A full generic `DayTimeline`/discriminated-union model** — rejected for this
  slice for the same reason ADR-16 rejected it: it rewrites `DayPlan`/`RouteStep`/the
  empty-day path all at once, for a need this ADR does not have. `DayRouteSegment`'s
  shape does not block a later migration to it.
- **A single flattened `DayPlan.steps` spanning both sides** — rejected: a list that
  silently teleports from the last origin-city stop to the first destination-city
  stop, distinguishable only by inspecting `travel_from_previous_s` on the boundary
  step, is exactly the ambiguity `route_segments` exists to make structural instead
  of implicit.
- **Making `route_segments` conditional on non-zero budget** — the first draft of
  this decision; rejected after review because it makes segment presence itself part
  of what a client has to interpret, undermining the fixed-position contract. See
  decision 2.
- **Renaming `TRANSFER_WINDOW_INFEASIBLE`/`CAPACITY_EXCEEDED` to a symmetrical
  `POST_TRANSFER_*` form** — rejected after review: an unforced break of an
  already-shipped API string for a purely cosmetic symmetry gain. See decision 14.
- **An `AMBIGUOUS` tier or distance-ratio threshold for `TransitionSide`** —
  rejected, matching ADR-16's own reasoning: the nearest-of-two heuristic is a named,
  accepted simplification for clearly-separated cities, not a general regional model.
- **Enforcing the hard visit-duration admission budget on every ordinary day, not
  just transition-day sides** — rejected for the same reason ADR-16 rejected it: this
  slice is validating the mechanism on a narrow, well-tested case, not changing
  every multi-day request's partitioning behavior.

### Technical Considerations
- `_resolve_segment_end_bound_fields` is the one place a resolved second-count is
  turned into an `OptimizeRequest`-legal hour/time pair for a value the caller did
  not directly supply. It is defensive about a resolved end bound landing exactly at
  `24 * 3600`, even though `pre_end_s` in practice never reaches it (`transfer.
  departure_time` is always a same-day `NaiveTime`, strictly below `24:00:00`) — the
  branch exists so the helper stays correct if the formula in decision 5 changes
  later, not because it is reachable today.
- The PRE request's `day_start_hour`/`day_start_time` are forwarded unchanged from
  `DayConfig`, not recomputed — PRE always starts at exactly the configured day
  start, so there is nothing to resolve. Only PRE's end bound goes through
  `_resolve_segment_end_bound_fields`, since it is the only value this ADR
  synthesizes independently of what the caller supplied.
- Two solver calls per transition day roughly double the Google Routes API calls for
  that day (up to two `compute_matrix` calls for the real-place matrices, each with
  up to two more for anchor legs) compared to ADR-16's POST-only day. Acceptable for
  the motivating scope (one transfer per day, ≤31 days), named here rather than left
  as a silent cost increase.

### Integration with Existing Environment
- `DayPlan.route_segments` is purely additive — a consumer that only reads the
  pre-ADR-17 fields observes no change in shape or meaning for those fields, on any
  day, transition or not. `src/trips/` is unaffected: it persists only single-day
  `OptimizeResponse`, never `DayPlan`/`MultiDayResponse` (unchanged since ADR-15).
- `src/transfers/` (`TransferBlock`, `resolve_day_transfer`) is untouched — this ADR
  is entirely about how `multi_day_service.py` and `src/optimizer/solver/models.py`
  consume an already-resolved transfer, not about how a transfer is described or
  validated on the request.
- `src/accommodations/` is untouched — `check_out_by` already existed on
  `AccommodationStay`; this ADR is the first place that reads it.
- The frontend (`apps/frontend/src/lib/types/optimizer.ts`, `DayPlanCard.svelte`)
  does not yet know about `transfer` or `route_segments` — it was never updated for
  ADR-16 either, since that work happened on a separate branch. This ADR does not
  regress it further: it renders exactly what it already rendered (the POST
  projection, under its current field names), unaware of the richer PRE data.
  Teaching the frontend about PRE/POST segments is future work.

### Future Potential
- `DayRouteSegment` as a list, keyed by `kind`, is the seam a future multi-transfer
  day would extend without renaming anything that exists today.
- `PartitionResult`/`TransferSideBuckets` (private to `multi_day_service.py`) isolate
  per-segment bucket/budget/skip bookkeeping behind one return type instead of a
  growing tuple — a future third segment (e.g. a second transfer) extends this
  structure rather than requiring another positional element.

## Consequences
### Positive Outcomes
- A transition day can now show a complete, non-degenerate itinerary on both sides
  of a transfer — closing the exact gap ADR-16 named and deferred.
- `TRANSFER_DAY_GEOGRAPHY_MISMATCH` — a false negative under the old model for any
  place legitimately closer to the origin — no longer exists as an outcome.
- `route_segments` gives every transition day a stable, position-addressable
  two-element contract regardless of how many places actually got scheduled,
  removing an entire category of "why does the shape differ today" questions.

### Challenges & Mitigation
- Two solver calls per transition day double that day's Google Routes API cost —
  mitigated by scope (one transfer per day, ADR-16's existing 31-day cap) and named
  explicitly rather than left implicit.
- The real-place matrix cache remains insensitive to `departure_time`/date — a
  preexisting limitation, not introduced or worsened here, but not fixed either;
  named explicitly rather than implied safe by the anchor-leg freshness guarantee.
- `check_out_by` is consumed only as a conservative upper bound on PRE sightseeing,
  not a model of luggage storage or post-checkout logistics — a traveller who checks
  out, sightsees, and returns for stored bags before the transfer is a real case this
  slice does not represent. Documented here rather than implied solved.
- `departure_time > configured_day_end` is not validated in this slice — a transfer
  can be scheduled outside the visible day window without a 422. Left as a known,
  unvalidated edge case rather than expanding scope to enforce it.

## Status
`Accepted` — scoped to `DayRouteSegment`/`DayPlan.route_segments` in
`src/optimizer/solver/models.py` and their construction in
`src/optimizer/solver/multi_day_service.py`. Persistence, automatic transit lookup,
station/airport transfer endpoints, more than one transfer per day, overnight
transfers, a generic fixed-events timeline, hard admission budgets for ordinary days,
correct Google Routes timezone handling, the 50-place request cap, and the frontend
are all explicitly out of scope and left to future work — see Non-goals.

This ADR supersedes ADR-16 decision 7's `GEOGRAPHY_MISMATCH` branch (an origin-side
place is now a valid PRE candidate, not a rejection) and closes ADR-16's "Pre-transfer
sightseeing" non-goal. All other ADR-16 decisions (door-to-door `TransferBlock`,
anchor precedence, minute precision, the POST window formula, the safety policy for a
transition day without a transfer) remain in force, unchanged.

## Non-goals
- **Persistence.** Unchanged from ADR-15/16 — `src/trips/` still only persists
  single-day trips.
- **Automatic transit-schedule lookup, ticket pricing, or booking.** Unchanged.
- **Station/airport transfer endpoints, or any transit before/after the intercity
  leg.** `TransferBlock` stays door-to-door (origin accommodation → destination
  accommodation), unchanged from ADR-16.
- **More than one transfer per day.** Still enforced by ADR-16's uniqueness
  validator on `transfers` dates.
- **Overnight transfers.** Still rejected by `TransferBlock`'s same-day validator.
- **A generic fixed-events/timeline engine.** `DayRouteSegment` has exactly two
  `kind` values, not an arbitrary event list — see Rationale.
- **Hard admission-budget enforcement for days without a transfer.** Ordinary days
  keep the ranking-only heuristic.
- **Correct timezone handling for `departure_time` sent to Google Routes.** Remains
  naive UTC, unchanged.
- **The 50-place request cap.** Unchanged; scaling to hundreds of places is a
  separate, unrelated problem.
- **Frontend.** `apps/frontend/` is not updated by this ADR.
- **Validating `departure_time`/`arrival_time` against the configured day window.**
  A transfer scheduled outside `[day_start, day_end]` remains a legal, unvalidated
  fixed block — see Consequences.
- **Luggage storage / post-checkout logistics.** `check_out_by` is a conservative
  upper bound on PRE sightseeing only, not a model of what a traveller can do with
  their belongings after checkout.
