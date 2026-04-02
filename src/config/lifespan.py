from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.core.db.manager import MongoDBManager
from src.gmaps.manager import GooglePlacesManager
from src.optimizer.matrix.client import GoogleRoutesManager
from src.orchestrator.manager import OrchestratorManager

logger = setup_logger(__name__, "main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Started with DEBUG=%s", settings.debug)

    manager = MongoDBManager(settings.mongo_uri, settings.mongo_db, settings.mongo_pool_size)
    app.state.db = await manager.connect()
    app.state.client = manager.client
    logger.info("MongoDB connected — pool_size=%d db=%s", settings.mongo_pool_size, settings.mongo_db)

    async with GooglePlacesManager(settings.google_places_api_key, settings.google_places_fields) as gp_manager:
        app.state.google_places = gp_manager
        logger.info("GooglePlacesManager connected — key_present=%s", bool(settings.google_places_api_key))

        async with GoogleRoutesManager(settings.google_routes_api_key) as gr_manager:
            app.state.google_routes = gr_manager
            logger.info("GoogleRoutesManager connected — key_present=%s", bool(settings.google_routes_api_key))

            llm_key = settings.openai_api_key if settings.llm_provider == "openai" else settings.anthropic_api_key
            if llm_key:
                async with OrchestratorManager(
                    provider=settings.llm_provider,
                    api_key=llm_key,
                    model_name=settings.llm_model_name,
                    langsmith_api_key=settings.langsmith_api_key,
                    langsmith_tracing=settings.langsmith_tracing,
                    langsmith_project=settings.langsmith_project,
                    db=app.state.db,
                ) as orch_manager:
                    app.state.orchestrator = orch_manager
                    logger.info(
                        "OrchestratorManager connected — provider=%s model=%s",
                        settings.llm_provider,
                        settings.llm_model_name,
                    )
                    yield
                logger.info("OrchestratorManager disconnected")
            else:
                app.state.orchestrator = None
                logger.warning(
                    "OrchestratorManager skipped — no API key for provider=%s",
                    settings.llm_provider,
                )
                yield

    logger.info("GooglePlacesManager disconnected")
    logger.info("GoogleRoutesManager disconnected")

    await manager.disconnect()
    logger.info("MongoDB disconnected")
