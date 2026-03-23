from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.core.db.manager import MongoDBManager
from src.gmaps.manager import GooglePlacesManager

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

        yield

    logger.info("GooglePlacesManager disconnected")

    await manager.disconnect()
    logger.info("MongoDB disconnected")
