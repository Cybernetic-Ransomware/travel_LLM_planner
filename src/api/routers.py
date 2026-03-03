from fastapi import APIRouter

from src.api.exceptions import EndpointUnimplementedException
from src.core import gmaps_router

router = APIRouter()
router.include_router(gmaps_router, prefix="/core/gmaps", tags=["core", "gmaps"])


@router.get("/", include_in_schema=False)
async def healthcheck():
    raise EndpointUnimplementedException(message="Router's Healthcheck not implemented")
