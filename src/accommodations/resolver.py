"""Deliberately solver-agnostic — callers decide what's safe to feed into a hard constraint, see ADR-15."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.accommodations.models import AccommodationStay


@dataclass(frozen=True)
class DayAccommodationAnchors:
    """The stay (if any) a traveller woke up in and the stay (if any) they will sleep in that day."""

    start: AccommodationStay | None
    end: AccommodationStay | None


def resolve_day_anchors(dates: list[date], stays: list[AccommodationStay]) -> list[DayAccommodationAnchors]:
    """Per day D: START = stay with check_in < D <= check_out; END = stay with check_in <= D < check_out. See ADR-15."""
    result: list[DayAccommodationAnchors] = []
    for day in dates:
        start = next((stay for stay in stays if stay.check_in_date < day <= stay.check_out_date), None)
        end = next((stay for stay in stays if stay.check_in_date <= day < stay.check_out_date), None)
        result.append(DayAccommodationAnchors(start=start, end=end))
    return result
