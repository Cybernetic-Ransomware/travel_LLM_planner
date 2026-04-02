from fastapi import APIRouter

from src.core import gmaps_router, optimizer_router, orchestrator_router
from src.core.exceptions import EndpointUnimplementedException

router = APIRouter()
router.include_router(gmaps_router, prefix="/core/gmaps", tags=["core", "gmaps"])
router.include_router(optimizer_router, prefix="/core/optimizer", tags=["core", "optimizer"])
router.include_router(orchestrator_router, prefix="/core/orchestrator", tags=["core", "orchestrator"])


@router.get("/", include_in_schema=False)
async def healthcheck():
    raise EndpointUnimplementedException(message="Router's Healthcheck not implemented")
