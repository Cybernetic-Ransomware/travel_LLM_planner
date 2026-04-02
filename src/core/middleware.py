import traceback
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.config.conf_logger import setup_logger
from src.core.exceptions import ErrorResponse

logger = setup_logger(__name__, "middleware")


def _format_validation_errors(errors: Sequence[Any]) -> str:
    """Convert Pydantic validation errors to a human-readable string."""
    parts = []
    for err in errors:
        loc = " → ".join(str(x) for x in err.get("loc", []) if x != "body")
        msg = err.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.error(
                "Unhandled exception for %s %s\n%s",
                request.method,
                request.url,
                traceback.format_exc(),
            )
            body = ErrorResponse(
                status_code=500,
                error="Internal Server Error",
                detail="An unexpected error occurred.",
            )
            return JSONResponse(status_code=500, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        try:
            error_phrase = HTTPStatus(exc.status_code).phrase
        except ValueError:
            error_phrase = "Unknown Error"

        body = ErrorResponse(
            status_code=exc.status_code,
            error=error_phrase,
            detail=str(exc.detail),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body = ErrorResponse(
            status_code=422,
            error="Unprocessable Entity",
            detail=_format_validation_errors(exc.errors()),
        )
        return JSONResponse(status_code=422, content=body.model_dump())
