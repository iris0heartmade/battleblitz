"""沉默领域 (鸢影 P+) — 沉默状态系统集成测试。

silence_until_turn 字段已废弃,所有 silence 状态读 status_effects。
本文件覆盖:
- apply_silence_aura:5×5 区域选择、非同 team、只 magic 单位、cap 取最长
- is_unit_silenced:基本工具(只读 status_effects)
- fire_co_power(silence_radius > 0) 触发 apply_silence_aura
- on_player_turn_start 通过 tick_effects_at_turn_start 清空过期沉默
- routes/actions.py:attack / counter 在 silence 时拒绝
- 2v2 / FFA team mode:同 team_id 的友军魔法单位不被沉默
- clear_expired_silences 现在是 no-op(兼容入口)
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.classes.units import get as get_unit_class
from app.commanders.effects import (
    apply_silence_aura,
    clear_expired_silences,
    fire_co_power,
    is_unit_silenced,
)
from app.commanders.meter import _ensure_co_state
from app.models import Game, Player, Unit


def _mk_unit(unit_id: int, owner_id: int, x: int, y: int, *, type_id="warlock", team_id=None):
    """构造一个 SimpleNamespace 模拟 Unit,带 status_effects list。"""
    return SimpleNamespace(
        id=unit_id,
        player_id=owner_id,
        unit_type=type_id,
        x=x, y=y,
        hp=20,
        status_effects=[],
        team_id=team_id,
    )


def _silenced(unit) -> bool:
    return any(
        isinstance(e, dict) and e.get("type") == "silence"
        for e in (getattr(unit, "status_effects", []) or [])
    )


def _silence_remaining(unit) -> int:
    for e in (getattr(unit, "status_effects", []) or []):
        if isinstance(e, dict) and e.get("type") == "silence":
            return int(e.get("remaining_turns", 0))
    return 0


def test_apply_silence_aura_silences_enemy_magic_units_in_5x5():
    """沉默领域 5×5:非同 team + magic 单位被沉默。"""
    owner = SimpleNamespace(id=1)
    enemy_warlock = _mk_unit(101, owner_id=2, x=5, y=5)             # 中心 ±2 内,magic
    enemy_archer = _mk_unit(102, owner_id=2, x=6, y=5, type_id="archer")  # 中心 ±2 内,physical
    ally_warlock = _mk_unit(103, owner_id=1, x=5, y=5)             # 5×5 内,但 owner 同 team
    far_enemy = _mk_unit(104, owner_id=2, x=20, y=20)              # 5×5 外
    dead_enemy = _mk_unit(105, owner_id=2, x=5, y=5)              # 5×5 内 + magic,但 hp=0
    dead_enemy.hp = 0
    units = [enemy_warlock, enemy_archer, ally_warlock, far_enemy, dead_enemy]

    silenced = apply_silence_aura(
        units,
        center_xy=(5, 5),
        radius=2,
        duration_turns=1,
        current_turn=3,
        owner_player_id=owner.id,
    )

    assert silenced == [enemy_warlock]
    assert _silenced(enemy_warlock)
    assert _silence_remaining(enemy_warlock) == 1
    assert not _silenced(enemy_archer)
    assert not _silenced(ally_warlock)
    assert not _silenced(far_enemy)
    assert not _silenced(dead_enemy)


def test_apply_silence_aura_takes_max_existing_remaining():
    """如果单位已被沉默更长时间,不要缩短。"""
    owner = SimpleNamespace(id=1)
    u = _mk_unit(201, owner_id=2, x=5, y=5)
    # 预存一个 remaining=5 的 silence
    u.status_effects = [{"type": "silence", "remaining_turns": 5, "applied_turn": 0, "params": {}}]
    units = [u]

    apply_silence_aura(
        units, center_xy=(5, 5), radius=2,
        duration_turns=1, current_turn=3, owner_player_id=owner.id,
    )
    # 已有的 5 大于新加的 1 → 保留 5
    assert _silence_remaining(u) == 5


def test_apply_silence_aura_5x5_square_boundary():
    """边界:中心 (5,5) 半径 2 = x ∈ [3,7] y ∈ [3,7]"""
    owner = SimpleNamespace(id=1)
    inside_edge = _mk_unit(1, owner_id=2, x=3, y=5)
    outside_one = _mk_unit(2, owner_id=2, x=2, y=5)
    outside_two = _mk_unit(3, owner_id=2, x=8, y=5)
    units = [inside_edge, outside_one, outside_two]
    silenced = apply_silence_aura(
        units, center_xy=(5, 5), radius=2,
        duration_turns=1, current_turn=1, owner_player_id=owner.id,
    )
    assert silenced == [inside_edge]
    assert not _silenced(outside_one)
    assert not _silenced(outside_two)


def test_is_unit_silenced_basic():
    """is_unit_silenced 只读 status_effects;无 silence entry → False。"""
    u = _mk_unit(1, owner_id=2, x=0, y=0)
    assert not is_unit_silenced(u, current_turn=5)
    u.status_effects = [{"type": "silence", "remaining_turns": 2, "applied_turn": 0, "params": {}}]
    assert is_unit_silenced(u, current_turn=5)
    assert is_unit_silenced(u, current_turn=99)


def test_clear_expired_silences_is_noop():
    """clear_expired_silences 现在是 no-op 兼容入口,返回 0。"""
    u1 = _mk_unit(1, owner_id=2, x=0, y=0)
    u1.status_effects = [{"type": "silence", "remaining_turns": 1, "applied_turn": 0, "params": {}}]
    cleared = clear_expired_silences([u1], current_turn=5)
    assert cleared == 0
    # 不应清掉 status_effects 里的 silence(由 on_player_turn_start → tick 来清)
    assert _silence_remaining(u1) == 1


def test_apply_silence_aura_noop_when_radius_zero():
    """radius=0 时不做任何事。"""
    owner = SimpleNamespace(id=1)
    u = _mk_unit(1, owner_id=2, x=5, y=5)
    silenced = apply_silence_aura(
        [u], center_xy=(5, 5), radius=0,
        duration_turns=1, current_turn=1, owner_player_id=owner.id,
    )
    assert silenced == []
    assert not _silenced(u)


def test_fire_co_power_yuanying_triggers_silence_aura():
    """fire_co_power + silence_radius=2 → 调 apply_silence_aura。"""
    from app.classes.heroes import get as get_hero

    yuanying = get_hero("yuanying")
    assert yuanying.commander_power.silence_radius == 2

    owner = SimpleNamespace(id=1)
    target = _mk_unit(101, owner_id=2, x=5, y=5)  # magic 单位
    unit_list = [target]
    player = SimpleNamespace(
        id=owner.id,
        commander_id="yuanying",
        units=[],
        co_state={
            "commander_id": "yuanying",
            "threshold": 16,
            "stars_earned_total": 18,
            "power_cost": 6,
            "is_power_active": False,
        },
    )

    fire_co_power(
        player,
        center_xy=(5, 5),
        current_turn=3,
        all_units=unit_list,
    )
    assert _silenced(target)
    assert _silence_remaining(target) == 1
    assert player.co_state["stars_earned_total"] == 12  # 18 - 6
    assert player.co_state["is_power_active"] is True


def test_fire_co_power_requires_center_for_silence_radius():
    """yuanying (silence_radius=2) 放 power 但没传 center_xy → raise。"""
    from app.classes.heroes import get as get_hero
    yuanying = get_hero("yuanying")
    player = SimpleNamespace(
        id=1,
        commander_id="yuanying",
        units=[],
        co_state={"commander_id": "yuanying", "stars_earned_total": 18,
                  "threshold": 16, "power_cost": 6, "is_power_active": False},
    )
    with pytest.raises(ValueError, match="requires center_xy"):
        fire_co_power(player, current_turn=3, all_units=[])


def test_fire_co_power_yun_no_silence_works_without_center():
    """yun 没有 silence_radius,允许不传 center_xy。"""
    player = SimpleNamespace(
        id=1,
        commander_id="yun",
        units=[],
        co_state={"commander_id": "yun", "stars_earned_total": 18,
                  "threshold": 18, "power_cost": 6, "is_power_active": False},
    )
    fire_co_power(player)
    assert player.co_state["is_power_active"] is True


@pytest.mark.asyncio
async def test_silenced_unit_cannot_attack_via_endpoint(db_session, monkeypatch):
    """routes/actions.py:attack 端点在 silence 时拒绝(主攻击)。"""
    from app.game_logic import DamageResult
    from app.models import Tile
    from app.routes.actions import attack
    from app.schemas import AttackRequest

    game = Game(name="sil", status="playing", map_seed=1, win_condition="defend")
    db_session.add(game)
    await db_session.flush()

    p1 = Player(game_id=game.id, user_name="a", color="red", seat=0,
                commander_id="yun",
                co_state={"stars_earned_total": 0, "threshold": 18, "power_cost": 6})
    p2 = Player(game_id=game.id, user_name="b", color="blue", seat=1)
    db_session.add_all([p1, p2])
    await db_session.flush()

    attacker = Unit(player_id=p1.id, unit_type="warlock", name="A",
                    hp=20, max_hp=20, atk=20, def_=1, matk=20, mdef=1,
                    mov=3, mp=3, x=0, y=0, skills=[],
                    status_effects=[{"type": "silence", "remaining_turns": 3,
                                     "applied_turn": 0, "applied_by": None, "params": {}}])
    target = Unit(player_id=p2.id, unit_type="archer", name="T",
                  hp=20, max_hp=20, atk=20, def_=1, matk=0, mdef=0,
                  mov=3, mp=3, x=1, y=0, skills=[])
    db_session.add_all([attacker, target])
    await db_session.flush()
    db_session.add_all([
        Tile(game_id=game.id, x=0, y=0, terrain="plain", occupied_unit_id=attacker.id),
        Tile(game_id=game.id, x=1, y=0, terrain="plain", occupied_unit_id=target.id),
    ])
    await db_session.flush()

    monkeypatch.setattr(
        "app.routes.actions.attack_with_double_strike",
        lambda *a, **k: [DamageResult(damage=10, is_crit=False, is_kill=False,
                                     effective_atk=10, defense_total=0)],
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await attack(game.id, AttackRequest(
            player_id=p1.id, attacker_id=attacker.id, target_id=target.id,
        ), db_session)
    assert "silenced" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_on_player_turn_start_ticks_silence_to_zero(db_session):
    """on_player_turn_start 调 tick_effects_at_turn_start → remaining=0 自动过期。"""
    from app.commanders.effects import on_player_turn_start

    game = Game(name="cl", status="playing", map_seed=1, win_condition="defend",
                turn_number=2)
    db_session.add(game)
    await db_session.flush()
    p1 = Player(game_id=game.id, user_name="a", color="red", seat=0,
                commander_id="yun",
                co_state={
                    "commander_id": "yun", "threshold": 18, "power_cost": 6,
                    "stars_earned_total": 0, "last_start_turn": 1,
                    "is_power_active": False, "meter": 0,
                })
    db_session.add(p1)
    await db_session.flush()

    u1 = Unit(player_id=p1.id, unit_type="warlock", name="A",
              hp=20, max_hp=20, atk=20, def_=1, matk=20, mdef=1,
              mov=3, mp=3, x=0, y=0, skills=[],
              status_effects=[{"type": "silence", "remaining_turns": 1,
                               "applied_turn": 0, "applied_by": None, "params": {}}])
    u2 = Unit(player_id=p1.id, unit_type="warlock", name="B",
              hp=20, max_hp=20, atk=20, def_=1, matk=20, mdef=1,
              mov=3, mp=3, x=1, y=0, skills=[],
              status_effects=[{"type": "silence", "remaining_turns": 5,
                               "applied_turn": 0, "applied_by": None, "params": {}}])
    db_session.add_all([u1, u2])
    await db_session.flush()
    await db_session.refresh(p1, ["units"])

    # game_turn_number=2 > last_start_turn=1 → 进 tick 分支
    on_player_turn_start(p1, 2, all_units=[u1, u2])
    await db_session.commit()
    await db_session.refresh(u1)
    await db_session.refresh(u2)
    # u1 remaining 1 → 0,被清;u2 remaining 5 → 4
    assert not _silenced(u1)
    assert _silenced(u2)
    assert _silence_remaining(u2) == 4


# =========================================================================
# 2v2 / FFA team mode (M1 fix): silence aura must NOT silence allied magic
# units that share the firing player's team_id.
# =========================================================================


def test_apply_silence_aura_skips_ally_in_2v2_team_mode():
    """2v2:同 team_id 的友军魔法单位,即使不同 player_id,也不被沉默。"""
    owner = SimpleNamespace(id=1, team_id="red")
    ally_warlock = _mk_unit(201, owner_id=2, x=5, y=5, team_id="red")  # 队友
    enemy_warlock = _mk_unit(202, owner_id=3, x=5, y=5, team_id="blue")  # 敌人
    enemy2_warlock = _mk_unit(203, owner_id=4, x=5, y=5, team_id="blue")  # 敌人
    teamless_warlock = _mk_unit(204, owner_id=99, x=5, y=5, team_id=None)  # 无 team
    units = [ally_warlock, enemy_warlock, enemy2_warlock, teamless_warlock]

    silenced = apply_silence_aura(
        units,
        center_xy=(5, 5),
        radius=2,
        duration_turns=1,
        current_turn=3,
        owner_player_id=owner.id,
        owner_player=owner,
    )

    assert not _silenced(ally_warlock)
    assert _silenced(enemy_warlock)
    assert _silenced(enemy2_warlock)
    assert _silenced(teamless_warlock)  # 无 team → 不是队友 → 被沉默
    assert silenced == [enemy_warlock, enemy2_warlock, teamless_warlock]


def test_apply_silence_aura_team_filter_no_op_in_1v1():
    """1v1 模式:owner_player 没传 / 没 team_id,只按 player_id 过滤(向后兼容)。"""
    owner = SimpleNamespace(id=1)  # 无 team_id
    enemy_warlock = _mk_unit(301, owner_id=2, x=5, y=5)  # 无 team_id
    units = [enemy_warlock]

    silenced = apply_silence_aura(
        units,
        center_xy=(5, 5),
        radius=2,
        duration_turns=1,
        current_turn=1,
        owner_player_id=owner.id,
        owner_player=owner,
    )
    assert silenced == [enemy_warlock]
    assert _silenced(enemy_warlock)
    assert _silence_remaining(enemy_warlock) == 1
