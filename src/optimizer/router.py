from fastapi import APIRouter

from src.core.db.deps import MongoDbDep
from src.optimizer.deps import GoogleRoutesDep
from src.optimizer.matrix.cache import invalidate_cache
from src.optimizer.matrix.models import TransportMode

router = APIRouter()


@router.get("/matrix/status")
async def matrix_cache_status(db: MongoDbDep) -> dict:
    """Return the number of cached distance matrix entries per transport mode."""
    from src.core.db.manager import MATRIX_COLLECTION

    counts: dict[str, int] = {}
    for mode in TransportMode:
        counts[mode.value] = await db[MATRIX_COLLECTION].count_documents({"transport_mode": mode.value})
    return {"cache_entries": counts}


@router.delete("/matrix/cache", status_code=204)
async def clear_matrix_cache(db: MongoDbDep, transport_mode: TransportMode | None = None) -> None:
    """Invalidate cached distance matrix entries. Optionally filter by transport mode."""
    await invalidate_cache(db, transport_mode)


@router.get("/keycheck")
async def routes_keycheck(gr: GoogleRoutesDep) -> dict:
    """Check whether the Google Routes API key is configured."""
    api_key = gr.api_key
    return {
        "present": bool(api_key),
        "length": len(api_key),
        "last4": api_key[-4:] if api_key else None,
    }
