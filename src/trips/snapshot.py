"""The single definition of "persisted trip state identity": the full canonical JSON of a
``SaveTripRequest`` (``name`` included, so it is restored on revert) + ``schema_version``,
deterministically serialised so the same logical trip always hashes to the same SHA-256 —
the hash drives ``update()`` no-op detection and migration baseline reconciliation (ADR-21)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from src.optimizer.solver.models import (
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
    OptimizeResponse,
)
from src.trips.models import (
    SCHEMA_VERSION,
    MultiDayTripDetailOut,
    SaveTripRequest,
    SingleDayTripDetailOut,
    TripDetailOut,
)


@dataclass(frozen=True)
class SnapshotDisplayFields:
    """Write-time projection of the snapshot for cheap list queries (amends ADR-18)."""

    start_date: str
    end_date: str
    num_days: int


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_payload(request: SaveTripRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json", exclude={"expected_revision"})
    payload["schema_version"] = SCHEMA_VERSION
    return payload


def display_fields(payload: dict[str, Any]) -> SnapshotDisplayFields:
    if payload.get("plan_type") == "MULTI_DAY":
        dates = [str(day["date"]) for day in payload["multi_day_request"]["days"]]
        return SnapshotDisplayFields(start_date=min(dates), end_date=max(dates), num_days=len(dates))
    date = str(payload["date"])
    return SnapshotDisplayFields(start_date=date, end_date=date, num_days=1)


def build_snapshot(request: SaveTripRequest) -> tuple[str, str, SnapshotDisplayFields]:
    """``(canonical_json, sha256_hex, display_fields)`` — raises before any DB work if the
    request is not JSON-serialisable."""
    payload = snapshot_payload(request)
    canonical = canonical_json(payload)
    return canonical, snapshot_hash(canonical), display_fields(payload)


def load_snapshot(snapshot: str, compression: str = "none") -> dict[str, Any]:
    if compression != "none":
        raise ValueError(f"unsupported snapshot compression: {compression!r}")
    return json.loads(snapshot)


def detail_from_snapshot(
    trip_id: str,
    payload: dict[str, Any],
    *,
    revision: int,
    created_at: str,
    updated_at: str | None,
) -> TripDetailOut:
    """Re-validate a stored snapshot into the discriminated ``TripDetailOut`` response model."""
    if payload.get("plan_type") == "MULTI_DAY":
        request = MultiDayRequest.model_validate(payload["multi_day_request"])
        response = MultiDayResponse.model_validate(payload["multi_day_response"])
        dates = [day.date for day in request.days]
        return MultiDayTripDetailOut(
            id=trip_id,
            name=payload["name"],
            created_at=created_at,
            updated_at=updated_at,
            revision=revision,
            start_date=str(min(dates)),
            end_date=str(max(dates)),
            num_days=len(request.days),
            transport_mode=request.transport_mode,
            multi_day_request=request,
            multi_day_response=response,
        )

    request = OptimizeRequest.model_validate(payload["optimizer_request"])
    response = OptimizeResponse.model_validate(payload["optimizer_response"])
    return SingleDayTripDetailOut(
        id=trip_id,
        name=payload["name"],
        date=str(payload["date"]),
        created_at=created_at,
        updated_at=updated_at,
        revision=revision,
        optimizer_request=request,
        optimizer_response=response,
        selected_place_ids=request.place_ids,
        transport_mode=request.transport_mode,
        day_start_hour=request.day_start_hour,
        day_end_hour=request.day_end_hour,
    )
