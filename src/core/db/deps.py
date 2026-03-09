from typing import Annotated

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase


def get_db(request: Request) -> AsyncIOMotorDatabase:
    """FastAPI dependency — returns the shared Motor database from app state."""
    return request.app.state.db


MongoDbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
