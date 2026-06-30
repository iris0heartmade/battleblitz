"""Tests for P2.3 victory conditions (Phase 1: rout + team aggregation).

Covers:
- check_win_condition returns True when one team drops to 0 units
  (Rout = last surviving team wins)
- A team with at least one alive unit is still 'alive'
- Two surviving teams = no winner (game continues)
- All-dead tie produces a draw (win_reason = 'draw')
- Team aggregation works: 2 players sharing team_id count as
  one logical side
- game.win_reason is set on the Game row when finished
"""
from __future__ import annotations

import pytest

from app.config import TERRAIN_PLAIN
from app.game_logic import check_win_condition
from app.models import Game, Player, Tile, Unit
from sqlalchemy import select


# ============================================================
# Helpers
# ============================================================

async def _make_game(db_session, *, num_players: int = 2,
                      teams: list[str] | None = None):
    """Create a minimal in-memory game with N players, all on plain
    tiles. `teams` overrides auto-assigned team_id (one entry per
    player; defaults to None which means 'use color')."""
    game = Game(
        name="victory-test", status="playing", map_seed=0,
        map_preset="classic", turn_number=1,
        current_player_index=0, phase="player",
        win_condition="rout",
    )
    db_session.add(game)
    await db_session.flush()
    colors = ("red", "blue", "green", "yellow")
    players = []
    for i in range(num_players):
        p = Player(
            game_id=game.id, user_name=f"P{i}", color=colors[i % 4],
            seat=i, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            team_id=(teams[i] if teams else None),
        )
        db_session.add(p)
        await db_session.flush()
        players.append(p)
    return game, players


async def _add_alive_unit(db_session, game, player, x, y):
    u = Unit(
        player_id=player.id, unit_type="swordsman", name=f"{player.user_name}-u",
        level=1, exp=0, hp=45, max_hp=45,
        atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0,
        x=x, y=y, has_acted=False, has_moved=False, skills=[],
    )
    db_session.add(u)
    await db_session.flush()
    # Make sure the (x, y) tile exists + the unit is parked on it.
    tile = (await db_session.execute(
        select(Tile).where(Tile.game_id == game.id, Tile.x == x, Tile.y == y)
    )).scalars().first()
    if tile is None:
        tile = Tile(game_id=game.id, x=x, y=y, terrain=TERRAIN_PLAIN)
        db_session.add(tile)
        await db_session.flush()
    tile.occupied_unit_id = u.id
    return u


async def _mark_dead(db_session, u):
    u.hp = 0
    await db_session.flush()


# ============================================================
# Tests
# ============================================================

@pytest.mark.asyncio
async def test_rout_one_team_dead_triggers_win(db_session, tmp_db_path):
    game, players = await _make_game(db_session, num_players=2)
    u1 = await _add_alive_unit(db_session, game, players[0], 0, 0)
    u2 = await _add_alive_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    # Both teams alive -> game continues
    ended = await check_win_condition(db_session, game)
    assert ended is False

    # Player 1's unit dies -> only player 0 alive -> rout
    await _mark_dead(db_session, u2)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.status == "finished"
    assert game.win_reason == "rout"


@pytest.mark.asyncio
async def test_rout_one_unit_alive_keeps_team_alive(db_session, tmp_db_path):
    """Owner rule 1: 'one unit alive = the team is still alive'."""
    game, players = await _make_game(db_session, num_players=2)
    u1a = await _add_alive_unit(db_session, game, players[0], 0, 0)
    u1b = await _add_alive_unit(db_session, game, players[0], 0, 1)
    u2 = await _add_alive_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    # Kill one of player 0's two units. They still have u1b -> alive.
    await _mark_dead(db_session, u1a)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is False  # game continues
    assert game.status == "playing"

    # Now kill the second. Player 0 has 0 units -> rout.
    await _mark_dead(db_session, u1b)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.win_reason == "rout"


@pytest.mark.asyncio
async def test_rout_two_teams_alive_no_winner(db_session, tmp_db_path):
    game, players = await _make_game(db_session, num_players=2)
    await _add_alive_unit(db_session, game, players[0], 0, 0)
    await _add_alive_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is False
    assert game.status == "playing"


@pytest.mark.asyncio
async def test_rout_both_dead_is_draw(db_session, tmp_db_path):
    game, players = await _make_game(db_session, num_players=2)
    u1 = await _add_alive_unit(db_session, game, players[0], 0, 0)
    u2 = await _add_alive_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    await _mark_dead(db_session, u1)
    await _mark_dead(db_session, u2)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.status == "finished"
    assert game.win_reason == "draw"


@pytest.mark.asyncio
async def test_team_aggregation_2v1_two_allies_share_team(db_session, tmp_db_path):
    """Owner rule 3: in team mode, 'a side' = a team. Here P0+P1 are
    on team 'red' vs P2 on 'blue'. Killing BOTH red players' units
    is the rout trigger; killing only one of them is not."""
    game, players = await _make_game(
        db_session, num_players=3, teams=["red", "red", "blue"]
    )
    r1u = await _add_alive_unit(db_session, game, players[0], 0, 0)
    r2u = await _add_alive_unit(db_session, game, players[1], 0, 1)
    bu = await _add_alive_unit(db_session, game, players[2], 5, 5)
    await db_session.flush()
    # Kill one of the red players. Red team still has 1 unit -> alive.
    await _mark_dead(db_session, r1u)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is False
    assert game.status == "playing"

    # Kill the second red player. Red team now has 0 units.
    await _mark_dead(db_session, r2u)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.win_reason == "rout"


@pytest.mark.asyncio
async def test_default_team_falls_back_to_color(db_session, tmp_db_path):
    """Without an explicit team_id, a player's team defaults to
    their color (1V1 free-for-all behaviour)."""
    game, players = await _make_game(db_session, num_players=2)
    # No team_id set -> each player is their own team (color).
    assert players[0].team_id is None
    assert players[1].team_id is None
    # 1 unit each -> 2 teams alive -> no winner.
    await _add_alive_unit(db_session, game, players[0], 0, 0)
    await _add_alive_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is False


@pytest.mark.asyncio
async def test_check_win_noop_when_game_already_finished(db_session, tmp_db_path):
    game, players = await _make_game(db_session, num_players=2)
    await _add_alive_unit(db_session, game, players[0], 0, 0)
    await _add_alive_unit(db_session, game, players[1], 5, 5)
    game.status = "finished"
    game.win_reason = "rout"
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    # Already finished -> returns True but doesn't re-set anything.
    assert ended is True
    assert game.win_reason == "rout"
