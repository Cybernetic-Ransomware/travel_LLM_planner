from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

PlacePriority = Literal["must_see", "normal", "optional"]


class ImportRequest(BaseModel):
    """Request body for importing a public Google Maps saved list."""

    model_config = ConfigDict(json_schema_extra={"example": {"list_url": "https://maps.app.goo.gl/o94j8NnqLffpivrv7"}})

    list_url: HttpUrl


class ScrapedPlace(BaseModel):
    """A single place as scraped from a public Google Maps list."""

    name: str | None = None
    address: str | None = None
    maps_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    gmaps_place_id: str | None = None
    gmaps_cid: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ImportResponse(BaseModel):
    """Summary returned after a completed import operation."""

    list_url: HttpUrl
    list_name: str | None = None
    scraped_at: datetime
    total: int
    upserted: int


class EnrichRequest(BaseModel):
    """Request body for a batch enrichment run via Google Places API."""

    limit: int = 20


class EnrichResponse(BaseModel):
    """Summary returned after a completed enrichment batch."""

    scanned: int
    updated: int


class PlacePatch(BaseModel):
    """Partial update for scheduling preferences.

    Omitted fields are left unchanged; an explicit null clears the stored value
    (except ``skipped``, which must always be a boolean).
    """

    preferred_hour_from: int | None = None  # local hour 0–23
    preferred_hour_to: int | None = None  # local hour 0–23
    visit_duration_min: int | None = None  # estimated minutes to spend at the place
    priority: PlacePriority | None = None  # null clears the field — reads back as "normal"
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

    @model_validator(mode="after")
    def validate_skipped_not_null(self) -> PlacePatch:
        if "skipped" in self.model_fields_set and self.skipped is None:
            raise ValueError("skipped cannot be null; use true or false")
        return self


class PlaceCreate(BaseModel):
    """Input model for creating a new place via the LLM tool."""

    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    visit_duration_min: int | None = None
    preferred_hour_from: int | None = None
    preferred_hour_to: int | None = None
    priority: PlacePriority | None = None

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
    def validate_hour_range(self) -> PlaceCreate:
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

    id: str = Field(validation_alias="_id")
    name: str | None = None
    address: str | None = None
    maps_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    gmaps_place_id: str | None = None
    list_name: str | None = None
    source_list_url: str | None = None
    scraped_at: datetime | None = None
    enriched_at: datetime | None = None
    # Opening hours from Google Places API — populated after enrichment
    opening_hours: dict | None = None  # regularOpeningHours from Places API (New)
    # Scheduling preferences — set via panel, consumed by the optimizer
    preferred_hour_from: int | None = None
    preferred_hour_to: int | None = None
    visit_duration_min: int | None = None
    priority: PlacePriority = "normal"
    skipped: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def coerce_object_id(cls, v: Any) -> str:
        """MongoDB returns _id as bson.ObjectId — coerce to plain string."""
        return str(v)
