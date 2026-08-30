"""The single LLM-facing write path for a persisted MULTI_DAY trip.

The tool takes no ``trip_id`` argument — the target comes only from the
server-side ``pending`` scope snapshotted at the interrupt and consumed here
exactly once. Any smuggled ``trip_id``-like key in ``operations`` is rejected
by ``TripEditBatch``'s ``extra="forbid"``.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from src.config.conf_logger import setup_logger
from src.optimizer.matrix.client import GoogleRoutesManager
from src.orchestrator.trip_session_state import TripSessionStateStore
from src.trips.editing.errors import TripEditError
from src.trips.editing.operations import TripEditBatch, TripEditOperation
from src.trips.editing.service import MultiDayTripEditor
from src.trips.manager import TripsManager

logger = setup_logger(__name__, "orchestrator")

_SCOPE_EXPIRED = "I can't confirm this change — the trip context for this proposal expired. Re-open the trip and ask again."


def build_edit_multi_day_trip_tool(
    db: AsyncDatabase,
    routes_manager: GoogleRoutesManager,
    session_state_store: TripSessionStateStore,
):
    @tool
    async def edit_multi_day_trip(
        operations: list[TripEditOperation],
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects by exact RunnableConfig type
    ) -> str | Command:
        """Apply a batch of typed changes to the saved multi-day trip this chat is editing.

        Use one call with an ``operations`` list for a multi-step change (e.g. pin a
        place to a day *and* shift that day's window). Describe the change and get the
        user's explicit confirmation before calling this. The trip is reloaded, the
        operations applied, the plan re-optimized, and the result saved atomically —
        or nothing is saved. Never pass a trip id; the trip is fixed by the chat context.
        """
        configurable = (config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            return _SCOPE_EXPIRED

        scope = await session_state_store.consume_pending(thread_id)
        if scope is None or scope.kind != "trip" or scope.trip_id is None or scope.revision is None:
            return _SCOPE_EXPIRED
        # Defense-in-depth: the armed scope names the tool call it was snapshotted for.
        if scope.tool_call_id and tool_call_id and scope.tool_call_id != tool_call_id:
            return _SCOPE_EXPIRED

        try:
            batch = TripEditBatch(operations=operations)
        except ValidationError as exc:
            first = exc.errors()[0]["msg"] if exc.errors() else "invalid operation"
            return f"That change isn't valid: {first}"

        editor = MultiDayTripEditor(db, TripsManager(db), routes_manager)
        try:
            updated = await editor.apply(scope.trip_id, batch.operations, scope.revision)
        except TripEditError as exc:
            return exc.user_message
        except Exception:
            logger.exception("Unexpected failure applying trip edit thread_id=%s trip_id=%s", thread_id, scope.trip_id)
            return "Something went wrong applying the trip changes; nothing was saved."

        summary = _summarize(updated.name, len(batch.operations))
        return Command(
            update={
                "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
                "last_trip_update": {
                    "trip_id": updated.id,
                    "revision": updated.revision,
                    "plan_type": "MULTI_DAY",
                    "name": updated.name,
                },
            }
        )

    return edit_multi_day_trip


def _summarize(name: str, change_count: int) -> str:
    plural = "change" if change_count == 1 else "changes"
    return f"Updated '{name}'. {change_count} {plural} applied; the day plan was recomputed."
