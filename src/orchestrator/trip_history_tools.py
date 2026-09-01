"""Revision-history tools for the active bound trip (ADR-21).

``list_trip_revisions`` is read-only — it reads the trusted ``binding``, never the single-use
``pending`` scope. ``revert_trip_revision`` is a write and reuses the whole ADR-20 gate
unchanged: the LLM supplies only ``target_revision``, scoped to this trip and CAS-guarded by
``scope.revision``. The optimizer is never invoked.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from src.config.conf_logger import setup_logger
from src.core.exceptions import (
    RevisionAlreadyCurrentError,
    RevisionNotFoundError,
    TripConcurrencyConflictError,
    TripNotFoundError,
)
from src.orchestrator.trip_session_state import TripSessionStateStore
from src.trips.repository import TripRepository

logger = setup_logger(__name__, "orchestrator")

_NO_TRIP = "This chat isn't editing a saved trip, so there's no revision history to show."
_SCOPE_EXPIRED = "I can't confirm this change — the trip context for this proposal expired. Re-open the trip and ask again."
_CONFLICT = "This trip changed since we started; nothing was restored. Ask me to re-read it and try again."


def _thread_id(config: RunnableConfig | None) -> str | None:
    if isinstance(config, dict):
        return (config.get("configurable") or {}).get("thread_id")
    return None


def build_list_trip_revisions_tool(trips_repo: TripRepository, session_state_store: TripSessionStateStore):
    @tool
    async def list_trip_revisions(
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects by exact RunnableConfig type
    ) -> str:
        """List the saved revision history of the trip this chat is editing.

        Use this when the user asks what changed, which revisions exist, or wants to go
        back to an earlier version. Returns each revision's number, where it came from,
        when it was recorded, and a short summary — newest first. Takes no arguments.
        """
        thread_id = _thread_id(config)
        if not thread_id:
            return _NO_TRIP

        binding = await session_state_store.get_binding(thread_id)
        if binding is None or binding.kind != "trip" or binding.trip_id is None:
            return _NO_TRIP

        data = await trips_repo.list_revisions(binding.trip_id)
        if data is None or not data.revisions:
            return _NO_TRIP

        lines = [f"Revision history for '{binding.name}':"]
        for rev in data.revisions:
            marker = " (current)" if rev.revision == data.current_revision else ""
            recorded = rev.recorded_at[:16].replace("T", " ")
            restored = (
                f" [restored from revision {rev.restored_from_revision}]" if rev.restored_from_revision is not None else ""
            )
            lines.append(f"- revision {rev.revision}{marker} — {rev.source} — {recorded} — {rev.summary}{restored}")
        return "\n".join(lines)

    return list_trip_revisions


def build_revert_trip_revision_tool(trips_repo: TripRepository, session_state_store: TripSessionStateStore):
    @tool
    async def revert_trip_revision(
        target_revision: int,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects by exact RunnableConfig type
    ) -> str | Command:
        """Restore the saved trip this chat is editing to an earlier revision.

        Describe the target revision and get the user's explicit confirmation first. This
        creates a new higher revision that copies the target's saved plan exactly; it does
        not re-run the optimizer, and nothing is deleted. Never pass a trip id — the trip is
        fixed by the chat context.

        Args:
            target_revision: The revision number to restore (from list_trip_revisions).
        """
        thread_id = _thread_id(config)
        if not thread_id:
            return _SCOPE_EXPIRED

        scope = await session_state_store.consume_pending(thread_id)
        if scope is None or scope.kind != "trip" or scope.trip_id is None or scope.revision is None:
            return _SCOPE_EXPIRED
        if scope.tool_call_id and tool_call_id and scope.tool_call_id != tool_call_id:
            return _SCOPE_EXPIRED

        try:
            result = await trips_repo.restore_revision(scope.trip_id, target_revision, expected_revision=scope.revision)
        except TripConcurrencyConflictError:
            return _CONFLICT
        except RevisionNotFoundError:
            return f"There's no revision {target_revision} to restore."
        except RevisionAlreadyCurrentError:
            return f"Revision {target_revision} is already the current state — nothing to restore."
        except TripNotFoundError:
            return "I couldn't find that trip anymore; nothing was restored."
        except Exception:
            logger.exception(
                "Unexpected failure reverting trip thread_id=%s trip_id=%s target=%s",
                thread_id,
                scope.trip_id,
                target_revision,
            )
            return "Something went wrong restoring that revision; nothing was saved."

        message = (
            f"Restored '{result.name}' to the state from revision {target_revision}; it's now revision {result.revision}."
        )
        return Command(
            update={
                "messages": [ToolMessage(content=message, tool_call_id=tool_call_id)],
                "last_trip_update": {
                    "trip_id": result.id,
                    "revision": result.revision,
                    "plan_type": result.plan_type,
                    "name": result.name,
                },
            }
        )

    return revert_trip_revision
