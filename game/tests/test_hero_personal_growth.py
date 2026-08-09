"""Unit tests for hero personal_growth_modifier merging into effective rates."""
from __future__ import annotations

from app.classes.heroes import get as get_hero
from app.classes.units import get as get_class
from app.progression.policies import RolledGrowthPolicy


def test_yun_atk_effective_is_warlock_atk_plus_0() -> None:
    """yun no longer has +15 atk (was reverted to +20 matk / +5 mdef in spec)."""
    yun = get_hero("yun")
    warlock = get_class(yun.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=warlock, hero_profile=yun)
    assert bl.class_growth_rates["atk"] == warlock.class_growth_rates["atk"]


def test_yun_matk_effective_is_warlock_matk_plus_20() -> None:
    yun = get_hero("yun")
    warlock = get_class(yun.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=warlock, hero_profile=yun)
    assert (
        bl.class_growth_rates["matk"]
        == warlock.class_growth_rates["matk"] + 20
    )


def test_yuanying_matk_effective_is_warlock_matk_plus_10() -> None:
    yuanying = get_hero("yuanying")
    warlock = get_class(yuanying.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=warlock, hero_profile=yuanying)
    assert (
        bl.class_growth_rates["matk"]
        == warlock.class_growth_rates["matk"] + 10
    )


def test_anna_def_effective_is_healer_def_plus_5() -> None:
    anna = get_hero("anna")
    healer = get_class(anna.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=healer, hero_profile=anna)
    assert (
        bl.class_growth_rates["def"]
        == healer.class_growth_rates["def"] + 5
    )


def test_youko_matk_effective_is_bard_matk_plus_10() -> None:
    youko = get_hero("youko")
    bard = get_class(youko.base_class_id)
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=bard, hero_profile=youko)
    assert (
        bl.class_growth_rates["matk"]
        == bard.class_growth_rates["matk"] + 10
    )
