from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.core.db.manager import MongoDBManager
from src.core.turso.manager import TursoManager
from src.core.turso.migration_state import MigrationState
from src.gmaps import GooglePlacesManager
from src.optimizer.matrix.client import GoogleRoutesManager
from src.orchestrator.manager import OrchestratorManager
from src.trips.repository import TripRepository

logger = setup_logger(__name__, "main")


async def _shutdown(turso: TursoManager, mongo: MongoDBManager) -> None:
    """Best-effort teardown of the two raw connections, reached even when startup fails fast
    before ``yield`` (missing migration marker, schema error)."""
    try:
        await turso.disconnect()
        logger.info("Trips database disconnected")
    except Exception:
        logger.exception("Error disconnecting trips database")
    try:
        await mongo.disconnect()
        logger.info("MongoDB disconnected")
    except Exception:
        logger.exception("Error disconnecting MongoDB")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Started with DEBUG=%s", settings.debug)

    manager = MongoDBManager(settings.mongo_uri, settings.mongo_db, settings.mongo_pool_size)
    turso = TursoManager(settings.turso_database_url, settings.turso_auth_token)
    try:
        app.state.db = await manager.connect()
        app.state.client = manager.client
        logger.info("MongoDB connected — pool_size=%d db=%s", settings.mongo_pool_size, settings.mongo_db)

        # Persisted trips live in Turso, not MongoDB (ADR-21); startup only checks the Turso
        # migration marker and never reads the now-legacy Mongo `trips` collection.
        trip_db = await turso.connect()
        await turso.apply_schema()
        if settings.trips_require_migration_marker and not await MigrationState(trip_db).is_complete():
            raise RuntimeError(
                "Turso trip migration marker missing — run `just migrate-trips-to-turso` "
                "(it verifies the source and stamps the marker) before starting the app. "
                "Set TRIPS_REQUIRE_MIGRATION_MARKER=False only for local development."
            )
        app.state.trip_db = trip_db
        app.state.turso = turso
        trips_repo = TripRepository(trip_db)
        logger.info(
            "Trips database ready — backend=%s marker_required=%s",
            turso.backend,
            settings.trips_require_migration_marker,
        )

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
                        trips_repo=trips_repo,
                        places_manager=gp_manager,
                        routes_manager=gr_manager,
                        checkpoint_ttl_days=settings.checkpoint_ttl_days,
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
    finally:
        await _shutdown(turso, manager)
