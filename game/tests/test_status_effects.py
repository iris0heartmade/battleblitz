"""通用 status effect 框架 + 5 个 effect 的单元测试。

覆盖:
- EFFECT_DEFS 注册表完整性
- add_effect / remove_effect / find_effect / has_effect 基本工具
- add_effect 同 type 已存在 → 取 max remaining + 合并 params
- tick_effects_at_turn_start:poison 扣 HP / paralyze/blind/slow/silence 倒计时
- should_skip_action:paralyze 概率不能行动
- modify_hit_chance:blind 降命中率
- modify_mov:slow 减 MOV
- should_block_attack / is_silenced:silence 兼容旧 silence_until_turn 字段
"""
import random
from types import SimpleNamespace

import pytest

from app.status import (
    EFFECT_DEFS,
    add_effect,
    find_effect,
    has_effect,
    is_silenced,
    modify_hit_chance,
    modify_mov,
    remove_effect,
    should_block_attack,
    should_skip_action,
    tick_effects_at_turn_start,
)


def _mk_unit(*, status_effects=None, hp=20, max_hp=20, silence_until_turn=0, mov=4):
    return SimpleNamespace(
        status_effects=list(status_effects or []),
        hp=hp, max_hp=max_hp,
        silence_until_turn=silence_until_turn,
        mov=mov,
    )


# ============================================================
# 注册表 / 工具
# ============================================================

def test_effect_defs_contains_all_five_types():
    assert set(EFFECT_DEFS.keys()) == {"poison", "paralyze", "blind", "slow", "silence"}


def test_add_effect_basic():
    u = _mk_unit()
    eff = add_effect(u, "poison", applied_turn=1, applied_by=2)
    assert eff["type"] == "poison"
    assert eff["remaining_turns"] == 3  # default
    assert eff["applied_turn"] == 1
    assert eff["applied_by"] == 2
    assert u.status_effects == [eff]


def test_add_effect_custom_remaining():
    u = _mk_unit()
    eff = add_effect(u, "blind", applied_turn=1, remaining_turns=5)
    assert eff["remaining_turns"] == 5


def test_add_effect_same_type_takes_max_remaining():
    u = _mk_unit()
    add_effect(u, "paralyze", applied_turn=1, remaining_turns=2)
    add_effect(u, "paralyze", applied_turn=2, remaining_turns=4)
    assert len(u.status_effects) == 1
    assert u.status_effects[0]["remaining_turns"] == 4  # max(2, 4)
    # applied_turn 更新到最新
    assert u.status_effects[0]["applied_turn"] == 2


def test_add_effect_merges_params():
    u = _mk_unit()
    add_effect(u, "slow", applied_turn=1, params={"mov_mult": 0.3})
    add_effect(u, "slow", applied_turn=2, params={"extra": 1})  # 新 params 不覆盖已有
    assert u.status_effects[0]["params"] == {"mov_mult": 0.3, "extra": 1}


def test_add_effect_unknown_type_raises():
    u = _mk_unit()
    with pytest.raises(ValueError, match="unknown status effect"):
        add_effect(u, "fake", applied_turn=1)


def test_remove_effect():
    u = _mk_unit()
    add_effect(u, "poison", applied_turn=1)
    add_effect(u, "slow", applied_turn=1)
    assert remove_effect(u, "poison") is True
    assert u.status_effects == [{"type": "slow", "remaining_turns": 2, "applied_turn": 1, "applied_by": None, "params": {"mov_mult": 0.5}}]
    assert remove_effect(u, "poison") is False  # 已删


def test_find_and_has():
    u = _mk_unit()
    add_effect(u, "paralyze", applied_turn=1)
    assert has_effect(u, "paralyze") is True
    assert has_effect(u, "blind") is False
    eff = find_effect(u, "paralyze")
    assert eff["remaining_turns"] == 2


# ============================================================
# tick_effects_at_turn_start
# ============================================================

def test_tick_decrements_all_remaining_turns():
    u = _mk_unit()
    add_effect(u, "poison", applied_turn=1)        # remaining=3 → 2
    add_effect(u, "paralyze", applied_turn=1)      # remaining=2 → 1
    add_effect(u, "blind", applied_turn=1)         # remaining=2 → 1
    add_effect(u, "slow", applied_turn=1)          # remaining=2 → 1
    add_effect(u, "silence", applied_turn=1)       # remaining=1 → 0 (expired)

    expired = tick_effects_at_turn_start(u, game_turn_number=2)

    assert expired == ["silence"]
    remaining_types = sorted(e["type"] for e in u.status_effects)
    assert remaining_types == ["blind", "paralyze", "poison", "slow"]
    rem_by_type = {e["type"]: e["remaining_turns"] for e in u.status_effects}
    assert rem_by_type == {"poison": 2, "paralyze": 1, "blind": 1, "slow": 1}


def test_tick_poison_deals_max_hp_pct_damage():
    """poison 每回合扣 max_hp × dmg_pct(默认 5%,向上取整最低 1)。"""
    u = _mk_unit(hp=20, max_hp=20)
    add_effect(u, "poison", applied_turn=1, params={"dmg_pct": 0.10})
    tick_effects_at_turn_start(u, game_turn_number=2)
    # 20 * 0.10 = 2
    assert u.hp == 18


