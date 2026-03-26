from __future__ import annotations

from datetime import datetime
from enum import StrEnum


class TransportMode(StrEnum):
    WALK = "WALK"
    DRIVE = "DRIVE"
    BICYCLE = "BICYCLE"
    TRANSIT = "TRANSIT"


class MatrixEntry:
    """Travel cost between one origin and one destination."""

    __slots__ = ("origin_id", "dest_id", "distance_m", "duration_s")

    def __init__(self, origin_id: str, dest_id: str, distance_m: int, duration_s: int) -> None:
        self.origin_id = origin_id
        self.dest_id = dest_id
        self.distance_m = distance_m
        self.duration_s = duration_s

    def __repr__(self) -> str:
        return f"MatrixEntry({self.origin_id!r} → {self.dest_id!r}, {self.duration_s}s, {self.distance_m}m)"


class DistanceMatrix:
    """Lookup table for travel costs between all pairs of places.

    Keyed by (origin_id, dest_id) tuples for O(1) access.
    """

    def __init__(
        self,
        entries: dict[tuple[str, str], MatrixEntry],
        transport_mode: TransportMode,
        computed_at: datetime,
    ) -> None:
        self._entries = entries
        self.transport_mode = transport_mode
        self.computed_at = computed_at

    def get(self, origin_id: str, dest_id: str) -> MatrixEntry | None:
        """Return the entry for the given pair, or None if not available."""
        return self._entries.get((origin_id, dest_id))

    def duration_s(self, origin_id: str, dest_id: str) -> int:
        """Return travel time in seconds. Raises KeyError if the pair is missing."""
        entry = self._entries[(origin_id, dest_id)]
        return entry.duration_s

    def distance_m(self, origin_id: str, dest_id: str) -> int:
        """Return distance in metres. Raises KeyError if the pair is missing."""
        entry = self._entries[(origin_id, dest_id)]
        return entry.distance_m

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"DistanceMatrix(mode={self.transport_mode}, entries={len(self._entries)})"
