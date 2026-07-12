"""Commander smoke tests through the real FastAPI and SQLite boundaries."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.classes.units import get as get_unit_class
from app.classes.heroes import get as get_hero
from app.commanders.meter import UNIT_DESTROY_SCORES
from app.database import AsyncSessionLocal
from app.models import Game, Player, Unit
from app.progression.models import PlayerProfile


MAINLINE = "chapter_01_steel_rebellion"


async def _profile(client, name, commanders=("yun",)):
    response = await client.post("/progression/profiles", json={"user_name": name})
    assert response.status_code == 201, response.text
    async with AsyncSessionLocal() as session:
        profile = await session.scalar(
            select(PlayerProfile).where(PlayerProfile.user_name == name)
        )
        profile.unlocked_classes = ["swordsman", "archer", "healer", "warlock"]
        profile.unlocked_commanders = list(commanders)
        await session.commit()


@pytest.mark.integration
async def test_mainline_commander_http_db_lifecycle(client):
    """Selection, spawn, combat meter, state, empty-body fire and expiry."""
    name = "commander-e2e"
    await _profile(client, name)
    selected = await client.post(
        f"/mainlines/{MAINLINE}/select-commander",
        json={"user_name": name, "commander_id": "yun"},
    )
    assert selected.status_code == 200, selected.text
    started = await client.post(
        f"/mainlines/{MAINLINE}/start",
        json={"user_name": name, "skip_intro": True},
    )
    assert started.status_code == 201, started.text
    game_id, player_id = started.json()["game_id"], started.json()["player_id"]

    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        units = (await session.scalars(
            select(Unit).where(Unit.player_id == player_id).order_by(Unit.id)
        )).all()
        assert player.commander_id == "yun"
        assert player.co_state["threshold"] == 22
        assert units
        yun_unit = next(unit for unit in units if unit.unit_type == "warlock")
        passive_atk = round(get_hero("yun").atk_override * 1.10)
        assert yun_unit.atk == passive_atk

        enemy = await session.scalar(select(Player).where(
            Player.game_id == game_id, Player.is_ai.is_(True)
        ))
        enemy.commander_id = "anna"
        enemy.co_state = {"commander_id": "anna", "meter": 0, "threshold": 18}
        target = await session.scalar(select(Unit).where(Unit.player_id == enemy.id))
        yun_unit.x, yun_unit.y, yun_unit.has_acted = 0, 0, False
        target.x, target.y, target.hp = 1, 0, 1
        await session.commit()
        attacker_id, target_id = yun_unit.id, target.id
        target_score = UNIT_DESTROY_SCORES.get(target.unit_type, 2)
        enemy_id = enemy.id

    attacked = await client.post(f"/games/{game_id}/attack", json={
        "player_id": player_id, "attacker_id": attacker_id, "target_id": target_id,
    })
    assert attacked.status_code == 200, attacked.text
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        enemy = await session.get(Player, enemy_id)
        assert player.co_state["meter"] == target_score
        assert enemy.co_state["meter"] == 2
        player.co_state = {**player.co_state, "meter": 22}
        await session.commit()

    state = await client.get(f"/games/{game_id}/state")
    public = next(x for x in state.json()["co_states"] if x["player_id"] == player_id)
    assert public["can_fire"] is True
    fired = await client.post(
        f"/games/{game_id}/co-power", json={"player_id": player_id}
    )
    assert fired.status_code == 200, fired.text

    async with AsyncSessionLocal() as fresh_session:
        player = await fresh_session.get(Player, player_id)
        assert player.co_state["is_power_active"] is True
        assert player.co_state["meter"] == 0
        powered = await fresh_session.get(Unit, attacker_id)
        assert powered.atk > passive_atk
        player.co_state = {**player.co_state, "last_start_turn": 0}
        await fresh_session.commit()

    # Exercise the persisted baseline after a completely new ORM session.
    from app.commanders.effects import on_player_turn_start
    async with AsyncSessionLocal() as fresh_session:
        player = await fresh_session.scalar(
            select(Player).where(Player.id == player_id).options(
                selectinload(Player.units)
            )
        )
        on_player_turn_start(player, 2)
        await fresh_session.commit()
    async with AsyncSessionLocal() as check:
        player = await check.get(Player, player_id)
        unit = await check.get(Unit, attacker_id)
        assert player.co_state["is_power_active"] is False
        assert unit.atk == passive_atk


@pytest.mark.integration
async def test_mainline_victory_unlocks_only_the_completed_battle(client):
    name = "unlock-e2e"
    await _profile(client, name, commanders=())
    started = await client.post(f"/mainlines/{MAINLINE}/start", json={
        "user_name": name, "skip_intro": True,
    })
    game_id = started.json()["game_id"]
    async with AsyncSessionLocal() as session:
        game = await session.get(Game, game_id)
        game.status = "finished"
        await session.commit()
    advanced = await client.post(f"/mainlines/{MAINLINE}/advance", json={
        "user_name": name, "game_id": game_id,
    })
    assert advanced.status_code == 200, advanced.text
    async with AsyncSessionLocal() as session:
        profile = await session.scalar(select(PlayerProfile).where(
            PlayerProfile.user_name == name
        ))
        assert profile.unlocked_commanders == ["anna"]


@pytest.mark.integration
async def test_mainline_ai_enemy_commander_spawns_with_passive(client, monkeypatch):
    from app.mainline import load_mainline

    source = load_mainline(MAINLINE)
    battle = source.battles[0].model_copy(update={"enemy_commander": "anna"})
    configured = source.model_copy(update={"battles": [battle, *source.battles[1:]]})
    monkeypatch.setattr("app.routes.mainline.load_mainline", lambda _: configured)
    name = "enemy-commander-e2e"
    await _profile(client, name)
    started = await client.post(f"/mainlines/{MAINLINE}/start", json={
        "user_name": name, "skip_intro": True,
    })
    assert started.status_code == 201, started.text
    async with AsyncSessionLocal() as session:
        enemy = await session.scalar(select(Player).where(
            Player.game_id == started.json()["game_id"], Player.is_ai.is_(True)
        ))
        units = (await session.scalars(select(Unit).where(Unit.player_id == enemy.id))).all()
        assert enemy.commander_id == "anna"
        assert enemy.co_state["commander_id"] == "anna"
        assert all(u.def_ == round(get_unit_class(u.unit_type).base_def * 1.15) for u in units)