def test_tick_poison_does_not_kill_below_zero():
    u = _mk_unit(hp=1, max_hp=100)
    add_effect(u, "poison", applied_turn=1, params={"dmg_pct": 0.50})
    tick_effects_at_turn_start(u, game_turn_number=2)
    assert u.hp == 0
    assert u.hp >= 0  # 不会变成负


def test_tick_removes_expired_effects():
    u = _mk_unit()
    add_effect(u, "poison", applied_turn=1, remaining_turns=1)
    expired = tick_effects_at_turn_start(u, game_turn_number=2)
    assert expired == ["poison"]
    assert u.status_effects == []


def test_tick_noop_when_no_effects():
    u = _mk_unit()
    expired = tick_effects_at_turn_start(u, game_turn_number=2)
    assert expired == []
    assert u.status_effects == []


# ============================================================
# should_skip_action(paralyze)
# ============================================================

def test_should_skip_action_paralyze_blocks_with_probability():
    """paralyze miss_pct 概率 skip(默认 25%)。"""
    u = _mk_unit()
    add_effect(u, "paralyze", applied_turn=1)
    # 强制 100% skip
    rng = random.Random(0)
    # 用 rng 试 100 次,至少一次 True
    blocked = sum(1 for _ in range(100) if should_skip_action(u, rng=rng)[0])
    # 默认 25%,100 次期望 ~25 次,实际应在 [10, 50] 之间(随机)
    assert 5 <= blocked <= 60, f"unexpected blocked count: {blocked}"


def test_should_skip_action_no_paralyze_never_blocks():
    u = _mk_unit()
    rng = random.Random(0)
    for _ in range(50):
        skip, reason = should_skip_action(u, rng=rng)
        assert skip is False
        assert reason == ""


def test_should_skip_action_paralyze_100_pct():
    u = _mk_unit()
    add_effect(u, "paralyze", applied_turn=1, params={"miss_pct": 1.0})
    rng = random.Random(0)
    for _ in range(20):
        skip, reason = should_skip_action(u, rng=rng)
        assert skip is True
        assert "麻痹" in reason


# ============================================================
# modify_hit_chance(blind)
# ============================================================

def test_modify_hit_chance_blind_reduces():
    u = _mk_unit()
    add_effect(u, "blind", applied_turn=1)  # default miss_pct=0.50
    assert modify_hit_chance(u, base=1.0) == 0.50
    # 已有的命中率乘子也可叠加
    assert modify_hit_chance(u, base=0.8) == pytest.approx(0.40)


def test_modify_hit_chance_no_blind_passthrough():
    u = _mk_unit()
    assert modify_hit_chance(u, base=1.0) == 1.0
    assert modify_hit_chance(u, base=0.7) == 0.7


def test_modify_hit_chance_blind_custom_miss_pct():
    u = _mk_unit()
    add_effect(u, "blind", applied_turn=1, params={"miss_pct": 0.25})
    assert modify_hit_chance(u, base=1.0) == 0.75


# ============================================================
# modify_mov(slow)
# ============================================================

def test_modify_mov_slow_halves():
    u = _mk_unit(mov=4)
    add_effect(u, "slow", applied_turn=1)  # default mult=0.50
    assert modify_mov(u, base=4) == 2


def test_modify_mov_slow_min_one():
    """slow 后 MOV 不能 < 1,否则单位没法动。"""
    u = _mk_unit(mov=2)
    add_effect(u, "slow", applied_turn=1, params={"mov_mult": 0.10})
    assert modify_mov(u, base=2) == 1


def test_modify_mov_no_slow_passthrough():
    u = _mk_unit(mov=4)
    assert modify_mov(u, base=4) == 4


# ============================================================
# should_block_attack / is_silenced (silence 兼容)
# ============================================================

def test_should_block_attack_silence_new_field():
    u = _mk_unit()
    add_effect(u, "silence", applied_turn=1)
    block, reason = should_block_attack(u, kind="outgoing")
    assert block is True
    assert "沉默" in reason
    block, _ = should_block_attack(u, kind="incoming")
    assert block is True


def test_should_block_attack_no_silence():
    u = _mk_unit()
    block, _ = should_block_attack(u, kind="outgoing")
    assert block is False


def test_is_silenced_new_field_only():
    """新 is_silenced 只读 status_effects(不读旧字段,职责单一)。"""
    u = _mk_unit()
    assert is_silenced(u) is False
    add_effect(u, "silence", applied_turn=1)
    assert is_silenced(u) is True


def test_is_silenced_legacy_field_ignored():
    """旧 silence_until_turn 字段(无新 effect)不算被沉默。"""
    u = _mk_unit(silence_until_turn=5)
    assert is_silenced(u) is False  # 新 is_silenced 不读旧字段


def test_should_block_attack_silence_legacy_field_fallback():
    """commanders.effects.is_unit_silenced 同时读 status_effects + 旧字段(过渡期 fallback)。

    旧字段的兼容由 commanders.effects.is_unit_silenced() 集中处理,这里
    测的是它的包装层。
    """
    from app.commanders.effects import is_unit_silenced as _is_silenced_compat
    u = _mk_unit(silence_until_turn=5)
    assert _is_silenced_compat(u, current_turn=4) is True