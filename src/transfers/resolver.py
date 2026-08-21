"""Deliberately solver-agnostic — mirrors src.accommodations.resolver, see ADR-16."""

from __future__ import annotations

from datetime import date

from src.transfers.models import TransferBlock


def resolve_day_transfer(dates: list[date], transfers: list[TransferBlock]) -> list[TransferBlock | None]:
    """Per day D: the TransferBlock scheduled on that date, if any."""
    by_date = {transfer.date: transfer for transfer in transfers}
    return [by_date.get(day) for day in dates]
