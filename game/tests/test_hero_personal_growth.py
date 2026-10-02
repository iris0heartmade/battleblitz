"""Unit tests for independent hero character_growth_rates."""
from __future__ import annotations

from app.classes.heroes import get as get_hero
from app.classes.units import get as get_class
from app.progression.policies import RolledGrowthPolicy


def test_yun_growth_rates_are_independent_from_warlock_rates() -> None:
    yun = get_hero("yun")
    warlock = get_class(yun.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=warlock, hero_profile=yun)
    assert bl.class_growth_rates == {
        "hp": 80,
        "atk": 35,
        "def": 35,
        "matk": 90,
        "mdef": 50,
        "mov": 0,
    }
    assert bl.class_growth_rates["matk"] != warlock.class_growth_rates["matk"] + 20


def test_yuanying_display_and_growth_rates_are_independent() -> None:
    yuanying = get_hero("yuanying")
    warlock = get_class(yuanying.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=warlock, hero_profile=yuanying)
    assert yuanying.display_cn == "鸢影"
    assert bl.class_growth_rates == {
        "hp": 85,
        "atk": 35,
        "def": 40,
        "matk": 80,
        "mdef": 55,
        "mov": 0,
    }


def test_anna_growth_rates_are_independent_from_healer_rates() -> None:
    anna = get_hero("anna")
    healer = get_class(anna.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=healer, hero_profile=anna)
    assert bl.class_growth_rates == {
        "hp": 80,
        "atk": 35,
        "def": 45,
        "matk": 50,
        "mdef": 70,
        "mov": 0,
    }


def test_youko_growth_rates_are_independent_from_bard_rates() -> None:
    youko = get_hero("youko")
    bard = get_class(youko.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=bard, hero_profile=youko)
    assert bl.class_growth_rates == {
        "hp": 75,
        "atk": 35,
        "def": 35,
        "matk": 55,
        "mdef": 65,
        "mov": 0,
    }
