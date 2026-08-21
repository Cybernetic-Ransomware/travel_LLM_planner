from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class TransferBlock(BaseModel):
    """A same-day, fixed-time journey between two accommodation stays — see ADR-16."""

    date: date
    departure_time: time
    arrival_time: time
    label: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_same_day_arrival_after_departure(self) -> TransferBlock:
        if self.arrival_time <= self.departure_time:
            raise ValueError(
                "arrival_time must be after departure_time; overnight transfers are not supported in this slice"
            )
        return self
