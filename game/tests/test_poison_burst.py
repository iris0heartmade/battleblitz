"""Poison Burst skill 测试 — 第一个走通用 status_effects 框架的主动 skill.

覆盖:
- 自动发现 / 注册表:poison_burst 在 list_all() 里、skill_id 一致、默认 warlock 学会
- can_use:target 必填 / 友军禁 / 距离 1-2 / MP ≥ 2 / 跳过死者
- describe:含目标名 + 持续回合数
- execute:add_effect 写 poison + mp -= 2 + has_acted=True
- 累加:同 type 已有 poison → remaining 取 max,applied_turn 更新
- SkillContext.game_turn_number:applied_turn 字段与 ctx 同步
- 副作用不影响其他 skill(heal/arcane_strike 仍 mp=0)
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.classes.units.skills import (
    default_skills_for,
    get,
    get_active_for,
    list_all,
)
from app.classes.units.skills.base import SkillContext


# ============================================================
# Helper
# ============================================================

def _mk_unit(*, unit_id=1, player_id=1, x=0, y=0, hp=20, mp=8, status_effects=None):
    return SimpleNamespace(
        id=unit_id, player_id=player_id, unit_type="warlock",
        name=f"U{unit_id}", level=1, exp=0,
        hp=hp, max_hp=20, atk=8, def_=10,
        matk=22, mdef=12, mov=3, mp=mp,
        morale=0, x=x, y=y, has_acted=False, has_moved=False,
        skills=["poison_burst"],
        attack_range=2, min_attack_range=0,
        status_effects=list(status_effects or []),
        silence_until_turn=0,
    )


def _mk_ctx(*, user=None, target=None, game_turn_number=5):
    if user is None:
        user = _mk_unit(player_id=1, x=0, y=0, mp=8)
    # NB: do NOT default `target` to a non-None unit — caller's explicit
    # None must survive so we can test "no target" branches.
    if target is None and False:  # sentinel disabled to keep explicit None
        target = _mk_unit(unit_id=2, player_id=2, x=1, y=0, hp=20)
    return SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target] if target else [],
        game_turn_number=game_turn_number,
    )


def _run(coro):
    """简化 async 入口(测试无 session 依赖时直接 run)。

    用 ``asyncio.run`` 而不是 ``get_event_loop().run_until_complete`` —
    后者在 pytest-asyncio 跑过 fixture 关闭 loop 后会抛
    ``RuntimeError: There is no current event loop``。
    ``asyncio.run`` 每次新建 loop,跑完关闭,与外部状态解耦。
    """
    return asyncio.run(coro)


# ============================================================
# 注册 / 默认用户
# ============================================================

def test_poison_burst_appears_in_registry():
    all_skills = list_all()
    ids = [sk.skill_id for sk in all_skills]
    assert "poison_burst" in ids


def test_poison_burst_is_active_skill():
    sk = get("poison_burst")
    assert sk.is_passive is False
    assert sk.skill_id == "poison_burst"
    assert sk.display_cn == "剧毒迸发"


def test_warlock_defaults_to_poison_burst():
    sk_ids = default_skills_for("warlock")
    assert "poison_burst" in sk_ids


def test_get_active_for_includes_poison_burst_when_unit_has_it():
    u = _mk_unit()
    actives = get_active_for(u)
    assert any(sk.skill_id == "poison_burst" for sk in actives)


def test_get_active_for_excludes_when_unit_lacks_it():
    u = _mk_unit()
    u.skills = ["snipe"]
    actives = get_active_for(u)
    assert all(sk.skill_id != "poison_burst" for sk in actives)


# ============================================================
# can_use 边界
# ============================================================

def test_can_use_requires_target():
    sk = get("poison_burst")
    ctx = _mk_ctx(target=None)
    assert sk.can_use(ctx) is False


def test_can_use_rejects_ally():
    sk = get("poison_burst")
    user = _mk_unit(player_id=1, x=0, y=0, mp=8)
    ally = _mk_unit(unit_id=2, player_id=1, x=1, y=0)  # 同 team
    ctx = SkillContext(
        user=user, target=ally,
        ally_units=[user, ally], enemy_units=[],
        game_turn_number=1,
    )
    assert sk.can_use(ctx) is False


def test_can_use_rejects_dead_target():
    sk = get("poison_burst")
    target = _mk_target(hp=0)
    ctx = _mk_ctx(target=target)
    assert sk.can_use(ctx) is False


def test_can_use_rejects_out_of_range():
    sk = get("poison_burst")
    user = _mk_unit(x=0, y=0, mp=8)
    far = _mk_unit(unit_id=2, player_id=2, x=5, y=5, hp=20)
    ctx = SkillContext(
        user=user, target=far,
        ally_units=[user], enemy_units=[far],
        game_turn_number=1,
    )
    assert sk.can_use(ctx) is False


def test_can_use_rejects_when_mp_below_cost():
    sk = get("poison_burst")
    user = _mk_unit(x=0, y=0, mp=1)  # < 2
    target = _mk_unit(unit_id=2, player_id=2, x=1, y=0)
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=1,
    )
    assert sk.can_use(ctx) is False


def test_can_use_approves_at_boundary():
    """距离 = 2(最大) + mp = 2(刚好) → 通过。"""
    sk = get("poison_burst")
    user = _mk_unit(x=0, y=0, mp=2)
    target = _mk_unit(unit_id=2, player_id=2, x=2, y=0)
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=1,
    )
    assert sk.can_use(ctx) is True


def _mk_target(*, unit_id=2, player_id=2, x=1, y=0, hp=20, mp=8, max_hp=20):
    u = _mk_unit(unit_id=unit_id, player_id=player_id, x=x, y=y, hp=hp, mp=mp)
    u.max_hp = max_hp
    return u


# ============================================================
# describe
# ============================================================

def test_describe_includes_target_name_and_turns():
    sk = get("poison_burst")
    target = _mk_target()
    ctx = _mk_ctx(target=target)
    desc = sk.describe(ctx)
    assert "剧毒迸发" in desc
    assert "U2" in desc  # target.name 前 4 字符
    assert "3" in desc   # POISON_TURNS


def test_describe_without_target_falls_back_to_skill_name():
    sk = get("poison_burst")
    desc = sk.describe(SkillContext(
        user=_mk_unit(), target=None,
        ally_units=[], enemy_units=[],
        game_turn_number=1,
    ))
    assert "剧毒迸发" in desc


# ============================================================
# execute:写 status_effects + drain MP + has_acted
# ============================================================

def test_execute_writes_poison_status_effect():
    sk = get("poison_burst")
    user = _mk_unit(mp=8)
    target = _mk_target(hp=20)
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=7,
    )

    result = _run(sk.execute(session=None, ctx=ctx))

    assert result.ok is True
    assert result.affected_units == [target.id]
    # poison 已被 add_effect 写入
    assert len(target.status_effects) == 1
    eff = target.status_effects[0]
    assert eff["type"] == "poison"
    assert eff["remaining_turns"] == 3
    assert eff["applied_turn"] == 7  # ctx.game_turn_number
    assert eff["applied_by"] == user.player_id


def test_execute_drains_mp_by_cost_not_zero():
    """poison_burst 用 mp -= 2(部分消耗),而非 heal/arcane_strike 的 mp=0。"""
    sk = get("poison_burst")
    user = _mk_unit(mp=8)
    target = _mk_target()
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=1,
    )

    _run(sk.execute(session=None, ctx=ctx))

    assert user.mp == 6  # 8 - 2


def test_execute_marks_has_acted():
    sk = get("poison_burst")
    user = _mk_unit(mp=8)
    target = _mk_target()
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=1,
    )
    assert user.has_acted is False

    _run(sk.execute(session=None, ctx=ctx))

    assert user.has_acted is True


def test_execute_stacks_remaining_when_already_poisoned():
    """add_effect 已实现累加:同 type 取 max(remaining) + 更新 applied_turn。"""
    sk = get("poison_burst")
    user = _mk_unit(mp=8)
    target = _mk_target(hp=20)
    target.status_effects = [{
        "type": "poison", "remaining_turns": 2,
        "applied_turn": 1, "applied_by": 3,
        "params": {"dmg_pct": 0.05},
    }]
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=10,
    )

    _run(sk.execute(session=None, ctx=ctx))

    assert len(target.status_effects) == 1
    eff = target.status_effects[0]
    assert eff["remaining_turns"] == 3  # max(2, 3)
    assert eff["applied_turn"] == 10   # 最新覆盖
    assert eff["applied_by"] == user.player_id


def test_execute_mp_floor_at_zero():
    """mp < MP_COST 仍走 max(0, ...)(安全垫,正常路径已被 can_use 拦)。"""
    sk = get("poison_burst")
    user = _mk_unit(mp=1)  # 强制绕过 can_use,直接 execute
    target = _mk_target()
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=1,
    )

    _run(sk.execute(session=None, ctx=ctx))

    assert user.mp == 0  # max(0, 1 - 2)


# ============================================================
# 端到端 tick:execute 后 turn_start 真的会扣 HP
# ============================================================

def test_poison_burst_then_tick_damages_target():
    """完整链路:execute 写 poison → tick_effects_at_turn_start 扣 HP + 倒计时。"""
    from app.status import tick_effects_at_turn_start

    sk = get("poison_burst")
    user = _mk_unit(mp=8)
    target = _mk_target(hp=20, max_hp=20)
    ctx = SkillContext(
        user=user, target=target,
        ally_units=[user], enemy_units=[target],
        game_turn_number=5,
    )

    _run(sk.execute(session=None, ctx=ctx))
    assert target.hp == 20  # 施加瞬间不扣血

    # 受害方回合开始:扣 5% max_hp = 1 HP,remaining 减到 2
    tick_effects_at_turn_start(target, game_turn_number=6)
    assert target.hp == 19
    assert target.status_effects[0]["remaining_turns"] == 2


# ============================================================
# 隔离:不污染其他 skill
# ============================================================

def test_other_skills_unaffected_by_poison_burst_changes():
    """回归保护:heal/arcane_strike 仍是 mp=0,poison_burst 是 mp -= 2。"""
    heal = get("heal")
    arcane = get("arcane_strike")
    poison = get("poison_burst")
    # mp 行为差异
    assert poison.MP_COST == 2
    # heal/arcane_strike 没有 MP_COST 常量(它们走 mp=0)
    assert not hasattr(heal, "MP_COST")
    assert not hasattr(arcane, "MP_COST")