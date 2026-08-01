from __future__ import annotations

import dataclasses

from app.commanders import COState, CommanderPassive, CommanderPower


def test_co_state_defaults_round_trip():
    state = COState.load(None)

    assert state == COState(
        commander_id=None,
        threshold=20,
        stars_earned_total=0,
        power_cost=6,
        meter=0,
        is_power_active=False,
        last_start_turn=-1,
    )
    assert state.dump() == {
        "commander_id": None,
        "threshold": 20,
        "stars_earned_total": 0,
        "power_cost": 6,
        "meter": 0,
        "is_power_active": False,
        "last_start_turn": -1,
    }
    assert COState.load(state.dump()) == state


def test_co_state_load_accepts_plain_dict():
    state = COState.load(
        {
            "commander_id": "yun",
            "stars_earned_total": 12,
            "threshold": 30,
            "power_cost": 8,
            "meter": 12,
            "is_power_active": True,
            "last_start_turn": 4,
        }
    )

    assert state.commander_id == "yun"
    assert state.stars_earned_total == 12
    assert state.threshold == 30
    assert state.power_cost == 8
    assert state.is_power_active is True
    assert state.last_start_turn == 4


def test_co_state_load_backfills_missing_new_fields():
    """旧档案缺新字段(stars_earned_total / power_cost)时回退到默认值。

    这是存档兼容的回归保护。
    """
    legacy_dict = {
        "commander_id": "yun",
        "meter": 0,
        "threshold": 18,
        "is_power_active": False,
        "last_start_turn": -1,
    }
    state = COState.load(legacy_dict)

    # 新字段缺,落到默认值
    assert state.stars_earned_total == 0
    assert state.power_cost == 6
    # 旧字段保留
    assert state.commander_id == "yun"
    assert state.threshold == 18
    assert state.meter == 0
    assert state.is_power_active is False


def test_commander_dataclasses_are_frozen():
    passive = CommanderPassive(id="passive-1")
    power = CommanderPower(id="power-1")

    assert dataclasses.is_dataclass(passive)
    assert dataclasses.is_dataclass(power)
    assert getattr(type(passive), "__dataclass_params__").frozen is True
    assert getattr(type(power), "__dataclass_params__").frozen is True


def test_commander_power_has_cost_field():
    """CommanderPower 加 cost 字段,默认 6。"""
    power = CommanderPower(id="p1")
    assert power.cost == 6

    power_with_cost = CommanderPower(id="p2", cost=10)
    assert power_with_cost.cost == 10
