from __future__ import annotations

from types import SimpleNamespace

from app.commanders import consume_power_stars, record_morale_star


def test_record_morale_star_initializes_state_and_increments():
    """无 co_state 时,record_morale_star 自动建出默认 dict 并累加星。"""
    player = SimpleNamespace(commander_id="yun", co_state=None)

    # 第一次:co_state 自动创建,默认 threshold=20 / power_cost=6
    added = record_morale_star(player, 1)
    assert added == 1
    assert player.co_state["stars_earned_total"] == 1
    assert player.co_state["threshold"] == 20
    assert player.co_state["power_cost"] == 6

    # 第二次:累加
    added = record_morale_star(player, 1)
    assert added == 1
    assert player.co_state["stars_earned_total"] == 2


def test_record_morale_star_caps_at_threshold():
    """达到 threshold 后不再增加(返回 0)。"""
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 5, "stars_earned_total": 3, "power_cost": 6,
    })
    # 还差 2 颗
    assert record_morale_star(player, 5) == 2
    assert player.co_state["stars_earned_total"] == 5
    # 已 cap
    assert record_morale_star(player, 1) == 0
    assert player.co_state["stars_earned_total"] == 5


def test_record_morale_star_noop_without_commander():
    """无 commander_id 的玩家不会进星(避免给无 CO 的玩家写脏数据)。"""
    player = SimpleNamespace(commander_id=None, co_state=None)
    assert record_morale_star(player, 1) == 0
    # co_state 此时仍为 None,函数无副作用
    assert player.co_state is None


def test_consume_power_stars_deducts_cost():
    """扣 power_cost 颗星,返回扣除后剩余。"""
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 18, "stars_earned_total": 12, "power_cost": 6,
    })
    remaining = consume_power_stars(player)
    assert remaining == 6
    assert player.co_state["stars_earned_total"] == 6


def test_consume_power_stars_raises_on_insufficient():
    """stars_earned_total < power_cost 时抛 ValueError,不修改状态。"""
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 18, "stars_earned_total": 5, "power_cost": 6,
    })
    import pytest
    with pytest.raises(ValueError, match="insufficient stars"):
        consume_power_stars(player)
    # 不变
    assert player.co_state["stars_earned_total"] == 5
