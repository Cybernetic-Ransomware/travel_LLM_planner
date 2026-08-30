"""Server-authoritative write scope for orchestrator chat threads (ADR-20).

The router binds a thread on every normal turn, snapshots the scope into
``pending`` at the interrupt, and the write tool single-use consumes it on
resume; scope never comes from the confirmation request. The binding doc is
never deleted on the happy path — only ``pending`` is atomically cleared.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from src.core.db.manager import THREAD_TRIP_STATE_COLLECTION

BindingKind = Literal["trip", "place_selection"]


@dataclass(frozen=True)
class Binding:
    thread_id: str
    kind: BindingKind
    trip_id: str | None
    plan_type: str | None
    name: str | None
    revision: int | None
    allowed_place_ids: list[str]


@dataclass(frozen=True)
class PendingScope:
    tool_call_id: str
    kind: BindingKind
    trip_id: str | None
    plan_type: str | None
    name: str | None
    revision: int | None
    allowed_place_ids: list[str]


class TripSessionStateStore:
    def __init__(self, db: AsyncDatabase, retention_days: int = 30) -> None:
        self._collection = db[THREAD_TRIP_STATE_COLLECTION]
        self._retention_days = retention_days

    def _expiry(self) -> datetime:
        return datetime.now(UTC) + timedelta(days=self._retention_days)

    async def bind_trip(
        self,
        thread_id: str,
        trip_id: str,
        plan_type: str,
        name: str,
        revision: int,
        allowed_place_ids: list[str],
    ) -> None:
        """Bind a thread to a persisted trip for its whole life. Clears any stale ``pending``."""
        await self._collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "thread_id": thread_id,
                    "kind": "trip",
                    "trip_id": trip_id,
                    "plan_type": plan_type,
                    "name": name,
                    "revision": revision,
                    "allowed_place_ids": list(allowed_place_ids),
                    "pending": None,
                    "updated_at": datetime.now(UTC),
                    "expires_at": self._expiry(),
                }
            },
            upsert=True,
        )

    async def bind_place_selection(self, thread_id: str, allowed_place_ids: list[str]) -> None:
        """Bind a generic (non-trip) chat thread to its place selection. Clears any stale ``pending``."""
        await self._collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "thread_id": thread_id,
                    "kind": "place_selection",
                    "trip_id": None,
                    "plan_type": None,
                    "name": None,
                    "revision": None,
                    "allowed_place_ids": list(allowed_place_ids),
                    "pending": None,
                    "updated_at": datetime.now(UTC),
                    "expires_at": self._expiry(),
                }
            },
            upsert=True,
        )

    async def clear_binding(self, thread_id: str) -> None:
        """Remove the binding entirely. Not used on the normal flow — kept for completeness/tests."""
        await self._collection.delete_one({"thread_id": thread_id})

    async def get_binding(self, thread_id: str) -> Binding | None:
        doc = await self._collection.find_one({"thread_id": thread_id})
        if doc is None:
            return None
        return _binding_from_doc(doc)

    async def arm_pending(self, thread_id: str, tool_call_id: str) -> bool:
        """Snapshot the binding into ``pending`` at the interrupt; ``False`` = no trusted
        binding, so the caller must fail closed and not emit a proposal.
        """
        doc = await self._collection.find_one({"thread_id": thread_id})
        if doc is None:
            return False
        pending = {
            "tool_call_id": tool_call_id,
            "kind": doc.get("kind"),
            "trip_id": doc.get("trip_id"),
            "plan_type": doc.get("plan_type"),
            "name": doc.get("name"),
            "revision": doc.get("revision"),
            "allowed_place_ids": list(doc.get("allowed_place_ids", [])),
            "armed_at": datetime.now(UTC),
        }
        result = await self._collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"pending": pending, "updated_at": datetime.now(UTC), "expires_at": self._expiry()}},
        )
        return result.matched_count == 1

    async def consume_pending(self, thread_id: str) -> PendingScope | None:
        """Atomically read ``pending`` and clear it — single use. The binding doc stays."""
        doc = await self._collection.find_one_and_update(
            {"thread_id": thread_id, "pending": {"$ne": None}},
            {"$set": {"pending": None, "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.BEFORE,
        )
        if doc is None or doc.get("pending") is None:
            return None
        pending = doc["pending"]
        return PendingScope(
            tool_call_id=pending.get("tool_call_id", ""),
            kind=pending.get("kind"),
            trip_id=pending.get("trip_id"),
            plan_type=pending.get("plan_type"),
            name=pending.get("name"),
            revision=pending.get("revision"),
            allowed_place_ids=list(pending.get("allowed_place_ids", [])),
        )

    async def clear_pending(self, thread_id: str) -> None:
        await self._collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"pending": None, "updated_at": datetime.now(UTC)}},
        )


def _binding_from_doc(doc: dict) -> Binding:
    return Binding(
        thread_id=doc["thread_id"],
        kind=doc.get("kind", "place_selection"),
        trip_id=doc.get("trip_id"),
        plan_type=doc.get("plan_type"),
        name=doc.get("name"),
        revision=doc.get("revision"),
        allowed_place_ids=list(doc.get("allowed_place_ids", [])),
    )
