from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from src.gmaps import PlacePatch, find_and_update_place


def create_tools(db: AsyncDatabase) -> list:
    """Return the list of LLM-callable tools with the database connection closure-bound.

    Each tool reads ``allowed_place_ids`` from ``config["configurable"]`` at runtime to
    enforce that only places belonging to the current session can be modified.
    """

    @tool
    async def update_visit_hours(
        place_id: str,
        preferred_hour_from: int | None = None,
        preferred_hour_to: int | None = None,
        visit_duration_min: int | None = None,
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects RunnableConfig by exact type match; RunnableConfig | None breaks injection
    ) -> str:
        """Update the preferred visit window or visit duration for a place in the trip plan.

        Use this tool when the user explicitly confirms they want to change the visiting
        time window or visit duration for a specific place. Only places that are part of
        the current trip plan (present in place_context) can be modified.

        Args:
            place_id: MongoDB ObjectId string of the place to update.
            preferred_hour_from: Earliest preferred local hour to visit (0-23, inclusive).
            preferred_hour_to: Latest preferred local hour to visit (0-23, inclusive,
                must be greater than preferred_hour_from).
            visit_duration_min: Estimated minutes to spend at the place (positive integer).
        """
        configurable: dict = {}
        if config is not None:
            configurable = (config.get("configurable") or {}) if isinstance(config, dict) else {}
        allowed: list[str] = configurable.get("allowed_place_ids", [])

        if allowed and place_id not in allowed:
            return f"Cannot update place '{place_id}': it is not part of the current trip plan."

        try:
            patch = PlacePatch(
                preferred_hour_from=preferred_hour_from,
                preferred_hour_to=preferred_hour_to,
                visit_duration_min=visit_duration_min,
            )
        except ValidationError as exc:
            first_error = exc.errors()[0]["msg"] if exc.errors() else str(exc)
            return f"Invalid visit hours: {first_error}"

        try:
            updated = await find_and_update_place(db, place_id, patch)
        except Exception as exc:
            return f"Failed to update place: {exc}"

        if updated is None:
            return f"Place '{place_id}' not found."

        name = updated.get("name") or place_id
        parts: list[str] = []
        h_from = updated.get("preferred_hour_from")
        h_to = updated.get("preferred_hour_to")
        if h_from is not None and h_to is not None:
            parts.append(f"visit window {h_from}:00\u2013{h_to}:00")
        dur = updated.get("visit_duration_min")
        if dur is not None:
            parts.append(f"{dur} min visit duration")
        detail = ", ".join(parts) if parts else "preferences updated"
        return f"Updated '{name}': {detail}."

    return [update_visit_hours]
