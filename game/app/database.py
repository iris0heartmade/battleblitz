"""
Async SQLAlchemy engine, session factory and table-creation helper.

Single source of truth for DB connection. Routes import `get_session` as a
FastAPI dependency and call `init_db` once at app startup.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import APP_TITLE, DEFAULT_DB_PATH

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _build_database_url(path: str) -> str:
    """Convert a filesystem path to an aiosqlite URL, ensuring the dir exists."""
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


# Module-level engine & sessionmaker. Created at import time so tests can
# override via env var DATABASE_URL before importing.
_DATABASE_URL = os.getenv("DATABASE_URL") or _build_database_url(DEFAULT_DB_PATH)

engine: AsyncEngine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    future=True,
    # SQLite single-writer: allow connection sharing across greenlets
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Create all tables. Safe to call on every startup."""
    # Import models so they register with Base.metadata before create_all.
    from app import models  # noqa: F401
    from app.progression import models as _progression_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized: %s", engine.url.render_as_string(hide_password=True))


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Programmatic session (for background tasks and game_logic helpers)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_db() -> None:
    """Cleanly dispose of the engine on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed")


__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_session",
    "init_db",
    "dispose_db",
    "session_scope",
    "APP_TITLE",
]