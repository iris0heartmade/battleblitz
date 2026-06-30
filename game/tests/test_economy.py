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
from httpx import ASGITransport, AsyncClient
from app.main import app


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
# Recruit (Phase 6) — end-to-end via the HTTP endpoint
# ============================================================

@pytest.mark.unit
class TestRecruitEndpoint:
    async def test_recruit_swordsman_at_owned_barracks(self, db_session, tmp_db_path):
        """A player with 200+ gold and a unit on an owned barracks
        successfully recruits a swordsman and loses 200 gold."""
        from app.config import RECRUIT_COST, TERRAIN_BARRACKS
        from app.models import Game, Player, Tile, Unit

        game = Game(
            name="recruit-test", status="playing", map_seed=0,
            map_preset="classic", turn_number=1, current_player_index=0,
            phase="player",
        )
        db_session.add(game)
        await db_session.flush()
        player = Player(
            game_id=game.id, user_name="Recruiter", color="red",
            seat=0, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            gold=300,  # enough for 1 swordsman (cost 200)
        )
        db_session.add(player)
        await db_session.flush()
        tile = Tile(
            game_id=game.id, x=5, y=5, terrain=TERRAIN_BARRACKS,
            owner_id=player.id,
        )
        db_session.add(tile)
        await db_session.flush()
        unit = Unit(
            player_id=player.id, unit_type="swordsman", name="RecruiterUnit",
            level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12,
            matk=4, mdef=4, mov=5, mp=5, morale=0,
            x=5, y=5, has_acted=False, has_moved=False, skills=[],
        )
        db_session.add(unit)
        await db_session.commit()  # commit so the HTTP endpoint can see it

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(f"/games/{game.id}/recruit", json={
                "player_id": player.id, "unit_id": unit.id, "unit_type": "swordsman",
            })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["cost"] == RECRUIT_COST["swordsman"]
        assert body["gold_remaining"] == 300 - RECRUIT_COST["swordsman"]
        assert body["new_unit_type"] == "swordsman"
        assert body["recruiter_unit_id"] == unit.id

    async def test_recruit_insufficient_gold(self, db_session, tmp_db_path):
        from app.config import RECRUIT_COST, TERRAIN_BARRACKS
        from app.models import Game, Player, Tile, Unit

        game = Game(
            name="poor-recruit", status="playing", map_seed=0,
            map_preset="classic", turn_number=1, current_player_index=0,
            phase="player",
        )
        db_session.add(game)
        await db_session.flush()
        player = Player(
            game_id=game.id, user_name="Poor", color="red",
            seat=0, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            gold=10,  # way too little for any unit
        )
        db_session.add(player)
        await db_session.flush()
        tile = Tile(
            game_id=game.id, x=5, y=5, terrain=TERRAIN_BARRACKS,
            owner_id=player.id,
        )
        db_session.add(tile)
        await db_session.flush()
        unit = Unit(
            player_id=player.id, unit_type="swordsman", name="U",
            level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12,
            matk=4, mdef=4, mov=5, mp=5, morale=0,
            x=5, y=5, has_acted=False, has_moved=False, skills=[],
        )
        db_session.add(unit)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(f"/games/{game.id}/recruit", json={
                "player_id": player.id, "unit_id": unit.id, "unit_type": "swordsman",
            })
        assert r.status_code == 400
        # Money and units are unchanged.
        await db_session.refresh(player)
        assert player.gold == 10
        swordsmen = (await db_session.execute(
            select(Unit).where(Unit.player_id == player.id, Unit.unit_type == "swordsman")
        )).scalars().all()
        assert len(swordsmen) == 1  # only the recruiter

    async def test_recruit_on_foreign_barracks_rejected(self, db_session, tmp_db_path):
        from app.config import TERRAIN_BARRACKS
        from app.models import Game, Player, Tile, Unit

        game = Game(
            name="foreign-barracks", status="playing", map_seed=0,
            map_preset="classic", turn_number=1, current_player_index=0,
            phase="player",
        )
        db_session.add(game)
        await db_session.flush()
        attacker = Player(
            game_id=game.id, user_name="Attacker", color="red",
            seat=0, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            gold=500,
        )
        owner = Player(
            game_id=game.id, user_name="Owner", color="blue",
            seat=1, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            gold=0,
        )
        db_session.add_all([attacker, owner])
        await db_session.flush()
        tile = Tile(
            game_id=game.id, x=5, y=5, terrain=TERRAIN_BARRACKS,
            owner_id=owner.id,
        )
        db_session.add(tile)
        await db_session.flush()
        intruder = Unit(
            player_id=attacker.id, unit_type="swordsman", name="Intruder",
            level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12,
            matk=4, mdef=4, mov=5, mp=5, morale=0,
            x=5, y=5, has_acted=False, has_moved=False, skills=[],
        )
        db_session.add(intruder)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(f"/games/{game.id}/recruit", json={
                "player_id": attacker.id, "unit_id": intruder.id, "unit_type": "swordsman",
            })
        assert r.status_code == 400
        body = r.json()
        assert "Owner" in body["detail"] or "其他玩家" in body["detail"]
        await db_session.refresh(attacker)
        assert attacker.gold == 500
        swordsmen = (await db_session.execute(
            select(Unit).where(Unit.player_id == attacker.id, Unit.unit_type == "swordsman")
        )).scalars().all()
        assert len(swordsmen) == 1  # only the intruder

    async def test_recruit_marks_recruiter_as_acted(self, db_session, tmp_db_path):
        from app.config import RECRUIT_COST, TERRAIN_BARRACKS
        from app.models import Game, Player, Tile, Unit

        game = Game(
            name="recruit-acted", status="playing", map_seed=0,
            map_preset="classic", turn_number=1, current_player_index=0,
            phase="player",
        )
        db_session.add(game)
        await db_session.flush()
        player = Player(
            game_id=game.id, user_name="R", color="red",
            seat=0, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            gold=RECRUIT_COST["archer"],
        )
        db_session.add(player)
        await db_session.flush()
        tile = Tile(
            game_id=game.id, x=5, y=5, terrain=TERRAIN_BARRACKS,
            owner_id=player.id,
        )
        db_session.add(tile)
        await db_session.flush()
        unit = Unit(
            player_id=player.id, unit_type="swordsman", name="R-unit",
            level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12,
            matk=4, mdef=4, mov=5, mp=5, morale=0,
            x=5, y=5, has_acted=False, has_moved=False, skills=[],
        )
        db_session.add(unit)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(f"/games/{game.id}/recruit", json={
                "player_id": player.id, "unit_id": unit.id, "unit_type": "archer",
            })
        assert r.status_code == 200
        new_id = r.json()["new_unit_id"]

        await db_session.refresh(unit)
        assert unit.has_acted is True
        assert unit.mp == 0
        new_unit = await db_session.get(Unit, new_id)
        assert (new_unit.x, new_unit.y) == (5, 5)
        assert new_unit.has_acted is True
        assert new_unit.has_moved is True
        assert new_unit.mp == 0
        assert new_unit.unit_type == "archer"


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
