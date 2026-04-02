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


class OrchestratorUnavailableError(HTTPException):
    """Raised when the LLM orchestrator is not initialised (no API key configured)."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            status_code=503,
            detail=f"Orchestrator not available — configure LLM_PROVIDER and the {provider} API key.",
        )
