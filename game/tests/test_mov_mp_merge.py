"""Unit tests for the MOV/MP merge: ``mp_pool`` is gone, ``base_mov`` is the only movement stat."""
from __future__ import annotations

import pytest

from app.classes.units import get as get_class
from app.classes.units import list_all as list_all_classes


def test_mp_pool_field_removed_from_profile() -> None:
    """`UnitClassProfile` no longer has an `mp_pool` attribute."""
    for cls in list_all_classes():
        assert not hasattr(cls, "mp_pool"), (
            f"{cls.type_id} profile still has mp_pool"
        )


@pytest.mark.parametrize("type_id,expected_mov", [
    # From spec §9.1 — base_mov is max(old_base_mov, old_mp_pool)
    ("swordsman", 5),  # 3, 5 -> 5
    ("archer", 5),     # 3, 5 -> 5
    ("lancer", 6),     # 5, 6 -> 6
    ("knight", 8),     # 5, 8 -> 8
    ("warlock", 8),    # 3, 8 -> 8
    ("healer", 5),     # 3, 5 -> 5
    ("dragon_rider", 7),
    ("falcon_knight", 6),
    ("warrior", 4),
    ("blade_master", 6),
    ("sniper", 6),
    ("paladin", 9),
    ("sage", 10),
    ("saint", 8),
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
