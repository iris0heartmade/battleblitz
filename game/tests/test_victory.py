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

from app.config import TERRAIN_CASTLE, TERRAIN_PLAIN, TERRAIN_VILLAGE
from app.game_logic import check_win_condition, check_pending_claims
from app.models import ActionLog, ClaimSession, Game, Player, Tile, Unit
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


# ============================================================
# Phase 2 — Seize mode (ownership flip on a castle tile wins)
# ============================================================

async def _make_seize_game(db_session):
    """Create a 2-player game with a single castle tile assigned to
    player 0. Both players have one unit; player 1 will try to seize
    player 0's HQ."""
    game = Game(
        name="seize-test", status="playing", map_seed=0,
        map_preset="classic", turn_number=1,
        current_player_index=0, phase="player",
        win_condition="seize",
    )
    db_session.add(game)
    await db_session.flush()
    colors = ("red", "blue")
    players = []
    for i in range(2):
        p = Player(
            game_id=game.id, user_name=f"P{i}", color=colors[i],
            seat=i, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            team_id=None,
        )
        db_session.add(p)
        await db_session.flush()
        players.append(p)
    return game, players


@pytest.mark.asyncio
async def test_seize_hq_takeover_triggers_victory(db_session, tmp_db_path):
    """Player 1 claims player 0's castle (HQ) for CLAIM_TURNS_REQUIRED
    turns. When the claim completes, the seizing team wins the match."""
    from app.config import CLAIM_TURNS_REQUIRED
    game, players = await _make_seize_game(db_session)
    # player 0's HQ at (0, 0) — castle
    hq = Tile(game_id=game.id, x=0, y=0, terrain=TERRAIN_CASTLE, owner_id=players[0].id)
    db_session.add(hq)
    await db_session.flush()
    # Both players have 1 unit. Place attacker on the HQ (the
    # starting tile is fine — claim is "I'm standing on it").
    attacker = await _add_alive_unit(db_session, game, players[1], 0, 0)
    defender_unit = await _add_alive_unit(db_session, game, players[0], 5, 5)
    await db_session.flush()
    # Set up a ClaimSession whose completes_turn is now (so the
    # next call to check_pending_claims finalises it).
    cs = ClaimSession(
        game_id=game.id, tile_id=hq.id, unit_id=attacker.id,
        target_player_id=players[1].id,
        started_turn=1,
        completes_turn=game.turn_number,
    )
    db_session.add(cs)
    await db_session.flush()

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()
    assert hq.id in flipped
    # The seizing team (player 1's color/team = 'blue') should win.
    assert game.status == "finished"
    assert game.win_reason == "seize"
    # A "victory" ActionLog was written.
    logs = (await db_session.execute(
        select(ActionLog).where(
            ActionLog.game_id == game.id,
            ActionLog.action_type == "victory",
        )
    )).scalars().all()
    assert len(logs) == 1
    assert "blue" in logs[0].description


@pytest.mark.asyncio
async def test_seize_non_castle_claim_does_not_trigger_victory(db_session, tmp_db_path):
    """Only castle tiles are HQs. A claim on a village is a normal
    P0.4 income flip — no seize win."""
    game, players = await _make_seize_game(db_session)
    game.win_condition = "seize"
    await db_session.flush()
    village = Tile(game_id=game.id, x=2, y=2, terrain=TERRAIN_VILLAGE, owner_id=None)
    db_session.add(village)
    await db_session.flush()
    attacker = await _add_alive_unit(db_session, game, players[1], 2, 2)
    await _add_alive_unit(db_session, game, players[0], 5, 5)
    await db_session.flush()
    cs = ClaimSession(
        game_id=game.id, tile_id=village.id, unit_id=attacker.id,
        target_player_id=players[1].id,
        started_turn=1, completes_turn=game.turn_number,
    )
    db_session.add(cs)
    await db_session.flush()
    await check_pending_claims(db_session, game)
    await db_session.flush()
    # Village flipped to blue's ownership but no win.
    assert village.owner_id == players[1].id
    assert game.status == "playing"
    assert game.win_reason is None


@pytest.mark.asyncio
async def test_seize_2v1_team_share_hq_both_players_can_trigger(db_session, tmp_db_path):
    """In team mode, taking an opponent HQ ends the match for the
    seizing team. The losing team's shared HQ is captured by a
    single player on the winning team — that single player's
    team_id wins."""
    game, players = await _make_game(
        db_session, num_players=3, teams=["blue", "red", "red"]
    )
    game.win_condition = "seize"
    await db_session.flush()
    # The red team (players 1, 2) own a single castle HQ at (3, 3).
    red_hq = Tile(game_id=game.id, x=3, y=3, terrain=TERRAIN_CASTLE, owner_id=players[1].id)
    db_session.add(red_hq)
    await db_session.flush()
    blue_unit = await _add_alive_unit(db_session, game, players[0], 3, 3)
    await _add_alive_unit(db_session, game, players[1], 8, 8)
    await _add_alive_unit(db_session, game, players[2], 8, 9)
    await db_session.flush()
    cs = ClaimSession(
        game_id=game.id, tile_id=red_hq.id, unit_id=blue_unit.id,
        target_player_id=players[0].id,
        started_turn=1, completes_turn=game.turn_number,
    )
    db_session.add(cs)
    await db_session.flush()
    await check_pending_claims(db_session, game)
    await db_session.flush()
    assert game.status == "finished"
    assert game.win_reason == "seize"
    # blue team won; the description should mention blue.
    log = (await db_session.execute(
        select(ActionLog).where(
            ActionLog.game_id == game.id,
            ActionLog.action_type == "victory",
        )
    )).scalars().first()
    assert "blue" in log.description


@pytest.mark.asyncio
async def test_rout_mode_unaffected_by_claim_completion(db_session, tmp_db_path):
    """In rout mode (default), a claim completing on a castle just
    transfers ownership without ending the game — only rout decides."""
    game, players = await _make_seize_game(db_session)
    game.win_condition = "rout"  # override
    await db_session.flush()
    hq = Tile(game_id=game.id, x=0, y=0, terrain=TERRAIN_CASTLE, owner_id=players[0].id)
    db_session.add(hq)
    await db_session.flush()
    attacker = await _add_alive_unit(db_session, game, players[1], 0, 0)
    await _add_alive_unit(db_session, game, players[0], 5, 5)
    await db_session.flush()
    cs = ClaimSession(
        game_id=game.id, tile_id=hq.id, unit_id=attacker.id,
        target_player_id=players[1].id,
        started_turn=1, completes_turn=game.turn_number,
    )
    db_session.add(cs)
    await db_session.flush()
    await check_pending_claims(db_session, game)
    await db_session.flush()
    # Both players still alive → game continues.
    assert hq.owner_id == players[1].id  # ownership DID flip
    assert game.status == "playing"
    assert game.win_reason is None
