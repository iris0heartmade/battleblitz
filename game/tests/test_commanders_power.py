import pytest

from app.commanders.effects import (
    bake_passive_into_units, can_fire_co_power, expire_power, fire_co_power,
)


class FakeUnit:
    def __init__(self, id=1, hp=20, max_hp=20, atk=10, def_=5, matk=2, mdef=1,
                 mov=4, mp=4, attack_range=2):
        self.id = id
        self.hp, self.max_hp = hp, max_hp
        self.atk, self.def_, self.matk, self.mdef = atk, def_, matk, mdef
        self.mov, self.mp, self.attack_range = mov, mp, attack_range


class FakePlayer:
    def __init__(self, commander_id, units=None, meter=0, active=False, threshold=22):
        self.commander_id, self.units = commander_id, units or []
        self.co_state = {"commander_id": commander_id, "meter": meter,
                         "threshold": threshold, "is_power_active": active,
                         "last_start_turn": -1}


@pytest.mark.parametrize("player, expected", [
    (FakePlayer("yun", meter=22), True),
    (FakePlayer("yun", meter=10), False),
    (FakePlayer("yun", meter=22, active=True), False),
    (FakePlayer(None, meter=100), False),
])
def test_can_fire_conditions(player, expected):
    assert can_fire_co_power(player) is expected


def test_fire_stacks_heals_marks_and_consumes_meter():
    unit = FakeUnit(hp=20, max_hp=40, atk=10)
    player = FakePlayer("yun", [unit], meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    assert (unit.atk, unit.hp) == (14, 40)
    assert player.co_state["meter"] == 0
    assert player.co_state["is_power_active"] is True
    assert unit._commander_power is not None


def test_fire_rejects_low_meter():
    with pytest.raises(ValueError, match="meter not full"):
        fire_co_power(FakePlayer("yun", meter=10))


def test_heal_is_capped_and_zero_extra_move_is_noop():
    unit = FakeUnit(hp=5, max_hp=20, mp=2, mov=5)
    player = FakePlayer("yun", [unit], meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    assert (unit.hp, unit.mp) == (15, 2)


def test_expire_restores_passive_baseline_only():
    unit = FakeUnit(atk=10)
    player = FakePlayer("yun", [unit], meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    expire_power(player)
    assert unit.atk == 11
    assert player.co_state["is_power_active"] is False
    assert not hasattr(unit, "_commander_power")


def test_expire_when_inactive_is_noop():
    unit = FakeUnit(atk=10)
    player = FakePlayer("yun", [unit])
    bake_passive_into_units(player)
    expire_power(player)
    assert unit.atk == 11


def test_expire_restores_after_unit_reload():
    unit = FakeUnit(id=42, atk=10)
    player = FakePlayer("yun", [unit], meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    saved_state = dict(player.co_state)

    reloaded = FakeUnit(id=42, atk=unit.atk)
    reloaded_player = FakePlayer("yun", [reloaded])
    reloaded_player.co_state = saved_state
    expire_power(reloaded_player)
    assert reloaded.atk == 11
    assert "_power_baselines" not in reloaded_player.co_state


def test_co_state_changes_use_new_dict_objects():
    player = FakePlayer("yun", [FakeUnit()], meter=22)
    bake_passive_into_units(player)
    before_fire = player.co_state
    fire_co_power(player)
    assert player.co_state is not before_fire
    before_expire = player.co_state
    expire_power(player)
    assert player.co_state is not before_expire
