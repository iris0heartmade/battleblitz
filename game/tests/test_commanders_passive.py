from app.classes.heroes import get as get_hero
from app.commanders import CommanderPassive
from app.commanders.effects import bake_passive_into_units
from app.commanders.registry import get_commander_passive


class FakeUnit:
    def __init__(self, hp=20, max_hp=20, atk=5, def_=3, matk=2, mdef=1,
                 mov=4, attack_range=1):
        self.hp, self.max_hp = hp, max_hp
        self.atk, self.def_, self.matk, self.mdef = atk, def_, matk, mdef
        self.mov, self.attack_range = mov, attack_range


class FakePlayer:
    def __init__(self, commander_id, units=None):
        self.commander_id, self.units = commander_id, units or []


def test_yun_bakes_attack_and_range():
    unit = FakeUnit(atk=10, attack_range=2)
    bake_passive_into_units(FakePlayer("yun", [unit]))
    assert unit.atk == 11
    assert unit._base_attack_range == 3
    assert unit._commander_passive is get_commander_passive("yun")


def test_anna_bakes_defense():
    unit = FakeUnit(def_=10)
    bake_passive_into_units(FakePlayer("anna", [unit]))
    assert unit.def_ == 12


def test_no_commander_is_noop():
    unit = FakeUnit(atk=10)
    bake_passive_into_units(FakePlayer(None, [unit]))
    assert unit.atk == 10
    assert not hasattr(unit, "_commander_passive")


def test_zero_hp_bonus_preserves_current_hp():
    unit = FakeUnit(hp=5, max_hp=20)
    bake_passive_into_units(FakePlayer("yun", [unit]))
    assert (unit.hp, unit.max_hp) == (5, 20)


def test_negative_values_and_movement_floor():
    hero = get_hero("yun")
    original = hero.commander_passive
    object.__setattr__(hero, "commander_passive", CommanderPassive(
        id="penalty", atk_pct=-.2, mov_delta=-10,
    ))
    try:
        unit = FakeUnit(atk=10, mov=5)
        bake_passive_into_units(FakePlayer("yun", [unit]))
        assert (unit.atk, unit.mov) == (8, 1)
    finally:
        object.__setattr__(hero, "commander_passive", original)


def test_bake_is_idempotent():
    unit = FakeUnit(atk=10, attack_range=2)
    player = FakePlayer("yun", [unit])
    bake_passive_into_units(player)
    bake_passive_into_units(player)
    assert unit.atk == 11
    assert unit._base_attack_range == 3
