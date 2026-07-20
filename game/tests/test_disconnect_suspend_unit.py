"""
Unit tests for the WS onclose auto-suspend flow.

Why this is a *unit* test rather than a WS integration test:
  The production WS gateway runs on an anyio.from_thread worker
  (because Starlette's WebSocketTestClient is sync).  The handler's
  ``_capture_disconnect_suspend`` opens a fresh AsyncSession in
  the worker's event loop.  When the test's main loop tries to
  observe the new row via AsyncClient, the connection state from
  the worker loop and the test loop don't synchronise cleanly on
  SQLite + aiosqlite — the test consistently sees "no active
  connection" errors during teardown and the row doesn't appear
  in time.

So we test the function directly with the in-memory DB the test
session already uses.  The function is pure orchestration over
``SaveService.capture_suspend``; the WS hook integration is
validated by inspection of ``ws_gateway.py``.

Coverage:
  1. Live game + disconnect → SuspendState row appears
  2. ``suspend_point`` is "disconnect"
  3. mainline_id + battle_id parsed from Game.name
  4. ``hero_campaign_states`` NOT touched
  5. Finished game + disconnect → no row written
  6. Missing game + disconnect → no row written (no crash)
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import (
    AsyncSessionLocal,
    Base,
    dispose_db,
    engine,
    init_db,
)
from app.models import Game, Player
from app.progression.models import PlayerProfile
from app.routes.ws_gateway import _capture_disconnect_suspend
from app.save.models import SuspendPoint, SuspendState


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def db_setup():
    """Fresh DB per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    yield
    await dispose_db()


async def _create_profile(session, user_name="alice"):
    p = PlayerProfile(user_name=user_name)
    session.add(p)
    await session.flush()
    await session.refresh(p)
    return p


async def _create_live_mainline_game(session, user_name="alice", name="mainline:chapter_01:battle_01"):
    """A finished-ready playing mainline game with a human player."""
    profile = await _create_profile(session, user_name)
    game = Game(name=name, status="playing", map_seed=42, map_preset="classic")
    session.add(game)
    await session.flush()
    await session.refresh(game)
    human = Player(
        game_id=game.id, user_name=user_name, color="red",
        seat=0, is_ai=False,
    )
    session.add(human)
    await session.commit()
    return game.id, profile


# ============================================================
# Tests
# ============================================================


@pytest.mark.integration
class TestDisconnectSuspend:
    async def test_live_game_writes_suspend(self, db_setup):
        async with AsyncSessionLocal() as s:
            gid, _ = await _create_live_mainline_game(
                s, "alice", "mainline:chapter_01:battle_01",
            )

        await _capture_disconnect_suspend(user_name="alice", game_id=gid)

        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one()
        assert row.game_id == gid
        assert row.suspend_point == SuspendPoint.DISCONNECT
        assert row.mainline_id == "chapter_01"
        assert row.battle_id == "battle_01"
        # Snapshot is the meta pointer; full state is re-fetched
        # on resume.
        assert row.snapshot["game_state"]["kind"] == "live_state_pointer"

    async def test_does_not_touch_hero_state(self, db_setup):
        from copy import deepcopy
        gid = 1
        async with AsyncSessionLocal() as s:
            profile = await _create_profile(s, "alice")
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun", "class_id": "warlock",
                    "level": 5, "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False, "equipment": {},
                }
            }
            game = Game(
                name="mainline:chapter_01:battle_01",
                status="playing", map_seed=42, map_preset="classic",
            )
            s.add(game)
            await s.flush()
            human = Player(
                game_id=game.id, user_name="alice", color="red",
                seat=0, is_ai=False,
            )
            s.add(human)
            await s.commit()
            baseline = deepcopy(dict(profile.hero_campaign_states))
            gid = game.id

        await _capture_disconnect_suspend(user_name="alice", game_id=gid)

        async with AsyncSessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert dict(p.hero_campaign_states) == baseline

    async def test_finished_game_skipped(self, db_setup):
        async with AsyncSessionLocal() as s:
            profile = await _create_profile(s, "alice")
            game = Game(
                name="mainline:chapter_01:battle_01",
                status="finished", map_seed=42, map_preset="classic",
            )
            s.add(game)
            await s.flush()
            gid = game.id

        await _capture_disconnect_suspend(user_name="alice", game_id=gid)

        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one_or_none()
        assert row is None

    async def test_missing_game_skipped(self, db_setup):
        # No game row at all
        await _capture_disconnect_suspend(user_name="alice", game_id=999)
        # No crash, no row
        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one_or_none()
        assert row is None

    async def test_non_mainline_name_parsing(self, db_setup):
        """Open-mode games (not mainline) still get a suspend row,
        with mainline_id="" and battle_id=game.name.  The FE checks
        for an empty mainline_id to decide whether to show the
        mainline-resume option."""
        async with AsyncSessionLocal() as s:
            profile = await _create_profile(s, "alice")
            game = Game(
                name="My Lobby Match",
                status="playing", map_seed=42, map_preset="classic",
            )
            s.add(game)
            await s.flush()
            human = Player(
                game_id=game.id, user_name="alice", color="red",
                seat=0, is_ai=False,
            )
            s.add(human)
            await s.commit()
            gid = game.id

        await _capture_disconnect_suspend(user_name="alice", game_id=gid)

        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one()
        assert row.mainline_id == ""
        assert row.battle_id == "My Lobby Match"

    async def test_disconnect_overwrites_previous_suspend(self, db_setup):
        """Reconnect + disconnect twice → still one row, newer
        saved_at (per SuspendState PK semantics)."""
        async with AsyncSessionLocal() as s:
            profile = await _create_profile(s, "alice")
            game = Game(
                name="mainline:chapter_01:battle_01",
                status="playing", map_seed=42, map_preset="classic",
            )
            s.add(game)
            await s.flush()
            await s.commit()  # commit so subsequent session sees the row
            gid = game.id

        # First disconnect
        await _capture_disconnect_suspend(user_name="alice", game_id=gid)
        async with AsyncSessionLocal() as s:
            first = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one()
        first_saved = first.saved_at

        import asyncio
        await asyncio.sleep(0.02)

        # Second disconnect
        await _capture_disconnect_suspend(user_name="alice", game_id=gid)
        async with AsyncSessionLocal() as s:
            rows = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalars().all()
        assert len(rows) == 1
        assert rows[0].saved_at >= first_saved
