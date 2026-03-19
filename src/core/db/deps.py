from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def get_db(request: Request) -> AsyncDatabase:
    """FastAPI dependency — returns the shared PyMongo async database from app state."""
    return request.app.state.db


def get_client(request: Request) -> AsyncMongoClient:
    """FastAPI dependency — returns the shared PyMongo async client from app state."""
    return request.app.state.client


MongoDbDep = Annotated[AsyncDatabase, Depends(get_db)]
MongoClientDep = Annotated[AsyncMongoClient, Depends(get_client)]


@asynccontextmanager
async def mongo_session(client: AsyncMongoClient):
    """Context manager that provides a client session for causally consistent reads/writes."""
    async with client.start_session() as session:
        yield session


@asynccontextmanager
async def mongo_transaction(client: AsyncMongoClient):
    """Context manager that wraps a session in a transaction (requires Replica Set or Sharded Cluster)."""
    async with client.start_session() as session, await session.start_transaction():
        yield session
