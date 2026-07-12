"""Integration regressions for commander meter scoring in real combat paths."""
import pytest
from sqlalchemy import select

from app.game_logic import DamageResult, cleanup_dead_units
from app.models import Game, Player, Tile, Unit
from app.routes.actions import attack
from app.schemas import AttackRequest


async def _combat(db_session, *, attacker_hp=20, target_hp=5):
    game = Game(name="meter", status="playing", map_seed=1, win_condition="defend")
    db_session.add(game)
    await db_session.flush()
    attacker_player = Player(
        game_id=game.id, user_name="attacker", color="red", seat=0,
        commander_id="yun",
        co_state={"meter": 0, "threshold": 20},
    )
    defender_player = Player(
        game_id=game.id, user_name="defender", color="blue", seat=1,
        commander_id="anna",
        co_state={"meter": 0, "threshold": 20},
    )
    db_session.add_all([attacker_player, defender_player])
    await db_session.flush()
    attacker = Unit(
        player_id=attacker_player.id, unit_type="swordsman", name="A",
        hp=attacker_hp, max_hp=20, atk=20, def_=1, matk=0, mdef=0,
        mov=3, mp=3, x=0, y=0, skills=[],
    )
    target = Unit(
        player_id=defender_player.id, unit_type="archer", name="D",
        hp=target_hp, max_hp=20, atk=20, def_=1, matk=0, mdef=0,
        mov=3, mp=3, x=1, y=0, skills=[],
    )
    db_session.add_all([attacker, target])
    await db_session.flush()
    db_session.add_all([
        Tile(game_id=game.id, x=0, y=0, terrain="plain", occupied_unit_id=attacker.id),
        Tile(game_id=game.id, x=1, y=0, terrain="plain", occupied_unit_id=target.id),
    ])
    await db_session.flush()
    return game, attacker_player, defender_player, attacker, target


def _hit(damage):
    return DamageResult(
        damage=damage, is_crit=False, is_kill=False,
        effective_atk=damage, defense_total=0,
    )


@pytest.mark.asyncio
async def test_attack_kill_scores_killer_and_casualty_once(db_session, monkeypatch):
    game, killer, casualty, attacker, target = await _combat(db_session)
    monkeypatch.setattr("app.routes.actions.attack_with_double_strike", lambda *a, **k: [_hit(5)])

    await attack(game.id, AttackRequest(
        player_id=killer.id, attacker_id=attacker.id, target_id=target.id,
    ), db_session)
    killer_id, casualty_id = killer.id, casualty.id
    await db_session.commit()
    db_session.expire_all()

    assert (await db_session.get(Player, killer_id)).co_state["meter"] == 3
    assert (await db_session.get(Player, casualty_id)).co_state["meter"] == 2


@pytest.mark.asyncio
async def test_counter_kill_scores_counterattacker_without_duplicate_death(db_session, monkeypatch):
    game, casualty, killer, attacker, target = await _combat(
        db_session, attacker_hp=3, target_hp=20,
    )
    target.unit_type = "swordsman"  # melee defender can counter at distance 1
    damages = iter((1, 10))
    monkeypatch.setattr(
        "app.routes.actions.attack_with_double_strike",
        lambda *a, **k: [_hit(next(damages))],
    )

    await attack(game.id, AttackRequest(
        player_id=casualty.id, attacker_id=attacker.id, target_id=target.id,
    ), db_session)

    assert killer.co_state["meter"] == 2  # swordsman kill
    assert casualty.co_state["meter"] == 2  # one death, no kill credit


@pytest.mark.asyncio
async def test_bulk_cleanup_scores_each_unique_dead_unit_once(db_session):
    game, _other, casualty, first, second = await _combat(db_session)
    game.status = "finished"
    first.player_id = casualty.id
    first.hp = second.hp = 0

    await cleanup_dead_units(db_session, [first, second, first])
    await db_session.flush()

    assert casualty.co_state["meter"] == 4
    remaining = (await db_session.execute(
        select(Unit.id).where(Unit.id.in_([first.id, second.id]))
    )).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_cleanup_same_orm_unit_twice_before_flush_scores_death_once(db_session):
    game, _other, casualty, dead, _alive = await _combat(db_session)
    game.status = "finished"
    dead.player_id = casualty.id
    dead.hp = 0

    assert await cleanup_dead_units(db_session, [dead]) == [dead.id]
    assert await cleanup_dead_units(db_session, [dead]) == []

    assert casualty.co_state["meter"] == 2
    assert list(db_session.deleted).count(dead) == 1


@pytest.mark.asyncio
async def test_attack_without_commander_does_not_accumulate_meter(db_session, monkeypatch):
    game, attacker_player, defender_player, attacker, target = await _combat(db_session)
    attacker_player.commander_id = None
    defender_player.commander_id = None
    monkeypatch.setattr("app.routes.actions.attack_with_double_strike", lambda *a, **k: [_hit(5)])

    await attack(game.id, AttackRequest(
        player_id=attacker_player.id, attacker_id=attacker.id, target_id=target.id,
    ), db_session)

    assert attacker_player.co_state["meter"] == 0
    assert defender_player.co_state["meter"] == 0
