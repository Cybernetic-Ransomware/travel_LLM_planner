from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from src.time_validation import NaiveTime


class AccommodationStay(BaseModel):
    """A lodging stay covering the half-open night interval [check_in_date, check_out_date) — see ADR-15."""

    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    check_in_date: date
    check_out_date: date

    check_in_from: NaiveTime | None = None
    check_out_by: NaiveTime | None = None

    @model_validator(mode="after")
    def validate_stay_covers_at_least_one_night(self) -> AccommodationStay:
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        return self


def validate_no_stay_overlaps(stays: list[AccommodationStay]) -> None:
    """Raise ValueError if any two stays share a night. A gap between stays is legal."""
    ordered = sorted(stays, key=lambda stay: stay.check_in_date)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.check_in_date < previous.check_out_date:
            raise ValueError(
                f"accommodation stays overlap: {previous.name!r} "
                f"({previous.check_in_date}–{previous.check_out_date}) and {current.name!r} "
                f"({current.check_in_date}–{current.check_out_date})"
            )
