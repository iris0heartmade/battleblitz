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
        # One-shot migrations: SQLAlchemy create_all() doesn't add columns to
        # existing tables, so we ALTER TABLE for fields added after v1.
        await conn.run_sync(_run_legacy_migrations)
    logger.info("Database initialized: %s", engine.url.render_as_string(hide_password=True))


def _run_legacy_migrations(sync_conn) -> None:
    """Apply column-level migrations that create_all() can't."""
    from sqlalchemy import text
    # 2026-06-28: add games.map_biome
    # 2026-06-29: add games.phase
    rows = sync_conn.execute(text("PRAGMA table_info(games)")).fetchall()
    cols = {r[1] for r in rows}
    if "map_biome" not in cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN map_biome VARCHAR(16) NOT NULL DEFAULT 'grass'"
        ))
        logger.info("Migration: added games.map_biome")
    if "phase" not in cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN phase VARCHAR(16) NOT NULL DEFAULT 'player'"
        ))
        logger.info("Migration: added games.phase")
    # 2026-06-30: add units.matk and units.mdef for magic combat
    unit_rows = sync_conn.execute(text("PRAGMA table_info(units)")).fetchall()
    unit_cols = {r[1] for r in unit_rows}
    if "matk" not in unit_cols:
        sync_conn.execute(text(
            "ALTER TABLE units ADD COLUMN matk INTEGER NOT NULL DEFAULT 0"
        ))
        logger.info("Migration: added units.matk")
    if "mdef" not in unit_cols:
        sync_conn.execute(text(
            "ALTER TABLE units ADD COLUMN mdef INTEGER NOT NULL DEFAULT 0"
        ))
        logger.info("Migration: added units.mdef")
    # 2026-06-30: P0.4 — players.gold, tiles.subtype for the economy +
    # castle-sub-features feature. The `claim_sessions` table is created
    # by create_all() above (it's a new table, not an ALTER on existing).
    player_rows = sync_conn.execute(text("PRAGMA table_info(players)")).fetchall()
    player_cols = {r[1] for r in player_rows}
    if "gold" not in player_cols:
        sync_conn.execute(text(
            "ALTER TABLE players ADD COLUMN gold INTEGER NOT NULL DEFAULT 0"
        ))
        logger.info("Migration: added players.gold")
    tile_rows = sync_conn.execute(text("PRAGMA table_info(tiles)")).fetchall()
    tile_cols = {r[1] for r in tile_rows}
    if "subtype" not in tile_cols:
        sync_conn.execute(text(
            "ALTER TABLE tiles ADD COLUMN subtype VARCHAR(16)"
        ))
        logger.info("Migration: added tiles.subtype")
    # confirm claim_sessions table exists (create_all covers new games;
    # this handles existing DBs that were initialized before the table
    # was declared in models.py).
    cs_rows = sync_conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='claim_sessions'"
    )).fetchall()
    if not cs_rows:
        sync_conn.execute(text("""
            CREATE TABLE claim_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                tile_id INTEGER NOT NULL REFERENCES tiles(id) ON DELETE CASCADE,
                unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                target_player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                started_turn INTEGER NOT NULL,
                completes_turn INTEGER NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        sync_conn.execute(text(
            "CREATE INDEX ix_claim_sessions_game_id ON claim_sessions(game_id)"
        ))
        logger.info("Migration: created claim_sessions table")
    # 2026-06-30: P2.3 victory conditions + team mode.
    game_rows = sync_conn.execute(text("PRAGMA table_info(games)")).fetchall()
    game_cols = {r[1] for r in game_rows}
    if "win_condition" not in game_cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN win_condition VARCHAR(16) NOT NULL DEFAULT 'rout'"
        ))
        logger.info("Migration: added games.win_condition")
    if "reach_tile_id" not in game_cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN reach_tile_id INTEGER"
        ))
        logger.info("Migration: added games.reach_tile_id")
    if "defend_turns" not in game_cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN defend_turns INTEGER NOT NULL DEFAULT 10"
        ))
        logger.info("Migration: added games.defend_turns")
    if "win_reason" not in game_cols:
        sync_conn.execute(text(
            "ALTER TABLE games ADD COLUMN win_reason VARCHAR(32)"
        ))
        logger.info("Migration: added games.win_reason")
    player_rows = sync_conn.execute(text("PRAGMA table_info(players)")).fetchall()
    player_cols = {r[1] for r in player_rows}
    if "team_id" not in player_cols:
        sync_conn.execute(text(
            "ALTER TABLE players ADD COLUMN team_id VARCHAR(16)"
        ))
        logger.info("Migration: added players.team_id")


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