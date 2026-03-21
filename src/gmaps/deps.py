from typing import Annotated

from fastapi import Depends, Request

from src.gmaps.manager import GooglePlacesManager


def get_google_places(request: Request) -> GooglePlacesManager:
    """FastAPI dependency — returns the shared GooglePlacesManager from app state."""
    return request.app.state.google_places


GooglePlacesDep = Annotated[GooglePlacesManager, Depends(get_google_places)]
