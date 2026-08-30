"""Bounded, deterministic system-prompt rendering of a persisted MULTI_DAY trip.

The agent gets this summary automatically when the chat is opened against a
saved trip, so it never has to call ``get_trip_details`` first. Every
user-controlled string (trip / place / accommodation / transfer names) goes
through ``_sanitize_for_prompt``; the whole block is capped so a large trip
can't blow the context window.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.optimizer.solver.models import (
    DayConfig,
    MultiDayRequest,
    PlaceDayPreference,
    resolve_day_bound_s,
    seconds_to_time,
)
from src.orchestrator.prompt_util import _sanitize_for_prompt
from src.trips.models import MultiDayTripDetailOut

_MAX_PROMPT_CHARS = 6000


@dataclass(frozen=True)
class TripPromptContext:
    trip_id: str
    name: str
    request: MultiDayRequest
    place_names: dict[str, str]
    itinerary_digest: list[str]
    unassigned_names: list[str]

    @classmethod
    def from_detail(cls, trip: MultiDayTripDetailOut) -> TripPromptContext:
        return cls(
            trip_id=trip.id,
            name=trip.name,
            request=trip.multi_day_request,
            place_names=_collect_place_names(trip),
            itinerary_digest=_build_itinerary_digest(trip),
            unassigned_names=[s.name or s.place_id for s in trip.multi_day_response.unassigned],
        )


def build_trip_context_prompt(ctx: TripPromptContext) -> str:
    req = ctx.request
    dates = [cfg.date for cfg in req.days]
    lines = [
        "You are editing the saved multi-day trip below.",
        (
            f"Trip id: {ctx.trip_id} | Name: {_sanitize_for_prompt(ctx.name)} | "
            f"Dates: {min(dates)}-{max(dates)} ({len(req.days)} days)"
        ),
        "",
        "Days:",
    ]
    for index, cfg in enumerate(req.days):
        lines.append(f"- day {index} {cfg.date}  window {_window(cfg)}")

    lines.append("Places (id -> assignment):")
    for pref in req.places[:50]:
        name = _sanitize_for_prompt(ctx.place_names.get(pref.place_id, pref.place_id))
        lines.append(f"- [id={pref.place_id}] {name}  {_assignment(pref)}")

    if req.accommodations:
        lines.append("Accommodations:")
        ordered = sorted(req.accommodations, key=lambda stay: stay.check_in_date)
        for stay_index, stay in enumerate(ordered):
            extra = f"  (check-in from {stay.check_in_from.strftime('%H:%M')})" if stay.check_in_from else ""
            lines.append(
                f"- [stay {stay_index}] {_sanitize_for_prompt(stay.name)}  "
                f"{stay.check_in_date} -> {stay.check_out_date}{extra}"
            )

    if req.transfers:
        lines.append("Transfers:")
        for transfer in sorted(req.transfers, key=lambda t: t.date):
            label = f"  ({_sanitize_for_prompt(transfer.label)})" if transfer.label else ""
            lines.append(
                f"- {transfer.date}  depart {transfer.departure_time.strftime('%H:%M')} -> "
                f"arrive {transfer.arrival_time.strftime('%H:%M')}{label}"
            )

    if ctx.itinerary_digest:
        lines.append("Itinerary digest:")
        lines.extend(ctx.itinerary_digest)

    unassigned = [_sanitize_for_prompt(name) for name in ctx.unassigned_names]
    if unassigned:
        lines.append("Unassigned: " + ", ".join(unassigned))

    lines.append("")
    lines.append(
        "To change this trip call edit_multi_day_trip(operations=[...]). Describe the change and get "
        "explicit user confirmation first. Do NOT use update_visit_hours / skip_place / add_place here."
    )

    prompt = "\n".join(lines)
    if len(prompt) > _MAX_PROMPT_CHARS:
        # Trim the digest first — it is the least load-bearing section for editing.
        without_digest = [line for line in lines if line not in ctx.itinerary_digest and line != "Itinerary digest:"]
        prompt = "\n".join(without_digest)[:_MAX_PROMPT_CHARS]
    return prompt


def _window(cfg: DayConfig) -> str:
    start = seconds_to_time(resolve_day_bound_s(cfg.day_start_hour, cfg.day_start_time))
    end_s = resolve_day_bound_s(cfg.day_end_hour, cfg.day_end_time)
    end = seconds_to_time(end_s) if end_s < 24 * 3600 else None
    end_text = end.strftime("%H:%M") if end is not None else "24:00"
    return f"{start.strftime('%H:%M')}-{end_text}"


def _assignment(pref: PlaceDayPreference) -> str:
    slots = pref.day_preferences
    if not slots:
        return "AUTO"
    if len(slots) == 1:
        slot = slots[0]
        if slot.preferred_hour_from is not None and slot.preferred_hour_to is not None:
            return f"PINNED day {slot.day_index}, pref {slot.preferred_hour_from:02d}:00-{slot.preferred_hour_to:02d}:00"
        return f"PINNED day {slot.day_index}"
    return "FLEXIBLE days " + ",".join(str(slot.day_index) for slot in slots)


def _collect_place_names(trip: MultiDayTripDetailOut) -> dict[str, str]:
    names: dict[str, str] = {}
    for day in trip.multi_day_response.days:
        _harvest_steps(day.steps, names)
        for segment in day.route_segments:
            _harvest_steps(segment.steps, names)
        for skipped in day.skipped:
            if skipped.name:
                names.setdefault(skipped.place_id, skipped.name)
    for skipped in trip.multi_day_response.unassigned:
        if skipped.name:
            names.setdefault(skipped.place_id, skipped.name)
    return names


def _harvest_steps(steps, names: dict[str, str]) -> None:
    for step in steps:
        if step.name:
            names.setdefault(step.place_id, step.name)


def _build_itinerary_digest(trip: MultiDayTripDetailOut) -> list[str]:
    digest: list[str] = []
    for day in trip.multi_day_response.days:
        if day.route_segments:
            by_kind = {segment.kind: segment for segment in day.route_segments}
            pre = len(by_kind["PRE_TRANSFER"].steps) if "PRE_TRANSFER" in by_kind else 0
            post = len(by_kind["POST_TRANSFER"].steps) if "POST_TRANSFER" in by_kind else 0
            digest.append(f"- day {day.day_index}: transfer day, {pre} stops before / {post} after")
        else:
            ends = day.steps[-1].departure_time.strftime("%H:%M") if day.steps else "—"
            digest.append(f"- day {day.day_index}: {len(day.steps)} stops, ends {ends}")
    return digest
