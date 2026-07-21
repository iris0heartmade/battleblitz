"""
Tests for F5B mainline event triggers (waves / traps / boss_kill).

Verifies the actual engine hooks really fire the expected events when
``apply_end_of_turn`` runs, by:
  1. Setting up a game whose ``name`` matches a known mainline
  2. Seeding units in the DB at the right tile coordinates
  3. Calling ``apply_end_of_turn`` via httpx
  4. Asserting the events log shows waves / trap damage / boss kill

These tests run after the F5B hook is registered (which happens at
``app.main`` import time).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.events import bus  # noqa: E402
from app.main import app  # noqa: E402  (registers F5B hook)
from app.database import init_db, dispose_db  # noqa: E402
from app.mainline import clear_cache, load_mainline  # noqa: E402


# ============================================================
# Helpers
# ============================================================

async def _start_chapter(client, user_name: str, mainline_id: str) -> int:
    """POST /mainlines/{id}/start, return game_id."""
    r = await client.post(
        f"/mainlines/{mainline_id}/start",
        json={"user_name": user_name, "skip_intro": True},
    )
    assert r.status_code in (200, 201), r.text
    return int(r.json()["game_id"])


# ============================================================
# Tests
# ============================================================

@pytest.mark.asyncio
async def test_wave_event_published_on_matching_turn(tmp_path):
    """When the current turn matches a battle's wave entry, apply_end_of_turn
    must spawn the unit and publish a move event with wave_turn marker.
    """
    from app.database import AsyncSessionLocal
    from app.models import Game, Player, Unit
        
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # chapter_06 battle_01 has waves at turn 3 and 7
            game_id = await _start_chapter(c, "f5b_tester", "chapter_06_iron_reckoning")

            # Bump game turn to 3 (battle_01 wave 0)
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                g.turn_number = 3
                await s.commit()

            # 直接调 apply_end_of_turn (绕开 HTTP, 走被 hook 的函数)
            from app.game_logic import apply_end_of_turn as _aet
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                await _aet(s, g)

        # Verify the log contains a wave-3 move event
        body = log.read_text(encoding="utf-8")
        events = [json.loads(l) for l in body.splitlines()
                  if l.strip() and not l.startswith("===")]
        wave_events = [e for e in events if e.get("type") == "move"
                       and e.get("ctx", {}).get("wave_turn") == 3]
        assert len(wave_events) >= 1, f"no wave-3 move in log: {events}"
        # Confirm a knight spawned at (12, 0) per the JSON
        ctx = wave_events[0]["ctx"]
        assert ctx["x"] == 12 and ctx["y"] == 0
        assert ctx["type"] == "knight"
        assert ctx["color"] == "blue"

        await dispose_db()
    finally:
        bus.close_file_logger()


@pytest.mark.asyncio
async def test_trap_event_published_when_unit_on_trap(tmp_path):
    """When a player unit sits on a trap coordinate, apply_end_of_turn
    must publish an attack event with trap=True and damage applied.
    """
    from app.database import AsyncSessionLocal
    from app.models import Game, Player, Unit

    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            game_id = await _start_chapter(c, "f5b_trap_tester", "chapter_06_iron_reckoning")

            # Manually move a red player unit to (8, 4) (trap_8_4 in JSON)
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                g.turn_number = 9  # turn 9 has yun in our snapshot
                # Find a red unit and move it
                from sqlalchemy import select
                reds = (await s.execute(
                    select(Player).where(Player.game_id == game_id, Player.color == "red")
                )).scalars().all()
                assert reds, "no red player"
                units = (await s.execute(
                    select(Unit).where(Unit.player_id == reds[0].id, Unit.hp > 0)
                )).scalars().all()
                if units:
                    units[0].x = 8
                    units[0].y = 4
                    await s.commit()

            # 直接调 apply_end_of_turn
            from app.game_logic import apply_end_of_turn as _aet
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                await _aet(s, g)

        body = log.read_text(encoding="utf-8")
        events = [json.loads(l) for l in body.splitlines()
                  if l.strip() and not l.startswith("===")]
        trap_events = [e for e in events if e.get("type") == "attack"
                       and e.get("ctx", {}).get("trap") is True]
        assert len(trap_events) >= 1, f"no trap attack in log: {events}"
        ctx = trap_events[0]["ctx"]
        assert ctx["x"] == 8 and ctx["y"] == 4
        assert ctx["dmg"] == 8  # battle_01 traps[0] damage is 8

        await dispose_db()
    finally:
        bus.close_file_logger()


@pytest.mark.asyncio
async def test_wave_no_match_publishes_nothing(tmp_path):
    """When turn doesn't match any wave, no wave event fires.
    (Trap and boss events also no-op since we haven't set them up.)
    """
    from app.database import AsyncSessionLocal
    from app.models import Game

    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            game_id = await _start_chapter(c, "f5b_quiet", "chapter_06_iron_reckoning")
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                g.turn_number = 1  # not 3 or 7
                await s.commit()
            from app.game_logic import apply_end_of_turn as _aet
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, game_id)
                await _aet(s, g)

        body = log.read_text(encoding="utf-8")
        events = [json.loads(l) for l in body.splitlines()
                  if l.strip() and not l.startswith("===")]
        wave_events = [e for e in events if e.get("type") == "move"
                       and e.get("ctx", {}).get("wave_turn") is not None]
        assert wave_events == [], f"unexpected wave events: {wave_events}"

        await dispose_db()
    finally:
        bus.close_file_logger()
