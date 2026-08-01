from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.classes.units import get as get_unit_class
from app.models import Game, Player, Unit
from app.routes.game import _start_battle_internal
from app.routes.turns import end_turn
from app.schemas import EndTurnRequest


@pytest.mark.asyncio
async def test_start_bakes_each_players_passive_once(db_session):
    game = Game(name="co-spawn", status="waiting", map_seed=7, map_preset="classic")
    db_session.add(game)
    await db_session.flush()
    red = Player(game_id=game.id, user_name="red", color="red", seat=0,
                 commander_id="yun")
    blue = Player(game_id=game.id, user_name="blue", color="blue", seat=1,
                  commander_id="anna")
    db_session.add_all([red, blue])
    await db_session.flush()

    await _start_battle_internal(db_session, game, [red, blue])
    units = (await db_session.execute(select(Unit))).scalars().all()
    red_units = [u for u in units if u.player_id == red.id]
    blue_units = [u for u in units if u.player_id == blue.id]

    assert red_units and blue_units
    for unit in red_units:
        base = get_unit_class(unit.unit_type)
        assert unit.atk == round(base.base_atk * 1.10)
    for unit in blue_units:
        base = get_unit_class(unit.unit_type)
        assert unit.def_ == round(base.base_def * 1.15)
    assert red.co_state["last_start_turn"] == 1


@pytest.mark.asyncio
async def test_passive_rebake_after_reload_is_idempotent_and_restores_range(db_session):
    from app.commanders.effects import bake_passive_into_units
    game = Game(name="reload", status="playing", map_seed=1)
    db_session.add(game)
    await db_session.flush()
    player = Player(game_id=game.id, user_name="p", color="red", seat=0,
                    commander_id="yun", co_state={})
    db_session.add(player)
    await db_session.flush()
    unit = Unit(player_id=player.id, unit_type="archer", name="a", hp=30,
                max_hp=30, atk=15, def_=5, matk=3, mdef=3, mov=4, mp=4,
                x=0, y=0, skills=[])
    db_session.add(unit)
    await db_session.flush()
    await db_session.refresh(player, ["units"])
    bake_passive_into_units(player)
    assert unit.atk == 16
    await db_session.commit()
    db_session.expunge_all()
    reloaded = await db_session.get(Player, player.id)
    await db_session.refresh(reloaded, ["units"])
    bake_passive_into_units(reloaded)
    assert reloaded.units[0].atk == 16
    assert reloaded.units[0]._base_attack_range == 5


