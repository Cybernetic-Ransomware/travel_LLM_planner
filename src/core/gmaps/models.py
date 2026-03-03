from typing import Any

import pendulum
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class ImportRequest(BaseModel):
    """Request body for importing a public Google Maps saved list."""

    list_url: HttpUrl


class ScrapedPlace(BaseModel):
    """A single place as scraped from a public Google Maps list."""

    name: str | None = None
    address: str | None = None
    maps_url: HttpUrl | None = None
    lat: float | None = None
    lng: float | None = None
    gmaps_place_id: str | None = None
    gmaps_cid: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ImportResponse(BaseModel):
    """Summary returned after a completed import operation."""

    list_url: HttpUrl
    list_name: str | None = None
    scraped_at: pendulum.DateTime
    total: int
    upserted: int

    @field_validator("scraped_at", mode="before")
    @classmethod
    def coerce_scraped_at(cls, v: Any) -> pendulum.DateTime:
        if isinstance(v, pendulum.DateTime):
            return v
        return pendulum.instance(v)


class EnrichRequest(BaseModel):
    """Request body for a batch enrichment run via Google Places API."""

    limit: int = 20


class EnrichResponse(BaseModel):
    """Summary returned after a completed enrichment batch."""

    scanned: int
    updated: int


class PlacePatch(BaseModel):
    """Partial update for scheduling preferences. Only provided fields are applied."""

    preferred_hour_from: int | None = None  # local hour 0–23
    preferred_hour_to: int | None = None  # local hour 0–23
    visit_duration_min: int | None = None  # estimated minutes to spend at the place
    skipped: bool | None = None  # soft-exclude from current route planning

    @field_validator("preferred_hour_from", "preferred_hour_to")
    @classmethod
    def validate_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("Hour must be between 0 and 23")
        return v

    @field_validator("visit_duration_min")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("visit_duration_min must be a positive integer")
        return v

    @model_validator(mode="after")
    def validate_hour_range(self) -> PlacePatch:
        if (
            self.preferred_hour_from is not None
            and self.preferred_hour_to is not None
            and self.preferred_hour_from >= self.preferred_hour_to
        ):
            raise ValueError("preferred_hour_from must be less than preferred_hour_to")
        return self


class PlaceOut(BaseModel):
    """Read model for a single place document returned to the panel."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    name: str | None = None
    address: str | None = None
    maps_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    gmaps_place_id: str | None = None
    list_name: str | None = None
    source_list_url: str | None = None
    scraped_at: pendulum.DateTime | None = None
    enriched_at: pendulum.DateTime | None = None
    # Scheduling preferences — set via panel, consumed by the optimizer
    preferred_hour_from: int | None = None
    preferred_hour_to: int | None = None
    visit_duration_min: int | None = None
    skipped: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def coerce_object_id(cls, v: Any) -> str:
        """MongoDB returns _id as bson.ObjectId — coerce to plain string."""
        return str(v)

    @field_validator("scraped_at", "enriched_at", mode="before")
    @classmethod
    def coerce_datetime(cls, v: Any) -> pendulum.DateTime | None:
        if v is None:
            return None
        if isinstance(v, pendulum.DateTime):
            return v
        return pendulum.instance(v)