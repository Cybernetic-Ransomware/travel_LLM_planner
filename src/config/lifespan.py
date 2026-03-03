from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.conf_logger import setup_logger
from src.config.config import settings

logger = setup_logger(__name__, "main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"DEBUG={settings.debug}", flush=True)
    logger.info("Started with DEBUG=%s", settings.debug)
    yield  # Separates code before the application starts and after it stops
    # ___ Any code to clean up resources after the application stops
