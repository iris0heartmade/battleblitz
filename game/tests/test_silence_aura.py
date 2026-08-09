"""沉默领域 (鸢影 P+) — 沉默状态系统集成测试。

覆盖:
- apply_silence_aura:5×5 区域选择、非同 team、只 magic 单位、cap 取最长
- is_unit_silenced / clear_expired_silences:基本工具
- fire_co_power(silence_radius > 0) 触发 apply_silence_aura
- on_player_turn_start 清空过期沉默(silence_duration_turns 后)
- routes/actions.py:attack / counter 在 silence 时拒绝
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
    """Construct a SimpleNamespace that mimics Unit enough for silence checks."""
    u = SimpleNamespace(
        id=unit_id,
        player_id=owner_id,
        unit_type=type_id,
        x=x, y=y,
        hp=20,
        silence_until_turn=0,
        team_id=team_id,
    )
    return u


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
    assert enemy_warlock.silence_until_turn == 4
    assert enemy_archer.silence_until_turn == 0
    assert ally_warlock.silence_until_turn == 0
    assert far_enemy.silence_until_turn == 0
    assert dead_enemy.silence_until_turn == 0


def test_apply_silence_aura_takes_max_existing_until():
    """如果单位已被沉默更长时间,不要缩短。"""
    owner = SimpleNamespace(id=1)
    u = _mk_unit(201, owner_id=2, x=5, y=5)
    u.silence_until_turn = 10  # 已沉默到 turn 10
    units = [u]

    apply_silence_aura(
        units, center_xy=(5, 5), radius=2,
        duration_turns=1, current_turn=3, owner_player_id=owner.id,
    )
    # expire_at = 3 + 1 = 4,小于已有的 10,保留 10
    assert u.silence_until_turn == 10


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
    assert outside_one.silence_until_turn == 0
    assert outside_two.silence_until_turn == 0


def test_is_unit_silenced_basic():
    """silence_until_turn=N 含义:沉默持续到 turn N 结束。turn N 开始时已解除。"""
    u = _mk_unit(1, owner_id=2, x=0, y=0)
    assert not is_unit_silenced(u, current_turn=5)
    u.silence_until_turn = 6
    assert is_unit_silenced(u, current_turn=5)         # 仍沉默
    assert not is_unit_silenced(u, current_turn=6)      # turn 6 开始 → 解除
    assert not is_unit_silenced(u, current_turn=7)


def test_clear_expired_silences():
    u1 = _mk_unit(1, owner_id=2, x=0, y=0)
    u1.silence_until_turn = 5
    u2 = _mk_unit(2, owner_id=2, x=1, y=1)
    u2.silence_until_turn = 7
    u3 = _mk_unit(3, owner_id=2, x=2, y=2)
    # u3 未沉默

    cleared = clear_expired_silences([u1, u2, u3], current_turn=5)
    assert cleared == 1
    assert u1.silence_until_turn == 0  # 5 <= 5 清空
    assert u2.silence_until_turn == 7  # 7 > 5 保留
    assert u3.silence_until_turn == 0  # 仍是 0


def test_apply_silence_aura_noop_when_radius_zero():
    """radius=0 时不做任何事。"""
    owner = SimpleNamespace(id=1)
    u = _mk_unit(1, owner_id=2, x=5, y=5)
    silenced = apply_silence_aura(
        [u], center_xy=(5, 5), radius=0,
        duration_turns=1, current_turn=1, owner_player_id=owner.id,
    )
    assert silenced == []
    assert u.silence_until_turn == 0


def test_fire_co_power_yuanying_triggers_silence_aura():
    """fire_co_power + silence_radius=2 → 调 apply_silence_aura。"""
    # 模拟玩家:yun(yun power 是 atk_pct,无 silence),yuanying(silence_radius=2)
    # 这里测 yuanying 路径
    from app.classes.heroes import get as get_hero

    yuanying = get_hero("yuanying")
    assert yuanying.commander_power.silence_radius == 2

    # 构造玩家 + 单位
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
    assert target.silence_until_turn == 4  # 3 + 1
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
    # 不传 center / all_units 也 OK
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
                    silence_until_turn=10)  # 沉默到 turn 10
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

    # current_turn 默认 0,attacker.silence_until_turn=10 > 0 → 沉默
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await attack(game.id, AttackRequest(
            player_id=p1.id, attacker_id=attacker.id, target_id=target.id,
        ), db_session)
    assert "silenced" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_on_player_turn_start_clears_expired_silence(db_session):
    """on_player_turn_start 时 silence_until_turn <= current_turn → 清空。"""
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
              silence_until_turn=2)
    u2 = Unit(player_id=p1.id, unit_type="warlock", name="B",
              hp=20, max_hp=20, atk=20, def_=1, matk=20, mdef=1,
              mov=3, mp=3, x=1, y=0, skills=[],
              silence_until_turn=10)
    db_session.add_all([u1, u2])
    await db_session.flush()
    await db_session.refresh(p1, ["units"])

    # game_turn_number=2 > last_start_turn=1 → 进 clear 分支
    # silence_until_turn <= 2 的清空(u1),10 的保留(u2)
    on_player_turn_start(p1, 2, all_units=[u1, u2])
    await db_session.commit()  # 持久化 silence_until_turn 改动
    await db_session.refresh(u1)
    await db_session.refresh(u2)
    assert u1.silence_until_turn == 0
    assert u2.silence_until_turn == 10


# =========================================================================
# 2v2 / FFA team mode (M1 fix): silence aura must NOT silence allied magic
# units that share the firing player's team_id.
# =========================================================================


def test_apply_silence_aura_skips_ally_in_2v2_team_mode():
    """2v2:同 team_id 的友军魔法单位,即使不同 player_id,也不被沉默。"""
    # 玩家 1 是 owner(player_id=1, team_id="red"),
    # 玩家 2 是同 team("red", 队友),玩家 3 / 4 是对方 team("blue")。
    owner = SimpleNamespace(id=1, team_id="red")
    ally_warlock = _mk_unit(201, owner_id=2, x=5, y=5, team_id="red")  # 队友
    enemy_warlock = _mk_unit(202, owner_id=3, x=5, y=5, team_id="blue")  # 敌人
    enemy2_warlock = _mk_unit(203, owner_id=4, x=5, y=5, team_id="blue")  # 敌人
    teamless_warlock = _mk_unit(204, owner_id=99, x=5, y=5, team_id=None)  # 无 team(不应当作队友)
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

    # ally 不沉默,teamless 被沉默(因为他不是队友),两个 enemy 被沉默
    assert ally_warlock.silence_until_turn == 0
    assert enemy_warlock.silence_until_turn == 4
    assert enemy2_warlock.silence_until_turn == 4
    assert teamless_warlock.silence_until_turn == 4
    assert silenced == [enemy_warlock, enemy2_warlock, teamless_warlock]


def test_apply_silence_aura_team_filter_no_op_in_1v1():
    """1v1 模式:owner_player 没传 / 没 team_id,只按 player_id 过滤(向后兼容)。"""
    # 1v1 玩家(无 team_id),owner_player=None 时也应当 work
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
    assert enemy_warlock.silence_until_turn == 2
