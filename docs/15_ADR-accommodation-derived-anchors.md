# ADR-15: Accommodation-derived daily START/END anchors

## Context
PR #32 gave the multi-day optimizer real START/END location anchors: `OptimizeRequest`,
`DayConfig`, and `MultiDayRequest` all carry optional `start_lat/lng`/`end_lat/lng`, and
`multi_day_service.py` resolves each day's anchors through a `DayConfig → MultiDayRequest global
→ None` precedence chain. `service.py`/`engine.py` treat END as a **hard feasibility deadline**:
`nn_from_start` rejects any candidate place that would leave the route unable to reach the END
anchor by `day_end_s`.

Users plan trips around hotel stays ("Tokyo Hotel 05–10, Kyoto Hotel 10–14"), not per-day
coordinates. Manually computing `DayConfig.start_lat/lng`/`end_lat/lng` for every day of a stay is
exactly the kind of busywork the anchor mechanism from PR #32 should remove — but doing so
naively creates a new failure mode: on the day a traveller changes hotels, the accommodation
resolver would derive START from one stay and END from a different, geographically distant one.
Feeding that distant END into the existing hard-deadline mechanism can strand or drop places that
are perfectly visitable, silently making results *worse* than not having the feature at all.

## Decision
1. **Module placement.** Accommodation stays live in a new `src/accommodations/` package, not in
   `src/optimizer/solver/models.py`. `AccommodationStay` (`models.py`) and the pure,
   solver-agnostic `resolve_day_anchors` (`resolver.py`) have zero knowledge of TSP, distance
   matrices, or hard constraints; `src/optimizer/solver/models.py` and `multi_day_service.py`
   import from `src.accommodations`, never the reverse.
2. **Precedence chain.** `explicit DayConfig anchor → accommodation-derived anchor → global
   MultiDayRequest anchor → None`, applied independently for START and END. Explicit `DayConfig`
   always wins, so a manual override (e.g. "start from the airport, not the hotel, today") needs
   no special-casing.
3. **Changeover-day safety policy.** A day is a *transition day* when `resolve_day_anchors`
   returns two different stay objects for START and END (`multi_day_service._is_accommodation_transition_day`,
   compared by object identity, not by `name` — stay names are not unique). On a transition day the
   accommodation-derived START is still applied (safe: START has no "must arrive by" semantics),
   but the accommodation-derived END is deliberately **not** forwarded to the per-day
   `OptimizeRequest`; it falls through to an explicit `DayConfig`/global anchor if the caller set
   one, or to `None` otherwise.
4. **Non-goals.** `check_in_from`/`check_out_by` are represented on `AccommodationStay` but are not
   read by the resolver or the solver in this slice — they are not persisted anywhere either, since
   nothing in `src/trips/` persists multi-day trips yet. No `Transfer`/leg model is introduced;
   the actual travel time of a changeover day (e.g. Tokyo→Kyoto by rail) is not computed by this
   feature.

## Rationale
### Evaluation of Alternatives
- **Always wire the accommodation END through unconditionally** — rejected: this is the behaviour
  that motivated decision 3. `nn_from_start`'s END-reachability check would reject any place whose
  visit would leave insufficient time to still reach a distant END, which can empty out an
  otherwise normal morning in the departure city.
- **Fake the changeover by giving each half of the day its own `day_start_hour`/`day_end_hour`**
  (e.g. "Tokyo ends at 10:00, Kyoto starts at 15:00") — rejected: `OptimizeRequest`/`DayConfig`
  model one day as one contiguous window with one START and one END; splitting it in two would
  misrepresent the day's actual geography and does not compose with the existing single-day
  solver without deeper changes.
- **Solve the changeover day properly (minimal `Transfer` leg model)** — deferred, not rejected.
  This is a materially different mechanic (a leg that is not a place visit, potentially with fixed
  departure/arrival times and buffers) and deserves its own design, not a bolt-on to this slice.
- **Put `AccommodationStay` inside `src/optimizer/solver/models.py`** — rejected: the optimizer
  should know as little domain detail as possible (existing convention, see ADR-02's rationale for
  keeping cross-cutting concerns out of layers that should not own them). Composing a Pydantic
  model from a sibling domain package is already an established pattern in this codebase —
  `src/trips/models.py` imports `OptimizeRequest`/`OptimizeResponse` from
  `src.optimizer.solver.models` in the opposite direction.

### Technical Considerations
- `resolve_day_anchors` implements the half-open night interval `[check_in_date, check_out_date)`:
  `START(D) = check_in_date < D <= check_out_date`, `END(D) = check_in_date <= D < check_out_date`.
  A stay's own check-in day is never its own START (the traveller woke up elsewhere), and its
  check-out day is never its own END (they no longer sleep there that night).
- Overlap validation (`validate_no_stay_overlaps`) rejects two stays sharing a night; a *gap*
  between stays is explicitly legal (it may represent a night train, a ferry, or accommodation the
  planner simply has not filled in yet) and resolves to `None` on both sides for the uncovered day.
- Identifying "the same stay" for transition-day detection relies on Python object identity within
  one `resolve_day_anchors` call, not on `AccommodationStay.id` — this model has no `id` field (see
  Consequences). This is safe only as long as stays are not deduplicated/copied between resolution
  and comparison.

### Integration with Existing Environment
- `MultiDayRequest.accommodations: list[AccommodationStay] = Field(default_factory=list)` is
  purely additive; a request that omits the field behaves exactly as before PR #32's anchors were
  extended with this feature.
- No changes to `DayPlan`/`MultiDayResponse` — see Consequences for why an earlier draft's
  `resolved_start_accommodation`/`resolved_end_accommodation` fields were dropped.

### Future Potential
- The transition-day detection this ADR introduces is exactly the information a future `Transfer`
  model needs to decide which two legs to solve independently and bridge — this feature identifies
  *which* day needs special handling without attempting to handle it.
- Once `src/trips/` persists multi-day trips, `accommodations` is a natural field to persist
  alongside them (see Non-goals).

## Consequences
### Positive Outcomes
- Multi-day trips describable by hotel stays instead of per-day coordinates, with zero risk of the
  new feature making a day's plan worse than omitting it — the mechanism this ADR describes is
  intentionally conservative on the one day it cannot safely automate.
- `src/accommodations/` stays trivially testable in isolation (pure functions, no I/O, no solver
  knowledge).

### Challenges & Mitigation
- A transition day gets no automatic END constraint, which means an unrealistic changeover
  (e.g. a "walk" from Tokyo to Kyoto) is not flagged, just silently unconstrained. Mitigated by
  documenting this explicitly rather than pretending the day is solved; a real fix requires the
  deferred `Transfer` model.
- Object-identity-based transition detection would silently break if `AccommodationStay` instances
  were copied or reconstructed between resolution and comparison. Mitigated by keeping resolution
  and comparison inside the same `optimize_trip` call over the same `request.accommodations` list;
  flagged as a risk to revisit once stays gain a persisted `id` (see Future Potential).
- An earlier draft of this feature added `resolved_start_accommodation`/`resolved_end_accommodation:
  str | None` to `DayPlan` for API observability. Removed: `AccommodationStay.name` is not a unique
  identifier, so echoing it back would be a misleading pseudo-identifier: a caller who sent the
  `accommodations` list can already determine which day is a transition day from their own request
  data, and correctness is verifiable through existing response fields (steps/skipped) plus tests
  asserting what reaches the per-day `OptimizeRequest`. A real provenance field, if ever needed by a
  UI, should be a proper `source`-tagged type, not two loose strings added on spec.

## Status
`Accepted` — scoped to `src/accommodations/` and its integration into
`src/optimizer/solver/multi_day_service.py`. Persistence, check-in/check-out enforcement, and a
`Transfer` model are explicitly out of scope and left to future ADRs.
