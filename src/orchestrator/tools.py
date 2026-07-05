from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from src.config.conf_logger import setup_logger
from src.gmaps import GooglePlacesManager, PlaceCreate, PlacePatch, find_and_update_place, insert_place
from src.trips.manager import TripsManager

logger = setup_logger(__name__, "orchestrator")


def create_tools(db: AsyncDatabase, places_manager: GooglePlacesManager | None = None) -> list:
    """Return the list of LLM-callable tools with the database connection closure-bound.

    Each tool reads ``allowed_place_ids`` from ``config["configurable"]`` at runtime to
    enforce that only places belonging to the current session can be modified.

    When ``places_manager`` is provided, a ``search_place`` tool is included that
    resolves place names via the Google Places API without writing to the database.
    """

    def _extract_allowed(config: RunnableConfig | None) -> list[str]:
        configurable: dict = {}
        if config is not None:
            if isinstance(config, dict):
                configurable = config.get("configurable") or {}
            else:
                logger.warning("Tool config is not a dict (got %s); allowed_place_ids defaults to []", type(config))
        return configurable.get("allowed_place_ids", [])

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
        allowed = _extract_allowed(config)
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

    @tool
    async def skip_place(
        place_id: str,
        skipped: bool,
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects RunnableConfig by exact type match; RunnableConfig | None breaks injection
    ) -> str:
        """Skip or un-skip a place in the trip plan.

        Use this tool when the user wants to remove a place from or restore a place to
        their active trip plan. Skipping is reversible — a skipped place can be un-skipped.
        Only places that are part of the current trip plan can be modified.

        Args:
            place_id: MongoDB ObjectId string of the place.
            skipped: True to skip (remove from active plan), False to un-skip (restore).
        """
        allowed = _extract_allowed(config)
        if allowed and place_id not in allowed:
            return f"Cannot update place '{place_id}': it is not part of the current trip plan."

        try:
            patch = PlacePatch(skipped=skipped)
        except ValidationError as exc:
            first_error = exc.errors()[0]["msg"] if exc.errors() else str(exc)
            return f"Invalid input: {first_error}"

        try:
            updated = await find_and_update_place(db, place_id, patch)
        except Exception as exc:
            return f"Failed to update place: {exc}"

        if updated is None:
            return f"Place '{place_id}' not found."

        name = updated.get("name") or place_id
        if skipped:
            return f"Skipped '{name}'."
        return f"Restored '{name}' to the plan."

    @tool
    async def add_place(
        name: str,
        address: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        visit_duration_min: int | None = None,
        preferred_hour_from: int | None = None,
        preferred_hour_to: int | None = None,
        config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects RunnableConfig by exact type match; RunnableConfig | None breaks injection
    ) -> str:
        """Add a new place to the trip plan.

        Use this tool when the user wants to add a place that is not currently in their
        plan. The place will be created as a new document in the database. Consider using
        search_place first to verify the place exists and obtain accurate coordinates.

        Args:
            name: Name of the place (required).
            address: Street address or location description.
            lat: Latitude coordinate.
            lng: Longitude coordinate.
            visit_duration_min: Estimated minutes to spend at the place (positive integer).
            preferred_hour_from: Earliest preferred local hour to visit (0-23, inclusive).
            preferred_hour_to: Latest preferred local hour to visit (0-23, inclusive,
                must be greater than preferred_hour_from).
        """
        try:
            place_create = PlaceCreate(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                visit_duration_min=visit_duration_min,
                preferred_hour_from=preferred_hour_from,
                preferred_hour_to=preferred_hour_to,
            )
        except ValidationError as exc:
            first_error = exc.errors()[0]["msg"] if exc.errors() else str(exc)
            return f"Invalid place data: {first_error}"

        try:
            inserted = await insert_place(db, place_create)
        except Exception as exc:
            return f"Failed to add place: {exc}"

        new_id = str(inserted.get("_id", ""))
        return f"Added '{name}' to the plan (id={new_id})."

    tools: list = [update_visit_hours, skip_place, add_place]

    trips_manager = TripsManager(db)

    @tool
    async def list_saved_trips() -> str:
        """List all saved trips by name and date.

        Use this tool when the user asks what trips they have saved, wants to browse
        their saved trips, or mentions a trip by name and you need to find its ID.
        Returns trip IDs that can be passed to get_trip_details.
        """
        try:
            trips = await trips_manager.list_all()
        except Exception as exc:
            return f"Failed to retrieve trips: {exc}"
        if not trips:
            return "No saved trips found."
        lines = [f"- id={t.id}, name='{t.name}', date={t.date}" for t in trips]
        return "Saved trips:\n" + "\n".join(lines)

    @tool
    async def get_trip_details(trip_id: str) -> str:
        """Get the full details of a saved trip including all places and route.

        Use this tool to retrieve complete information about a specific trip:
        transport mode, time window, ordered place list with arrival/departure times,
        visit durations, and any skipped places.

        Args:
            trip_id: MongoDB ObjectId string of the trip (from list_saved_trips).
        """
        try:
            trip = await trips_manager.find_by_id(trip_id)
        except Exception as exc:
            return f"Failed to retrieve trip: {exc}"
        if trip is None:
            return f"Trip '{trip_id}' not found."

        header = (
            f"Trip '{trip.name}' ({trip.date})\n"
            f"Transport: {trip.transport_mode.value}, window: "
            f"{trip.day_start_hour}:00–{trip.day_end_hour}:00\n"
        )

        steps = trip.optimizer_response.steps
        if not steps:
            return header + "No places in route."

        place_lines = []
        for i, step in enumerate(steps, 1):
            travel = f", {step.travel_from_previous_s // 60} min travel" if step.travel_from_previous_s else ""
            place_lines.append(
                f"{i}. {step.name or step.place_id} — "
                f"arrive {step.arrival_time.strftime('%H:%M')}, "
                f"depart {step.departure_time.strftime('%H:%M')}, "
                f"{step.visit_duration_min} min visit{travel}"
            )

        resp = trip.optimizer_response
        skipped_section = "Skipped: none"
        if resp.skipped:
            names = [s.name or s.place_id for s in resp.skipped]
            skipped_section = "Skipped: " + ", ".join(names)

        summary = (
            f"Total: {resp.total_travel_time_s // 60} min travel, "
            f"{resp.total_visit_time_min} min visits, "
            f"{resp.total_wait_min} min wait"
        )

        return header + "\n".join(place_lines) + "\n" + summary + "\n" + skipped_section

    tools.append(list_saved_trips)
    tools.append(get_trip_details)

    if places_manager is not None:

        @tool
        async def search_place(
            query: str,
            lat: float | None = None,
            lng: float | None = None,
            config: RunnableConfig = None,  # type: ignore[assignment]  # LangChain injects RunnableConfig by exact type match; RunnableConfig | None breaks injection
        ) -> str:
            """Search for a place by name using the Google Places API.

            Use this tool to verify that a place exists and retrieve its accurate name,
            address, and coordinates before adding it with add_place. Does not modify
            the database.

            Args:
                query: Name or description of the place to search for.
                lat: Optional latitude for location bias (narrows search to nearby results).
                lng: Optional longitude for location bias (narrows search to nearby results).
            """
            place_id, status, error = await places_manager.search_place_id(query, lat, lng)
            if status == "MISSING_API_KEY":
                return "Google Places search is not available: API key not configured."
            if status == "NOT_FOUND":
                return f"No place found matching '{query}'."
            if status != "OK" or not place_id:
                return f"Search failed: {error or status}."

            payload, detail_status, detail_error = await places_manager.fetch_place_details(place_id)
            if detail_status != "OK" or payload is None:
                return f"Found a match but could not retrieve details: {detail_error or detail_status}."

            display_name = payload.get("displayName", {}).get("text") or query
            formatted_address = payload.get("formattedAddress", "")
            location = payload.get("location") or {}
            result_lat = location.get("latitude")
            result_lng = location.get("longitude")

            parts = [f"Found '{display_name}'"]
            if formatted_address:
                parts.append(f"at {formatted_address}")
            if result_lat is not None and result_lng is not None:
                parts.append(f"(lat={result_lat}, lng={result_lng})")
            parts.append(f"gmaps_id={place_id}")
            return ", ".join(parts) + "."

        tools.append(search_place)

    return tools
