# ADR-16: Transition-day transfers as time-consuming blocks

## Context
ADR-15 gave multi-day trips accommodation-derived daily START/END anchors, but
deliberately left the changeover day itself unmodeled: on the day a traveller checks
out of one hotel and into another, `multi_day_service.py` suppresses both
accommodation-derived anchors rather than risk stranding a reachable place behind a
long, unmodeled leg. ADR-15 named this a known, accepted gap and explicitly deferred
"a minimal `Transfer` leg model" to future work.

The gap is real: a transition day with a Tokyo→Kyoto Shinkansen still shows up in a
`MultiDayResponse` as either an empty `DayPlan` (no places assigned) or a fully
unconstrained day where the partitioner — which has no geographic awareness — can
place a Kyoto attraction on the day the traveller is still in Tokyo. This ADR
introduces `TransferBlock`, a fixed-time journey between the two accommodation stays
either side of a transition day, and wires it through partitioning, anchor
resolution, and the response shape so the transfer is a real, time-consuming part of
the day rather than an ignored field.

## Decision
1. **`TransferBlock` lives in a new `src/transfers/` package, not `src/accommodations/`.**
   `TransferBlock` (`date`, `departure_time`, `arrival_time`, optional `label`) carries
   nothing hotel-specific — only the orchestration in `multi_day_service.py` ties it to
   the two `AccommodationStay` objects either side of the transition day (via
   `DayAccommodationAnchors`). Keeping it in `src/accommodations/` would force a future
   generic transfer (e.g. airport→station, unrelated to any accommodation) or
   pre-transfer sightseeing to relocate a settled domain. `src/transfers/resolver.py`
   mirrors `src/accommodations/resolver.py`'s `resolve_day_anchors` with
   `resolve_day_transfer(dates, transfers) -> list[TransferBlock | None]` — equally
   solver-agnostic, equally a pure per-day lookup.
2. **Request-side `TransferBlock` and response-side `TransferSegment`/`TransferEndpoint`
   are different types.** `TransferBlock` stays minimal because its origin/destination
   are implied by the accommodations already in the request. `DayPlan.transfer:
   TransferSegment | None` must be self-contained for a consumer of the API response —
   it carries `origin`/`destination` as `TransferEndpoint(name, lat, lng)` (display
   data, not an identifier — the same reasoning ADR-15 used to reject
   `resolved_start_accommodation: str | None` doesn't apply here, since a `name` used
   only for display in an already-fully-resolved response isn't standing in as a
   pseudo-identifier) plus `departure_time`, `arrival_time`, `duration_s`, and `label`.
3. **One TransferBlock per date, and only on a transition day.** `MultiDayRequest.
   transfers: list[TransferBlock] = Field(default_factory=list)` is validated for:
   unique dates within `transfers`; every transfer date must be among `request.days`
   dates; every transfer date must resolve to a transition day via
   `resolve_day_anchors` (both accommodation-derived START and END present and
   distinct) — a transfer submitted for any other day is a 422, not a silent no-op,
   matching the existing style of `validate_no_transit`/`validate_day_indices`.
   `TransferBlock` itself rejects `arrival_time <= departure_time` — overnight
   transfers are out of scope for this slice (see Non-goals).
4. **Anchor precedence gains a transfer-derived tier, and explicit `DayConfig` anchors
   are rejected outright when a transfer exists for that date.** The precedence chain
   from ADR-15 becomes `transfer-derived → accommodation-derived → global
   MultiDayRequest anchor → None` for any date with a `TransferBlock` — explicit
   `DayConfig.start_lat/lng`/`end_lat/lng` for that date is a validation error
   (`validate_transfer_day_config_conflict`), not simply overridden. `TransferBlock`
   models a **door-to-door** journey (origin accommodation → destination
   accommodation); letting an explicit `DayConfig` anchor win, per the ordinary
   precedence rule, would silently teleport the post-transfer segment to a location the
   transfer never actually reached, without ever modeling the extra leg. A global
   `MultiDayRequest`-level anchor needs no such guard — it only takes effect when
   nothing above it applies, and transfer-derived anchors always apply on a transfer
   date, so there is no conflict to resolve.
5. **Effective post-transfer start is `max(arrival_time, check_in_from, configured day
   start)`, in seconds.** A traveller who arrives before check-in waits (mirroring how
   `TimeWindow.earliest_start` already lets a solver wait for a place to open); a
   traveller can never be shown starting sightseeing before they actually arrived,
   since `max()` is monotonic in `arrival_time`. `check_out_by` is read but not
   enforced — a late checkout with luggage storage is a legitimate real-world case this
   model doesn't yet represent, and is deliberately left advisory-only rather than
   blocking a request over it.
