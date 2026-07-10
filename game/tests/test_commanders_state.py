from __future__ import annotations

import dataclasses

from app.commanders import COState, CommanderPassive, CommanderPower


def test_co_state_defaults_round_trip():
    state = COState.load(None)

    assert state == COState(
        commander_id=None,
        meter=0,
        threshold=20,
        is_power_active=False,
        last_start_turn=-1,
    )
    assert state.dump() == {
        "commander_id": None,
        "meter": 0,
        "threshold": 20,
        "is_power_active": False,
        "last_start_turn": -1,
    }
    assert COState.load(state.dump()) == state


def test_co_state_load_accepts_plain_dict():
    state = COState.load(
        {
            "commander_id": "yun",
            "meter": 12,
            "threshold": 30,
            "is_power_active": True,
            "last_start_turn": 4,
        }
    )

    assert state.commander_id == "yun"
    assert state.meter == 12
    assert state.threshold == 30
    assert state.is_power_active is True
    assert state.last_start_turn == 4


def test_commander_dataclasses_are_frozen():
    passive = CommanderPassive(id="passive-1")
    power = CommanderPower(id="power-1")

    assert dataclasses.is_dataclass(passive)
    assert dataclasses.is_dataclass(power)
    assert getattr(type(passive), "__dataclass_params__").frozen is True
    assert getattr(type(power), "__dataclass_params__").frozen is True
