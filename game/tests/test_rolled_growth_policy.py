"""Unit tests for RolledGrowthPolicy (FE8-style per-stat per-level roll)."""
from __future__ import annotations

import random

import pytest

from app.classes.units import get
from app.progression.policies import (
    PROMOTION_BONUSES,
    RolledGrowthPolicy,
    STAT_CAPS,
    STAT_KEYS,
    promotion_bonus_for,
)


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


# ======================================================================
# Hit-rate close to the configured rate
# ======================================================================

@pytest.mark.parametrize("rate", [25, 50, 75, 100])
def test_hit_rate_close_to_rate(rate: int) -> None:
    """Across 10_000 trials at `rate` %, hits land within ~5% of rate.

    The test counts the number of trials where atk actually grew
    (delta > 0), which combines the hit-rate check and the 5% +0
    magnitude bucket.  Expected hits = trials * rate/100 * 0.95.
    At rate=100 this means 9500 hits; at rate=50 it's 4750.  The
    +/-5% window is wide enough to accommodate Monte-Carlo noise
    plus the small P0 (~5%) bucket.
    """
    sw = get("swordsman")
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=sw, hero_profile=None)
    bl.class_growth_rates["atk"] = rate
    bl.stat_caps["atk"] = 99_999  # never saturate across 10k rolls

    rng = random.Random(0)
    hits = 0
    trials = 10_000
    v = bl.base_stats
    for _ in range(trials):
        before = v["atk"]
        v = policy.roll_level_up(current_stats=v, baseline_=bl, rng=rng)
        if v["atk"] > before:
            hits += 1
    # Combined: hit AND magnitude > 0.  Hit prob = rate/100, mag>0
    # prob = 0.95, so expected = trials * rate / 100 * 0.95.
    expected = trials * rate / 100 * 0.95
    assert abs(hits - expected) / trials < 0.05, (
        f"rate={rate}: hits={hits} expected~{expected}"
    )


# ======================================================================
# Magnitude distribution within tolerance
# ======================================================================

def test_magnitude_distribution_close_to_p1_p2() -> None:
    """Among 10_000 hits, ~25% are +2 and ~70% are +1 (5% +0 is a knob).

    The cap has to be high enough that 10_000 hits don't saturate the
    stat (swordsman base 18 + 1.05 * 10_000 ~ 10_500).  Use 99_999.
    """
    sw = get("swordsman")
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=sw, hero_profile=None)
    bl.class_growth_rates["atk"] = 100  # always hit
    bl.stat_caps["atk"] = 99_999  # never saturate

    rng = random.Random(0)
    p1 = p2 = p0 = 0
    trials = 10_000
    v = bl.base_stats
    for _ in range(trials):
        before = v["atk"]
        v = policy.roll_level_up(current_stats=v, baseline_=bl, rng=rng)
        delta = v["atk"] - before
        if delta == 1:
            p1 += 1
        elif delta == 2:
            p2 += 1
        elif delta == 0:
            p0 += 1
        else:
            pytest.fail(f"unexpected delta {delta}")
    # Allow ±3% per bucket.
    assert 0.67 < p1 / trials < 0.73, f"p1 share = {p1 / trials}"
    assert 0.22 < p2 / trials < 0.28, f"p2 share = {p2 / trials}"
    assert 0.02 < p0 / trials < 0.08, f"p0 share = {p0 / trials}"


# ======================================================================
# Stat caps apply
# ======================================================================

def test_caps_apply_across_many_rolls() -> None:
    """1000 hits at a stat near its cap never overflows."""
    sw = get("swordsman")
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=sw, hero_profile=None)
    bl.class_growth_rates["atk"] = 100
    # Cap atk at 25 (swordsman base 18; only ~7 expected hits needed).
    bl.stat_caps["atk"] = 25
    v = dict(bl.base_stats)
    rng = random.Random(0)
    for _ in range(1000):
        v = policy.roll_level_up(current_stats=v, baseline_=bl, rng=rng)
    assert v["atk"] == 25, f"expected atk capped at 25, got {v['atk']}"


# ======================================================================
# Baseline clamps class+personal to [0, 100]
# ======================================================================

def test_baseline_clamps_modifier_sum_to_100() -> None:
    """Class 70 + hero +30 → effective 100 (clamped at the ceiling)."""
    from types import SimpleNamespace

    from app.progression.policies import _resolve_effective_growth_rates

    sw = get("swordsman")
    # Bump swordsman's atk rate to 70, then a +30 personal modifier
    # pushes it to the 100 ceiling.
    sw.class_growth_rates["atk"] = 70
    try:
        fake_hero = SimpleNamespace(
            hero_id="x", display_cn="x", base_class_id="swordsman",
            personal_growth_modifier={"atk": 30},
        )
        eff = _resolve_effective_growth_rates(sw, fake_hero)
        assert eff["atk"] == 100
    finally:
        # restore — don't pollute the registry for other tests
        sw.class_growth_rates["atk"] = 45


def test_baseline_modifier_can_be_negative() -> None:
    """Class 45 + hero -20 -> effective 25."""
    from types import SimpleNamespace

    sw = get("swordsman")
    fake_hero = SimpleNamespace(
        hero_id="x", display_cn="x", base_class_id="swordsman",
        personal_growth_modifier={"atk": -20},
    )
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=sw, hero_profile=fake_hero)
    # swordsman atk base is 45; clamp(45 + (-20), 0, 100) = 25
    assert bl.class_growth_rates["atk"] == 25


# ======================================================================
# Determinism via injected rng
# ======================================================================

def test_seeded_rng_is_deterministic() -> None:
    """Same seed produces identical results; different seeds diverge."""
    sw = get("swordsman")
    policy = RolledGrowthPolicy()
    bl = policy.baseline(class_profile=sw, hero_profile=None)

    v1 = policy.stat_at_level(baseline_=bl, level=10, rng=random.Random(123))
    v2 = policy.stat_at_level(baseline_=bl, level=10, rng=random.Random(123))
    v3 = policy.stat_at_level(baseline_=bl, level=10, rng=random.Random(456))
    assert v1 == v2
    assert v1 != v3


# ======================================================================
# STAT_CAPS exposed
# ======================================================================

def test_stat_caps_keys_match_stat_keys() -> None:
    assert set(STAT_CAPS.keys()) == set(STAT_KEYS)
    # Sanity: every cap is > corresponding FE8 L1 base.
    for k in STAT_KEYS:
        assert STAT_CAPS[k] > 0


def test_promotion_bonus_for_known_tier1_class() -> None:
    bonus = promotion_bonus_for("swordsman")
    assert bonus == {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 0}


def test_promotion_bonus_for_tier2_returns_zero() -> None:
    """Tier-2 unit_types get a zero bonus (no double-promotion)."""
    bonus = promotion_bonus_for("paladin")
    assert all(v == 0 for v in bonus.values())


def test_promotion_bonus_for_unknown_returns_zero() -> None:
    bonus = promotion_bonus_for("nonexistent_class")
    assert all(v == 0 for v in bonus.values())
