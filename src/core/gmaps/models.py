from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ImportRequest(BaseModel):
    list_url: HttpUrl


class ScrapedPlace(BaseModel):
    name: str | None = None
    address: str | None = None
    maps_url: HttpUrl | None = None
    lat: float | None = None
    lng: float | None = None
    gmaps_place_id: str | None = None
    gmaps_cid: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ImportResponse(BaseModel):
    list_url: HttpUrl
    list_name: str | None = None
    scraped_at: datetime
    total: int
    upserted: int


class EnrichRequest(BaseModel):
    limit: int = 20


class EnrichResponse(BaseModel):
    scanned: int
    updated: int