@pytest.mark.asyncio
async def test_timeout_round_wrap_runs_commander_lifecycle(db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.routes.turns import _check_stale_turns
    game = Game(name="timeout", status="playing", map_seed=1,
                current_player_index=0, turn_number=1, phase="player",
                created_at=datetime.now(timezone.utc) - timedelta(days=2))
    db_session.add(game)
    await db_session.flush()
    red = Player(game_id=game.id, user_name="red", color="red", seat=0,
                 commander_id="yun", co_state={"stars_earned_total": 0,
                 "threshold": 18, "power_cost": 6,
                 "is_power_active": True, "last_start_turn": 1,
                 "_power_baselines": {}})
    blue = Player(game_id=game.id, user_name="blue", color="blue", seat=1,
                  has_ended_turn=True)
    db_session.add_all([red, blue])
    await db_session.commit()
    red_id = red.id
    async def no_eot(session, battle): return SimpleNamespace(leveled_units=[])
    monkeypatch.setattr("app.routes.turns.apply_end_of_turn", no_eot)
    await _check_stale_turns()
    db_session.expire_all()
    refreshed = await db_session.get(Player, red_id)
    assert refreshed.co_state["is_power_active"] is False
    assert refreshed.co_state["last_start_turn"] == 2


@pytest.mark.asyncio
async def test_mainline_enemy_commander_is_configured_and_baked(db_session, monkeypatch):
    from app.mainline import load_mainline
    from app.progression import PlayerProfile
    from app.routes.mainline import _spawn_battle_for_index

    source = load_mainline("chapter_01_steel_rebellion")
    enemy_battle = source.battles[0].model_copy(update={"enemy_commander": "anna"})
    configured = source.model_copy(update={
        "battles": [enemy_battle, *source.battles[1:]],
    })
    monkeypatch.setattr("app.routes.mainline.load_mainline", lambda _: configured)
    profile = PlayerProfile(user_name="campaign", unlocked_classes=[
        "swordsman", "archer", "healer", "warlock",
    ], mainline_commanders={})
    db_session.add(profile)
    await db_session.flush()

    game, _, _ = await _spawn_battle_for_index(
        db_session, profile, "chapter_01_steel_rebellion", 0,
    )
    players = (await db_session.execute(
        select(Player).where(Player.game_id == game.id)
    )).scalars().all()
    enemy = next(player for player in players if player.is_ai)
    enemy_units = (await db_session.execute(
        select(Unit).where(Unit.player_id == enemy.id)
    )).scalars().all()
    assert enemy.commander_id == "anna"
    assert enemy.co_state["commander_id"] == "anna"
    assert enemy_units
    for unit in enemy_units:
        assert unit.def_ == round(get_unit_class(unit.unit_type).base_def * 1.15)


@pytest.mark.asyncio
async def test_power_expires_only_at_owners_next_round_start(db_session, monkeypatch):
    game = Game(name="co-turn", status="playing", current_player_index=0,
                turn_number=1, phase="player", map_seed=1)
    db_session.add(game)
    await db_session.flush()
    red = Player(game_id=game.id, user_name="red", color="red", seat=0,
                 commander_id="yun", co_state={"stars_earned_total": 0,
                 "threshold": 18, "power_cost": 6,
                 "is_power_active": True, "last_start_turn": 1,
                 "_power_baselines": {}})
    blue = Player(game_id=game.id, user_name="blue", color="blue", seat=1,
                  commander_id="anna", co_state={"stars_earned_total": 0,
                  "threshold": 14, "power_cost": 6,
                  "is_power_active": True, "last_start_turn": 1,
                  "_power_baselines": {}})
    db_session.add_all([red, blue])
    await db_session.flush()

    async def no_eot(session, battle):
        return SimpleNamespace(leveled_units=[])
    monkeypatch.setattr("app.routes.turns.apply_end_of_turn", no_eot)

    await end_turn(game.id, EndTurnRequest(player_id=red.id), db_session)
    assert red.co_state["is_power_active"] is True
    assert blue.co_state["is_power_active"] is True
    await end_turn(game.id, EndTurnRequest(player_id=blue.id), db_session)
    assert red.co_state["is_power_active"] is False
    assert blue.co_state["is_power_active"] is True


@pytest.mark.asyncio
async def test_first_turn_fire_expires_at_next_round_after_real_spawn(db_session, monkeypatch):
    from app.commanders.effects import fire_co_power
    game = Game(name="first-fire", status="waiting", map_seed=8,
                map_preset="classic")
    db_session.add(game)
    await db_session.flush()
    red = Player(game_id=game.id, user_name="red", color="red", seat=0,
                 commander_id="yun", co_state={"stars_earned_total": 18,
                 "threshold": 18, "power_cost": 6,
                 "is_power_active": False, "last_start_turn": -1},
                 has_ended_turn=False, is_alive=True)
    blue = Player(game_id=game.id, user_name="blue", color="blue", seat=1,
                  has_ended_turn=False, is_alive=True)
    db_session.add_all([red, blue])
    await db_session.flush()
    await _start_battle_internal(db_session, game, [red, blue])
    red.has_ended_turn = False
    blue.has_ended_turn = False
    await db_session.refresh(red, ["units"])
    fire_co_power(red)
    async def no_eot(session, battle): return SimpleNamespace(leveled_units=[])
    monkeypatch.setattr("app.routes.turns.apply_end_of_turn", no_eot)
    await end_turn(game.id, EndTurnRequest(player_id=red.id), db_session)
    await end_turn(game.id, EndTurnRequest(player_id=blue.id), db_session)
    assert red.co_state["is_power_active"] is False
    assert red.co_state["last_start_turn"] == 2
