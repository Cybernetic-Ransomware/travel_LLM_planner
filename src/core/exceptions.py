from fastapi import HTTPException
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    status_code: int
    error: str
    detail: str


class EndpointUnimplementedException(HTTPException):
    def __init__(self, message: str = ""):
        super().__init__(status_code=501, detail=f"Endpoint not implemented: {message}")


class EndpointUnexpectedException(HTTPException):
    def __init__(self, message: str = ""):
        super().__init__(status_code=500, detail=f"Unexpected Endpoint Error: {message}")


class MatrixUnavailableError(HTTPException):
    """Raised when the Google Routes distance matrix cannot be obtained."""

    def __init__(self, status: str, error: str | None = None) -> None:
        detail = f"Distance matrix unavailable: {status}"
        if error:
            detail += f" — {error}"
        super().__init__(status_code=502, detail=detail)


class PlaceResolutionError(HTTPException):
    """Raised when Google Places cannot locate a place during single-place enrichment."""

    def __init__(self, status: str | None, error: str | None = None) -> None:
        detail = f"Google Places could not resolve this location: {status or 'NOT_FOUND'}"
        if error:
            detail += f" — {error}"
        super().__init__(status_code=502, detail=detail)


class InvalidHourRangeError(HTTPException):
    """Raised when a partial patch would leave a place with preferred_hour_from >= preferred_hour_to."""

    def __init__(self) -> None:
        super().__init__(status_code=422, detail="preferred_hour_from must be less than preferred_hour_to")


class OrchestratorUnavailableError(HTTPException):
    """Raised when the LLM orchestrator is not initialised (no API key configured)."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            status_code=503,
            detail=f"Orchestrator not available — configure LLM_PROVIDER and the {provider} API key.",
        )


class TripPlanTypeConflictError(HTTPException):
    """Raised when an update would change a trip's plan_type (e.g. SINGLE_DAY -> MULTI_DAY)."""

    def __init__(self, trip_id: str, existing_plan_type: str, requested_plan_type: str) -> None:
        detail = (
            f"Trip {trip_id!r} is a {existing_plan_type} trip; cannot change plan_type to {requested_plan_type} via update"
        )
        super().__init__(status_code=409, detail=detail)


class TripConcurrencyConflictError(HTTPException):
    """Raised when a trip update's expected_revision no longer matches the stored revision."""

    def __init__(self, trip_id: str, expected: int) -> None:
        super().__init__(
            status_code=409,
            detail=(
                f"Trip {trip_id!r} changed since it was loaded (expected revision {expected}); "
                "reload the trip and retry the update"
            ),
        )


class MissingExpectedRevisionError(HTTPException):
    """Raised when a trip update omits expected_revision — updates must carry the concurrency token."""

    def __init__(self, trip_id: str) -> None:
        super().__init__(
            status_code=428,
            detail=f"Updating trip {trip_id!r} requires expected_revision; reload the trip and retry",
        )


class AuthenticationError(HTTPException):
    """Raised when the JWT token is missing, malformed, or fails RS256 verification."""

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(
            status_code=401,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
