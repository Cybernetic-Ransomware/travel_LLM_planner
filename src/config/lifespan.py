from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.core.db.manager import MongoDBManager

logger = setup_logger(__name__, "main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Started with DEBUG=%s", settings.debug)

    manager = MongoDBManager(settings.mongo_uri, settings.mongo_db, settings.mongo_pool_size)
    app.state.db = await manager.connect()
    logger.info("MongoDB connected — pool_size=%d db=%s", settings.mongo_pool_size, settings.mongo_db)

    yield

    await manager.disconnect()
    logger.info("MongoDB disconnected")
