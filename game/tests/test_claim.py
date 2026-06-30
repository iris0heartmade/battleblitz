"""Unit tests for the P0.4 claim mechanic.

Covers the core game_logic primitives (check_pending_claims,
cancel_claim_sessions_for_unit, is_claimable). The HTTP endpoint
itself is exercised by the integration smoke test in
test_integration_smoke.py.
"""
from __future__ import annotations

import pytest

from app.config import TERRAIN_PLAIN, TERRAIN_VILLAGE
from app.game_logic import (
    cancel_claim_sessions_for_unit,
    check_pending_claims,
    is_claimable,
)
from app.models import ActionLog, ClaimSession, Game, Player, Tile, Unit
from sqlalchemy import select


def test_village_claimable():
    assert is_claimable(TERRAIN_VILLAGE) is True


def test_plain_not_claimable():
    assert is_claimable(TERRAIN_PLAIN) is False


@pytest.mark.asyncio
async def test_no_sessions_is_noop(db_session, tmp_db_path):
    game, _player = await _make_game_with_player(db_session)
    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()
    assert flipped == []


@pytest.mark.asyncio
async def test_session_before_completes_turn_does_not_flip(db_session, tmp_db_path):
    game, player = await _make_game_with_player(db_session)
    tile = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=2, y=2)
    unit = await _add_unit(db_session, game, player, x=2, y=2)
    # started_turn = 1, completes_turn = 2. We're still on turn 1.
    cs = ClaimSession(
        game_id=game.id, tile_id=tile.id, unit_id=unit.id,
        target_player_id=player.id,
        started_turn=1, completes_turn=2,
    )
    db_session.add(cs)
    await db_session.flush()

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()

    assert flipped == []
    await db_session.refresh(tile)
    assert tile.owner_id is None
    sessions = (await db_session.execute(
        select(ClaimSession).where(ClaimSession.game_id == game.id)
    )).scalars().all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_session_on_completes_turn_flips(db_session, tmp_db_path):
    game, player = await _make_game_with_player(db_session)
    tile = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=2, y=2)
    unit = await _add_unit(db_session, game, player, x=2, y=2)
    cs = ClaimSession(
        game_id=game.id, tile_id=tile.id, unit_id=unit.id,
        target_player_id=player.id,
        started_turn=1, completes_turn=2,
    )
    db_session.add(cs)
    await db_session.flush()
    game.turn_number = 2

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()

    assert flipped == [tile.id]
    await db_session.refresh(tile)
    assert tile.owner_id == player.id
    sessions = (await db_session.execute(
        select(ClaimSession).where(ClaimSession.game_id == game.id)
    )).scalars().all()
    assert sessions == []
    logs = (await db_session.execute(
        select(ActionLog).where(
            ActionLog.game_id == game.id,
            ActionLog.action_type == "claim_complete",
        )
    )).scalars().all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_unit_moved_away_cancels_claim(db_session, tmp_db_path):
    """If the unit is no longer on the contested tile, the claim is
    silently cancelled (no flip)."""
    game, player = await _make_game_with_player(db_session)
    tile = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=2, y=2)
    unit = await _add_unit(db_session, game, player, x=2, y=2)
    unit.x, unit.y = 5, 5  # unit moved
    cs = ClaimSession(
        game_id=game.id, tile_id=tile.id, unit_id=unit.id,
        target_player_id=player.id,
        started_turn=1, completes_turn=2,
    )
    db_session.add(cs)
    await db_session.flush()
    game.turn_number = 2

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()

    assert flipped == []
    await db_session.refresh(tile)
    assert tile.owner_id is None


@pytest.mark.asyncio
async def test_unit_dead_cancels_claim(db_session, tmp_db_path):
    game, player = await _make_game_with_player(db_session)
    tile = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=2, y=2)
    unit = await _add_unit(db_session, game, player, x=2, y=2)
    unit.hp = 0
    cs = ClaimSession(
        game_id=game.id, tile_id=tile.id, unit_id=unit.id,
        target_player_id=player.id,
        started_turn=1, completes_turn=2,
    )
    db_session.add(cs)
    await db_session.flush()
    game.turn_number = 2

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()

    assert flipped == []
    await db_session.refresh(tile)
    assert tile.owner_id is None


@pytest.mark.asyncio
async def test_cancel_for_unit_removes_all_sessions(db_session, tmp_db_path):
    game, player = await _make_game_with_player(db_session)
    tile1 = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=1, y=1)
    tile2 = await _add_tile(db_session, game, owner=None, terrain=TERRAIN_VILLAGE, x=2, y=2)
    unit = await _add_unit(db_session, game, player, x=1, y=1)
    for t in (tile1, tile2):
        db_session.add(ClaimSession(
            game_id=game.id, tile_id=t.id, unit_id=unit.id,
            target_player_id=player.id,
            started_turn=1, completes_turn=2,
        ))
    await db_session.flush()

    n = await cancel_claim_sessions_for_unit(db_session, unit.id)
    await db_session.flush()

    assert n == 2
    sessions = (await db_session.execute(
        select(ClaimSession).where(ClaimSession.unit_id == unit.id)
    )).scalars().all()
    assert sessions == []


# ============================================================
# Helpers
# ============================================================

async def _make_game_with_player(session):
    game = Game(
        name="claim-test",
        status="playing",
        map_seed=0,
        map_preset="classic",
        turn_number=1,
        current_player_index=0,
        phase="player",
    )
    session.add(game)
    await session.flush()
    player = Player(
        game_id=game.id, user_name="Tester", color="red",
        seat=0, is_alive=True, has_ended_turn=False,
        is_ai=False, agent_kind="rules", agent_personality="balanced",
        gold=0,
    )
    session.add(player)
    await session.flush()
    return game, player


async def _add_tile(session, game, owner, terrain, x, y):
    tile = Tile(
        game_id=game.id, x=x, y=y, terrain=terrain,
        owner_id=owner.id if owner else None,
    )
    session.add(tile)
    await session.flush()
    return tile


async def _add_unit(session, game, player, x, y):
    unit = Unit(
        player_id=player.id, unit_type="swordsman", name="TestUnit",
        level=1, exp=0,
        hp=45, max_hp=45,
        atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5,
        morale=0, x=x, y=y,
        has_acted=False, has_moved=False,
        skills=[],
    )
    session.add(unit)
    await session.flush()
    return unit