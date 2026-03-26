from typing import Annotated

from fastapi import Depends, Request

from src.optimizer.matrix.client import GoogleRoutesManager


def get_google_routes(request: Request) -> GoogleRoutesManager:
    """FastAPI dependency — returns the shared GoogleRoutesManager from app state."""
    return request.app.state.google_routes


GoogleRoutesDep = Annotated[GoogleRoutesManager, Depends(get_google_routes)]
