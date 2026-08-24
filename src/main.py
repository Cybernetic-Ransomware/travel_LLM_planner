from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.config.lifespan import lifespan
from src.core.middleware import ExceptionHandlerMiddleware, register_exception_handlers
from src.core.routers import router as api_router

logger = setup_logger(__name__, "main")

app = FastAPI(title="Travel Planner API", lifespan=lifespan)

app.add_middleware(ExceptionHandlerMiddleware)  # type: ignore[arg-type]
# Added last so CORS wraps the exception middleware and error responses keep CORS headers.
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "PATCH", "POST", "DELETE"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1", tags=["api"])


@app.get("/")
async def healthcheck():
    logger.info("Called first healthcheck")
    return {"status": "OK"}
