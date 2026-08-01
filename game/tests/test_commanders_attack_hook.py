"""Integration regressions for commander star accrual in real combat paths.

新机制:每次击杀 +1 颗星(recorded by award_morale → record_morale_star)。
旧机制下的"杀不同 unit_type 给不同分"+"死亡 +2"路径已删除。
"""
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
        co_state={"stars_earned_total": 0, "threshold": 18, "power_cost": 6},
    )
    defender_player = Player(
        game_id=game.id, user_name="defender", color="blue", seat=1,
        commander_id="anna",
        co_state={"stars_earned_total": 0, "threshold": 14, "power_cost": 6},
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
async def test_attack_kill_grants_one_star_to_killer(db_session, monkeypatch):
    """主攻击杀:kill +1 星(不依赖 unit_type)。"""
    game, killer, casualty, attacker, target = await _combat(db_session)
    monkeypatch.setattr("app.routes.actions.attack_with_double_strike", lambda *a, **k: [_hit(5)])

    await attack(game.id, AttackRequest(
        player_id=killer.id, attacker_id=attacker.id, target_id=target_id(target),
    ), db_session)
    killer_id, casualty_id = killer.id, casualty.id
    await db_session.commit()
    db_session.expire_all()

    # 攻击方 +1 星(无论 target 类型)
    assert (await db_session.get(Player, killer_id)).co_state["stars_earned_total"] == 1
    # 旧 on_death +2 路径已删除:casualty 现在不减星
    assert (await db_session.get(Player, casualty_id)).co_state["stars_earned_total"] == 0


def target_id(target):
    return target.id


@pytest.mark.asyncio
async def test_counter_kill_grants_star_to_counterattacker(db_session, monkeypatch):
    """反击击杀:counter_player +1 星(attacker 自己不会加,因为走的是 "hit" 路径)。"""
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

    # counter_player(killer = target 的 owner) +1 星
    assert killer.co_state["stars_earned_total"] == 1
    # casualty 没杀,不会加星
    assert casualty.co_state["stars_earned_total"] == 0


@pytest.mark.asyncio
async def test_bulk_cleanup_does_not_grant_stars(db_session):
    """新机制:cleanup_dead_units 死亡路径不加分(死亡本身不进入累积槽)。"""
    game, _other, casualty, first, second = await _combat(db_session)
    game.status = "finished"
    first.player_id = casualty.id
    first.hp = second.hp = 0

    await cleanup_dead_units(db_session, [first, second, first])
    await db_session.flush()

    # 死亡不再给 +2:casualty.co_state["stars_earned_total"] 仍是 0
    assert casualty.co_state["stars_earned_total"] == 0
    remaining = (await db_session.execute(
        select(Unit.id).where(Unit.id.in_([first.id, second.id]))
    )).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_attack_without_commander_does_not_accumulate_stars(db_session, monkeypatch):
    """无指挥官玩家击杀不累加星(与 record_morale_star 行为一致)。"""
    game, attacker_player, defender_player, attacker, target = await _combat(db_session)
    attacker_player.commander_id = None
    defender_player.commander_id = None
    monkeypatch.setattr("app.routes.actions.attack_with_double_strike", lambda *a, **k: [_hit(5)])

    await attack(game.id, AttackRequest(
        player_id=attacker_player.id, attacker_id=attacker.id, target_id=target.id,
    ), db_session)

    assert attacker_player.co_state["stars_earned_total"] == 0
    assert defender_player.co_state["stars_earned_total"] == 0