6. **Minute precision is threaded through the whole pipeline, not just the request
   model.** `OptimizeRequest`/`DayConfig` gain additive `day_start_time`/`day_end_time:
   time | None` fields; a shared `resolve_day_bound_s(hour, explicit_time)` /
   `seconds_to_time(s)` pair (in `src/optimizer/solver/models.py`) resolves the
   effective seconds-from-midnight and converts back. `service.py`'s `optimize_route`
   uses this for both `day_start_s`/`day_end_s` and the `departure_time` sent to Google
   Routes — previously both were computed from `day_start_hour`/`day_end_hour` alone,
   which would have made the new fields dead on arrival for a multi-day transfer day.
   `day_end_time == time(0, 0)` is rejected outright (midnight cannot be expressed this
   way — `day_end_hour=24` remains the only way to say "until midnight"), and
   `day_end_hour == 24` combined with any explicit `day_end_time` is also rejected, so
   there is exactly one way to express end-of-day, never two disagreeing ones. The
   `validate_day_range` validator on both models now compares *effective* seconds, not
   raw hours — `day_start_hour=9, day_start_time=22:30, day_end_hour=21` would pass a
   naive hour-only check but must not pass overall.
7. **A unified partitioning mechanism resolves eligibility, admission budget, and
   pre-solver skips in one pass.** `_partition_places` gained an optional
   `transfer_contexts: dict[int, TransferDayContext]` parameter and now returns
   `(buckets, unassigned, pre_solver_skipped_by_day)`. For a date with a
   `TransferDayContext`, every place — pinned, flexible, or auto — is evaluated by
   `_transition_day_eligibility(doc, origin, destination)`, a **three-state** result
   (`ELIGIBLE` / `GEOGRAPHY_MISMATCH` / `NO_COORDINATES`) using haversine distance to
   the two accommodation stays either side of the day, not a raw squared
   latitude/longitude difference (which distorts with latitude) and not a binary
   pass/fail that would conflate "no coordinates" with "wrong city" — those are
   different failures with different, pre-existing response semantics
   (`NO_COORDINATES` already exists as a `SkippedPlace.reason`).
   - **Pinned** places are checked *before* being added to the bucket and *before*
     `fill` is incremented: a pinned place that fails eligibility must not silently
     consume the day's admission budget and crowd out a legitimate destination-city
     place processed afterwards. A rejected pinned place is recorded directly into
     `pre_solver_skipped_by_day[day_idx]`.
   - **Auto/flexible** places filter their candidate days down to admissible ones
     *first*, then rank among only those — not the reverse. Picking the
     highest-ranked candidate first and only then checking whether it happens to pass
     would wrongly send an otherwise-placeable place to `unassigned` just because the
     single roomiest-looking candidate happened to be an inadmissible transfer day,
     even when another perfectly good candidate day existed.
   - Only auto/flexible places are bound by a **hard admission budget**
     (`visit_budget_min`, computed as `(configured_day_end_s -
     effective_start_s) // 60`, 0 when no viable window exists) — but this budget
     bounds only the *sum of `visit_duration_min`*, not travel or waiting time between
     stops. It is documented and named accordingly (a "hard visit-duration admission
     budget", not "capacity" or a feasibility guarantee) so a future reader does not
     assume the partitioner alone proves a day is solvable — the single-day solver
     can, and does, still classify a place as infeasible afterwards once travel time is
     accounted for. This budget is scoped strictly to transfer dates; ordinary days
     keep today's ranking-only heuristic unchanged.
   - Places that fail admission are never force-packed: auto/flexible failures land in
     `MultiDayResponse.unassigned` (previously always `[]` — this is its first real
     use), pinned failures land in the day's `DayPlan.skipped`.
8. **No viable post-transfer window is a distinct, explicit branch — not a disguised
   empty day.** When `visit_budget_min == 0` (arrival, or check-in, at or after the
   configured day end), `optimize_route` is never called for that day (its
   `place_ids` cannot legally be empty), and every place still assigned to that date
   — necessarily pinned, since auto/flexible were already filtered out during
   partitioning — is surfaced in `DayPlan.skipped` with reason
   `TRANSFER_WINDOW_INFEASIBLE`, not silently dropped.
9. **`DayPlan.skipped` is an explicit merge of two independent sources.** Places
   rejected before the single-day solver ever runs (`pre_solver_skipped`, from
   geography/no-coordinates) and places the solver itself skips
   (`single_result.skipped`, e.g. `TIME_WINDOW_INFEASIBLE`) are concatenated —
   `pre_solver_skipped + single_result.skipped` — never one in place of the other.
   Using only the solver's own list would silently drop every place this feature
   itself filtered out before the solver ran, defeating the point of the feature.
10. **`total_travel_time_s` is unchanged in meaning.** It continues to mean exactly
    what it meant before this ADR — local solver travel time for the day's steps —
    and does **not** include `TransferSegment.duration_s`. A consumer that already
    sums `total_travel_time_s` against `travel_from_previous_s`/`travel_to_end_s`
    keeps getting the same answer. The transfer's own duration is only ever exposed
    via `DayPlan.transfer.duration_s`.

## Rationale
### Evaluation of Alternatives
- **Give `TransferBlock` its own origin/destination coordinates, independent of
  accommodations** — rejected: duplicates fields `AccommodationStay` already has and
  reopens the geography-mismatch risk ADR-15 closed (a transfer's endpoints could then
  silently disagree with the accommodations in the same request).
- **A generic `DayTimeline`/`FixedBlock` model with transfer as one block type** — the
  eventual right shape, but rewrites `DayPlan`/`RouteStep`/the empty-day path all at
  once with no test precedent; deferred, not rejected, and nothing in this ADR's
  `TransferSegment` shape blocks migrating to it later (it already carries
  start/end/duration/origin/destination, the fields a `DayTimelineItem` variant would
  need).
- **Split the transition day into two full optimization segments** (pre-transfer
  sightseeing in the origin city, then the transfer, then post-transfer sightseeing) —
  doubles the solver surface (two matrices, two anchor sets, two `two_opt` runs
  stitched together) for a case the motivating scenario doesn't need; deferred as
  "pre-transfer sightseeing" (see Non-goals), and the post-transfer-only shape chosen
  here composes with it additively later.
- **Enforce `visit_budget_min` as a true hard capacity for every day, not just transfer
  days** — considered, since `_partition_places`'s existing capacity math was already
  known to be ranking-only for every day, not just transfer days. Rejected for this
  slice: `unassigned` becomes meaningfully populated here for the first time, and it's
  safer to validate the mechanism on the narrow, well-tested transfer-day case before
  changing partitioner behavior for every existing multi-day request.
- **Pick best-day-first, then check eligibility** for auto/flexible partitioning — the
  first implementation of this ADR did exactly this, and a review caught the bug: it
  can send a place to `unassigned` even when a different, perfectly good candidate day
  existed, only because the single highest-ranked candidate happened to fail. Fixed to
  filter admissible candidates first, then rank only among those.

### Technical Considerations
- Haversine distance (not raw squared lat/lng difference) is used for the
  origin-vs-destination eligibility comparison — degrees of longitude shrink with
  latitude, so a naive squared difference can misorder places near the poles or at
  very different latitudes than the accommodations being compared. This is still a
  binary comparison to exactly two points, not a region/clustering algorithm — a
  deliberate simplification, sufficient for the motivating Tokyo/Kyoto scale (hundreds
  of kilometers apart), and named here as a boundary of correctness: a place roughly
  equidistant between two closer cities could still be misclassified.
- `resolve_day_bound_s`/`seconds_to_time` are the single shared conversion pair between
  hour-only and minute-precise day bounds, used identically by `OptimizeRequest`,
  `DayConfig`, `service.py`, and `multi_day_service.py` — one function, not parallel
  reimplementations that could drift.
- `departure_time` sent to Google Routes for TRANSIT/DRIVE matrix lookups is
  constructed with `tzinfo=UTC` — this was already true before this ADR and remains a
  naive stand-in for local wall-clock time, unrelated to the transfer's own timezone.
  Minute precision here makes wall-clock times more precise; it does not make them
  timezone-correct. See Non-goals.

### Integration with Existing Environment
- `MultiDayRequest.transfers: list[TransferBlock] = Field(default_factory=list)` is
  purely additive, exactly like `accommodations` in ADR-15 — a request that omits the
  field, or a transition day with no matching `TransferBlock`, behaves identically to
  before this ADR (`_is_accommodation_transition_day` still suppresses both
  accommodation-derived anchors with no transfer wired in).
- `MultiDayRequest.days` gained `validate_unique_day_dates` — an unrelated but
  necessary hardening, since `TransferBlock` is matched to a day by date; two
  `DayConfig` entries sharing a date would make that matching ambiguous. This closes a
  pre-existing gap (duplicate day dates were previously accepted) rather than
  introducing new surface area.
- `MultiDayRequest.days` max_length raised from 14 to 31 in the same branch: an
  undocumented, arbitrary constant from the original multi-day implementation
  (`3264b91`), with no accompanying rationale in its commit history and no test at its
  boundary, that would otherwise block the target ~3-week trip use case this feature
  is built for. A one-line, purely numeric `Field` constraint change with no
  algorithmic dependency on the number.

### Future Potential
- `resolve_day_transfer`'s per-day lookup and `TransferDayContext`'s composition of
  `(origin, destination, effective_start_s, visit_budget_min)` are the exact seams a
  future multi-transfer-per-day or pre-transfer-sightseeing feature would extend,
  without renaming or restructuring what already exists.
- `TransferSegment`'s shape (origin/destination/departure/arrival/duration/label) is
  the natural first variant of a future generic `DayTimelineItem`, should the codebase
  later adopt ADR-15/16's originally-considered generic timeline model.
- Once `src/trips/` persists multi-day trips, `transfers` — like `accommodations` — is
  a natural field to persist alongside them.

## Consequences
### Positive Outcomes
- A transition day with a `TransferBlock` now shows a real, time-consuming block in
  the response, with the post-transfer segment correctly anchored to the destination
  accommodation and never populated with origin-city places — closing the exact gap
  ADR-15 named and deferred.
- `MultiDayResponse.unassigned` and `SkippedPlace.reason` gain real, non-silent
  meaning for transfer-day rejections (`TRANSFER_DAY_GEOGRAPHY_MISMATCH`,
  `TRANSFER_WINDOW_INFEASIBLE`, `CAPACITY_EXCEEDED`), reusing `NO_COORDINATES` where
  it already applies instead of inventing an overlapping reason.
- A transition day with **no** `TransferBlock` submitted is provably unaffected
  (regression-tested) — this feature is strictly opt-in.

### Challenges & Mitigation
- The geography eligibility check is a binary nearest-of-two-stays comparison, not a
  true regional model — mitigated by scope (this ADR targets clearly-separated cities
  like the motivating Tokyo/Kyoto case) and named explicitly as a future-work boundary
  rather than presented as fully general.
- `visit_budget_min` bounds only summed visit duration, not travel/wait — mitigated by
  naming it accordingly in code and docs, and by leaving final feasibility to the
  existing single-day solver, which already handles this correctly for every other
  day.
- `departure_time`'s naive UTC handling predates this ADR and is not fixed here —
  mitigated by naming it explicitly as a non-goal rather than letting minute precision
  imply a timezone fix that hasn't happened.

## Status
`Accepted` — scoped to `src/transfers/`, its integration into
`src/optimizer/solver/models.py`, `src/optimizer/solver/service.py`, and
`src/optimizer/solver/multi_day_service.py`. Persistence, overnight transfers,
multiple transfers per day, pre-transfer sightseeing, automatic transit-schedule
lookup, and correct transfer/departure-time timezone handling are explicitly out of
scope and left to future ADRs.

## Non-goals
- **Persistence.** `transfers` stays request-only, exactly like `accommodations` in
  ADR-15 — `src/trips/` still only persists single-day trips.
- **Automatic transit-schedule lookup, ticket pricing, or booking.** Departure/arrival
  times are always supplied by the caller; nothing in this feature queries a live
  timetable or fare API.
- **More than one transfer per day.** Enforced by a uniqueness validator on
  `transfers` dates; a second transfer for an already-covered date is a 422.
- **Overnight transfers.** `arrival_time <= departure_time` is rejected outright, not
  silently mishandled — a deliberate same-calendar-day-only restriction for this
  slice.
- **Pre-transfer sightseeing.** This slice models only the segment after the
  transfer; the origin-city side of a transition day is untouched, matching the
  motivating scenario (checkout → transfer → check-in → sightseeing).
- **A generic fixed-events/timeline engine.** `TransferSegment` is a single dedicated
  field on `DayPlan`, not a generic block list — see Rationale.
- **Hard capacity/admission-budget enforcement for days without a transfer.** Ordinary
  days keep today's ranking-only partitioning heuristic unchanged.
- **Correct timezone handling for `departure_time` sent to Google Routes.** Remains
  naive UTC, unchanged by this ADR — see Technical Considerations.
- **Frontend.**
