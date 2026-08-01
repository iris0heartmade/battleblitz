"""CO state 存档兼容:旧档案缺新字段时回退到默认值。

新加 stars_earned_total / power_cost 字段,但旧 co_state 可能没有它们。
回退到默认值后,游戏可以继续跑,玩家能重新攒星放 power。
"""
from types import SimpleNamespace

from app.commanders import (
    can_fire_co_power, consume_power_stars, record_morale_star,
)
from app.commanders.effects import can_fire_co_power as can_fire_from_effects


def test_legacy_co_state_load_defaults_to_zero_stars():
    """旧 co_state 缺 stars_earned_total 时,record_morale_star 自动建出 0。"""
    legacy = SimpleNamespace(commander_id="yun", co_state={
        # 旧字段
        "commander_id": "yun",
        "meter": 5,  # 旧积分
        "threshold": 18,
        "is_power_active": False,
        "last_start_turn": 2,
        # 缺:stars_earned_total, power_cost
    })
    added = record_morale_star(legacy, 1)
    # 自动建出 stars_earned_total=0 然后 +1
    assert added == 1
    assert legacy.co_state["stars_earned_total"] == 1
    # power_cost 兜底
    assert legacy.co_state["power_cost"] == 6
    # 旧字段保留
    assert legacy.co_state["meter"] == 5
    assert legacy.co_state["last_start_turn"] == 2


def test_legacy_co_state_can_fire_after_reaching_cost():
    """旧档案读出来后,玩家可以从 0 颗星开始攒,攒到 6 颗就能放。"""
    legacy = SimpleNamespace(commander_id="yun", co_state={
        "commander_id": "yun",
        "meter": 0,
        "threshold": 18,
        "is_power_active": False,
        "last_start_turn": -1,
    })
    # 杀 5 个:stars 5
    for _ in range(5):
        record_morale_star(legacy, 1)
    assert legacy.co_state["stars_earned_total"] == 5
    assert can_fire_from_effects(legacy) is False
    # 第 6 个:能放
    record_morale_star(legacy, 1)
    assert legacy.co_state["stars_earned_total"] == 6
    assert can_fire_from_effects(legacy) is True
    # 放 power
    remaining = consume_power_stars(legacy)
    assert remaining == 0
    assert legacy.co_state["stars_earned_total"] == 0


def test_legacy_no_co_state_at_all_initializes_fresh():
    """co_state 完全为 None / 空 dict,record_morale_star 自动建默认结构。"""
    player = SimpleNamespace(commander_id="yun", co_state=None)
    record_morale_star(player, 1)
    # 第一次调用建出全部默认
    assert player.co_state == {
        "commander_id": "yun",
        "threshold": 20,
        "stars_earned_total": 1,
        "power_cost": 6,
        "meter": 0,
        "is_power_active": False,
        "last_start_turn": -1,
    }


def test_legacy_co_state_can_player_continue_to_play():
    """新机制下,旧 co_state 不影响游戏继续:玩家能正常进入和放 power。"""
    # 玩家初始时 co_state 只有旧字段(没有 stars_earned_total)
    player = SimpleNamespace(commander_id="yun", co_state={
        "commander_id": "yun",
        "meter": 0,
        "threshold": 18,
    })
    # 杀 3 个:累积 3
    for _ in range(3):
        record_morale_star(player, 1)
    assert player.co_state["stars_earned_total"] == 3
    # 不能放(stars=3 < power_cost=6)
    assert can_fire_from_effects(player) is False
    # 杀满 6 颗
    for _ in range(3):
        record_morale_star(player, 1)
    # 现在可以放
    assert can_fire_from_effects(player) is True
    # 放
    remaining = consume_power_stars(player)
    assert remaining == 0  # 6 - 6
