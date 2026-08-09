"""Unit tests for the MOV/MP merge: ``mp_pool`` is gone, ``base_mov`` is the only movement stat."""
from __future__ import annotations

import pytest

from app.classes.heroes import list_all as list_all_heroes
from app.classes.units import get as get_class
from app.classes.units import list_all as list_all_classes


def test_mp_pool_field_removed_from_profile() -> None:
    """`UnitClassProfile` no longer has an `mp_pool` attribute."""
    for cls in list_all_classes():
        assert not hasattr(cls, "mp_pool"), (
            f"{cls.type_id} profile still has mp_pool"
        )


# 2026-08-10 平衡:全部 4 个英雄 effective mov = 5(无论 override 还是 inherit)。
HERO_MOV = 5


@pytest.mark.parametrize("hero_id,base_class_id", [
    ("anna",     "healer"),
    ("youko",    "bard"),
    ("yun",      "warlock"),
    ("yuanying", "warlock"),
])
def test_every_hero_effective_mov_is_uniform(hero_id: str, base_class_id: str) -> None:
    """All heroes share effective mov=5 (uniform standard).  Catches
    accidental drift back to per-hero overrides."""
    from app.classes.heroes import get as get_hero
    hero = get_hero(hero_id)
    base = get_class(base_class_id)
    effective = hero.mov_override if hero.mov_override is not None else base.base_mov
    assert effective == HERO_MOV, (
        f"{hero_id}: expected effective mov={HERO_MOV}, got {effective} "
        f"(override={hero.mov_override}, base_class.base_mov={base.base_mov})"
    )


@pytest.mark.parametrize("type_id,expected_mov", [
    # 2026-08-10 平衡(两次调):
    #   7+ 移动力普遍下调;法师/射手再砍一档。
    #   - 物理射手(archer / sniper)降速最狠: 5 -> 3, 6 -> 4
    #   - 骑士/法师/治疗/飞龙/升阶后 5-6
    #   - 物理重装 / 法师 / 治疗封顶 6,飞龙走飞行地形作为补偿
    ("swordsman", 5),
    ("archer", 3),         # 5 -> 3 (T1 射手脆皮)
    ("lancer", 6),
    ("knight", 6),         # 8 -> 6
    ("warlock", 5),        # 8 -> 5
    ("healer", 5),
    ("dragon_rider", 5),   # 7 -> 5
    ("falcon_knight", 6),
    ("warrior", 4),
    ("blade_master", 6),
    ("sniper", 4),         # 6 -> 4 (T2 射手脆皮,比 archer 略多)
    ("paladin", 6),        # 9 -> 6
    ("sage", 6),           # 10 -> 6
    ("saint", 6),          # 8 -> 6
    ("berserker", 5),
    ("bard", 6),
])
def test_base_mov_after_merge_matches_spec(type_id: str, expected_mov: int) -> None:
    prof = get_class(type_id)
    assert prof.base_mov == expected_mov, (
        f"{type_id}: expected base_mov={expected_mov}, got {prof.base_mov}"
    )


def test_every_class_has_complete_growth_rates() -> None:
    """Every registered class declares all 6 STAT_KEYS in class_growth_rates."""
    from app.progression.policies import STAT_KEYS
    for cls in list_all_classes():
        missing = set(STAT_KEYS) - set(cls.class_growth_rates.keys())
        assert not missing, f"{cls.type_id} missing growth rates: {sorted(missing)}"


def test_every_class_growth_rate_in_range() -> None:
    for cls in list_all_classes():
        for stat, rate in cls.class_growth_rates.items():
            assert 0 <= rate <= 100, (
                f"{cls.type_id}.{stat} = {rate} not in [0, 100]"
            )
