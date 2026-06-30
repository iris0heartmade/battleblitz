"""Unit tests for the P0.4 in-game economy (gold + per-turn income).

Covers the `_collect_income_for_player` function: tiles owned by a
player that yield income (village / barracks / castle_vault) each
add their `INCOME_PER_TURN` value to the player's gold. Unowned
tiles and tiles that don't yield income are ignored.
"""
from __future__ import annotations

import pytest

from app.config import (
    CASTLE_VAULT,
    INCOME_PER_TURN,
    TERRAIN_BARRACKS,
    TERRAIN_PLAIN,
    TERRAIN_VILLAGE,
)
from app.models import ActionLog, Game, Player, Tile
from app.routes.turns import _collect_income_for_player
from app.utils import in_bounds
from sqlalchemy import select


@pytest.mark.unit
@pytest.mark.asyncio
class TestCollectIncome:
    async def test_village_50_gold(self, db_session, tmp_db_path):
        game, player = await _make_game_with_player(db_session)
        await _add_tile(db_session, game, player, TERRAIN_VILLAGE, x=1, y=1)
        await db_session.flush()

        breakdown = await _collect_income_for_player(db_session, game, player)
        await db_session.flush()

        assert breakdown == {TERRAIN_VILLAGE: 1}
        assert player.gold == INCOME_PER_TURN[TERRAIN_VILLAGE]

    async def test_mixed_income_sources(self, db_session, tmp_db_path):
        game, player = await _make_game_with_player(db_session)
        # 2 villages + 1 barracks + 1 vault
        await _add_tile(db_session, game, player, TERRAIN_VILLAGE, x=1, y=1)
        await _add_tile(db_session, game, player, TERRAIN_VILLAGE, x=2, y=1)
        await _add_tile(db_session, game, player, TERRAIN_BARRACKS, x=3, y=1)
        await _add_tile(db_session, game, player, CASTLE_VAULT, x=4, y=1)
        # Plain tile owned by same player — should NOT contribute income
        await _add_tile(db_session, game, player, TERRAIN_PLAIN, x=5, y=1)
        # Village owned by someone else — should NOT contribute
        other = await _make_other_player(db_session, game)
        await _add_tile(db_session, game, other, TERRAIN_VILLAGE, x=6, y=1)
        await db_session.flush()

        breakdown = await _collect_income_for_player(db_session, game, player)
        await db_session.flush()

        expected = (
            INCOME_PER_TURN[TERRAIN_VILLAGE] * 2
            + INCOME_PER_TURN[TERRAIN_BARRACKS] * 1
            + INCOME_PER_TURN[CASTLE_VAULT] * 1
        )
        assert breakdown == {TERRAIN_VILLAGE: 2, TERRAIN_BARRACKS: 1, CASTLE_VAULT: 1}
        assert player.gold == expected
        # Other player's gold must be untouched (their village wasn't
        # included in `player`'s income call).
        assert other.gold == 0

    async def test_no_income_yielding_tiles(self, db_session, tmp_db_path):
        game, player = await _make_game_with_player(db_session)
        # Only a plain tile owned by player — no income sources
        await _add_tile(db_session, game, player, TERRAIN_PLAIN, x=1, y=1)
        await db_session.flush()

        breakdown = await _collect_income_for_player(db_session, game, player)
        await db_session.flush()

        assert breakdown == {}
        assert player.gold == 0
        # No ActionLog is written when there's no income to record.
        logs = (await db_session.execute(
            select(ActionLog).where(
                ActionLog.game_id == game.id,
                ActionLog.action_type == "income",
            )
        )).scalars().all()
        assert logs == []

    async def test_income_adds_to_existing_gold(self, db_session, tmp_db_path):
        game, player = await _make_game_with_player(db_session)
        await _add_tile(db_session, game, player, TERRAIN_VILLAGE, x=1, y=1)
        await db_session.flush()
        player.gold = 175  # some pre-existing gold

        await _collect_income_for_player(db_session, game, player)
        await db_session.flush()

        assert player.gold == 175 + INCOME_PER_TURN[TERRAIN_VILLAGE]


# ============================================================
# Helpers
# ============================================================

async def _make_game_with_player(session):
    """Create a minimal in-memory game + a single alive player."""
    game = Game(
        name="income-test",
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


async def _make_other_player(session, game):
    player = Player(
        game_id=game.id, user_name="Other", color="blue",
        seat=1, is_alive=True, has_ended_turn=False,
        is_ai=False, agent_kind="rules", agent_personality="balanced",
        gold=0,
    )
    session.add(player)
    await session.flush()
    return player


async def _add_tile(session, game, owner, terrain, x, y):
    tile = Tile(
        game_id=game.id, x=x, y=y, terrain=terrain,
        owner_id=owner.id if owner else None,
    )
    session.add(tile)
