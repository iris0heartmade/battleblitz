"""
Shared pytest fixtures for BattleBlitz.

The trickiest part of testing this app is that `app.database` builds the
async engine at *import time* (so tests can't trivially swap the URL).
We work around that by setting `DATABASE_URL` env var before any
`app.*` import happens, via the `pytest_configure` hook below.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure `game/` is on sys.path when pytest is launched from elsewhere.
_GAME_ROOT = Path(__file__).resolve().parent
if str(_GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(_GAME_ROOT))

# Point the DB at a per-session file inside the temp dir BEFORE any
# `app.*` import.  This has to happen at collection time (not inside a
# fixture) because `app.database` reads the env var at import.
import tempfile
_TMPDIR = tempfile.mkdtemp(prefix="bb_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMPDIR}/test.db"
# Force the logging config to skip creating timestamped files for tests.
os.environ.setdefault("BB_LOG_DIR", os.path.join(_TMPDIR, "logs"))


import pytest  # noqa: E402


# ============================================================
# Async / DB fixtures
# ============================================================

@pytest.fixture
def tmp_db_path(tmp_path) -> str:
    """Per-test DB file path. Useful when a test needs its own engine."""
    return str(tmp_path / "fresh.db")


@pytest.fixture
async def db_session():
    """Provide a clean async session with all tables created and torn down.

    Each test gets a fresh DB file. Uses the engine that `app.database`
    built at import time (pointed at the tmp file via env var).
    """
    from app import models  # noqa: F401  (register models with Base)
    from app.database import AsyncSessionLocal, Base, engine, init_db

    await init_db()
    async with AsyncSessionLocal() as session:
        yield session
    # Drop everything for the next test.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ============================================================
# HTTP client fixture (ASGI in-process)
# ============================================================

@pytest.fixture
async def client():
    """ASGI httpx client against the FastAPI app — no network required.

    Runs the FastAPI lifespan so init_db() / scheduler startup happen
    (ASGITransport does NOT auto-trigger lifespan events).
    """
    from httpx import ASGITransport, AsyncClient
    from contextlib import asynccontextmanager

    from app.main import app
    from app.database import init_db, dispose_db

    await init_db()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        await dispose_db()


# ============================================================
# Convenience builders for game fixtures
# ============================================================

@pytest.fixture
async def waiting_game(db_session):
    """A freshly created game with 2 human players, not yet started."""
    from app.models import Game, Player

    game = Game(name="Test Lobby", status="waiting", map_seed=42)
    db_session.add(game)
    await db_session.flush()
    db_session.add_all([
        Player(game_id=game.id, user_name="alice", color="red", seat=0),
        Player(game_id=game.id, user_name="bob", color="blue", seat=1),
    ])
    await db_session.flush()
    return game


@pytest.fixture
async def playing_game(db_session):
    """A started game with tiles + units spawned — ready for actions."""
    from app.models import ActionLog, Game, Player

    from app.game_logic import (
        castle_positions,
        create_initial_units_with_roster,
        generate_map_preset,
        get_roster_for_composition,
    )

    game = Game(
        name="Test Match", status="playing",
        map_seed=123, map_preset="classic", unit_composition="classic",
    )
    db_session.add(game)
    await db_session.flush()

    players = [
        Player(game_id=game.id, user_name="p1", color="red", seat=0),
        Player(game_id=game.id, user_name="p2", color="blue", seat=1),
    ]
    db_session.add_all(players)
    await db_session.flush()

    # Map + tiles
    grid = generate_map_preset(preset_id="classic", seed=123, num_castles=2)
    for row in grid:
        for t in row:
            t.game_id = game.id
            db_session.add(t)
    await db_session.flush()

    # Units
    castle_xy = castle_positions(len(players))
    roster = get_roster_for_composition("classic")
    units = create_initial_units_with_roster(game, players, castle_xy, roster)
    db_session.add_all(units)

    # Castle ownership
    seat_to_pid = {p.seat: p.id for p in players}
    from sqlalchemy import select
    from app.models import Tile
    tile_rows = (await db_session.execute(
        select(Tile).where(Tile.game_id == game.id)
    )).scalars().all()
    for seat, (cx, cy) in castle_xy.items():
        for t in tile_rows:
            if t.x == cx and t.y == cy:
                t.owner_id = seat_to_pid[seat]
                break
    # Occupy tiles
    for u in units:
        for t in tile_rows:
            if t.x == u.x and t.y == u.y:
                t.occupied_unit_id = u.id
                break

    db_session.add(ActionLog(
        game_id=game.id, turn_number=1, player_id=None,
        action_type="system", description="Test game started",
    ))
    await db_session.flush()
    return game
