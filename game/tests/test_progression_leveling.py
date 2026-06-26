"""
Unit tests for the leveling math (pure functions).

Covers XP curves, level-up cascading, tier promotion, growth curves.
"""
from __future__ import annotations

import pytest

from app.progression import (
    GROWTH_CURVES,
    TALENT_POINTS_PER_LEVEL,
    TIER_LEVEL_CAP,
    TIER_PROMO_LEVEL_REQ,
    XP_CURVE,
    UnitInstance,
    award_exp,
    can_level_up,
    can_promote,
    max_level_for_tier,
    promote,
    stat_at_level,
    xp_to_next,
)
from app.progression.leveling import LevelUpResult


def _stub_unit(*, level: int = 1, exp: int = 0, tier: int = 1, talent_points: int = 0) -> UnitInstance:
    """In-memory UnitInstance, never persisted. We only touch the leveling fields."""
    return UnitInstance(
        profile_id=1,
        base_type="swordsman",
        nickname=f"Test{level}",
        tier=tier,
        level=level,
        exp=exp,
        talent_points=talent_points,
    )


# ============================================================
# Constants / lookups
# ============================================================

@pytest.mark.unit
class TestCurves:
    def test_xp_curve_grows(self):
        # XP to advance should never decrease with level
        levels = sorted(XP_CURVE.keys())
        prev = 0
        for lv in levels:
            cost = XP_CURVE[lv]
            assert cost > prev, f"XP_CURVE not monotonic at level {lv}"
            prev = cost

    def test_xp_to_next_known_levels(self):
        assert xp_to_next(1) == 100
        assert xp_to_next(5) == 800
        assert xp_to_next(10) == 2800

    def test_xp_to_next_above_max_returns_none(self):
        assert xp_to_next(60) is None
        assert xp_to_next(100) is None

    def test_max_level_for_tier(self):
        assert max_level_for_tier(1) == 20
        assert max_level_for_tier(2) == 35
        assert max_level_for_tier(3) == 50

    def test_tier_promo_requirements(self):
        assert TIER_PROMO_LEVEL_REQ[1] == 20
        assert TIER_PROMO_LEVEL_REQ[2] == 35


# ============================================================
# can_level_up / can_promote
# ============================================================

@pytest.mark.unit
class TestEligibility:
    def test_fresh_unit_can_level_up(self):
        u = _stub_unit(level=1, exp=0)
        assert can_level_up(u) is True

    def test_at_tier_cap_cannot_level(self):
        u = _stub_unit(level=20, exp=0, tier=1)  # tier 1 cap is 20
        assert can_level_up(u) is False

    def test_fresh_unit_cannot_promote(self):
        u = _stub_unit(level=1, tier=1)
        assert can_promote(u) is False

    def test_at_promo_level_can_promote(self):
        u = _stub_unit(level=20, tier=1)
        assert can_promote(u) is True

    def test_max_tier_cannot_promote(self):
        u = _stub_unit(level=50, tier=3)
        assert can_promote(u) is False


# ============================================================
# award_exp
# ============================================================

@pytest.mark.unit
class TestAwardExp:
    def test_single_level_up(self):
        u = _stub_unit(level=1, exp=0)
        r = award_exp(u, 100)  # exactly enough for Lv 1→2
        assert r.levels_gained == 1
        assert r.new_level == 2
        assert u.exp == 0
        assert u.talent_points == TALENT_POINTS_PER_LEVEL

    def test_multi_level_up(self):
        u = _stub_unit(level=1, exp=0)
        # 100 (to 2) + 200 (to 3) + 350 (to 4) = 650
        r = award_exp(u, 650)
        assert r.levels_gained == 3
        assert r.new_level == 4
        assert u.talent_points == 3 * TALENT_POINTS_PER_LEVEL

    def test_partial_progress(self):
        u = _stub_unit(level=1, exp=0)
        r = award_exp(u, 50)  # half-way to Lv 2
        assert r.levels_gained == 0
        assert u.level == 1
        assert u.exp == 50
        assert u.talent_points == 0

    def test_caps_at_tier(self):
        u = _stub_unit(level=20, exp=0, tier=1)  # at tier 1 cap
        r = award_exp(u, 100_000)  # huge amount
        # can_level_up is False, so the while loop never enters.
        # We return early — no level-up, no exp added (caller should
        # not waste exp on a capped unit).
        assert r.levels_gained == 0
        assert u.level == 20
        assert u.exp == 0
        assert u.talent_points == 0

    def test_rejects_negative(self):
        u = _stub_unit()
        with pytest.raises(ValueError):
            award_exp(u, -1)

    def test_level_19_to_20_then_stops(self):
        # Lv 19, 5500 EXP (half-way to 20). Award 5000: total 10500,
        # enough for 19→20 (9550). Remaining 950 EXP is capped to 0.
        u = _stub_unit(level=19, exp=5500, tier=1)
        r = award_exp(u, 5000)
        assert r.levels_gained == 1
        assert u.level == 20
        assert u.talent_points == 1


# ============================================================
# promote
# ============================================================

@pytest.mark.unit
class TestPromote:
    def test_basic_promote(self):
        u = _stub_unit(level=20, tier=1)
        new_tier = promote(u)
        assert new_tier == 2
        assert u.tier == 2

    def test_promote_ineligible_raises(self):
        u = _stub_unit(level=10, tier=1)
        with pytest.raises(ValueError):
            promote(u)

    def test_promote_max_tier_raises(self):
        u = _stub_unit(level=50, tier=3)
        with pytest.raises(ValueError):
            promote(u)

    def test_after_promote_can_level_again(self):
        u = _stub_unit(level=20, exp=0, tier=1)
        promote(u)
        # Now tier=2, cap=35, level still 20 — can keep levelling
        assert can_level_up(u) is True


# ============================================================
# stat_at_level (growth curves)
# ============================================================

@pytest.mark.unit
class TestStatAtLevel:
    def test_linear_growth(self):
        # base=100, lv=1: 100. lv=2: 105. lv=10: 145
        assert stat_at_level(100, 1, "linear") == 100
        assert stat_at_level(100, 2, "linear") == 105
        assert stat_at_level(100, 10, "linear") == 145

    def test_exponential_growth_stronger_than_linear(self):
        linear = stat_at_level(100, 10, "linear")
        exp = stat_at_level(100, 10, "exponential")
        assert exp > linear

    def test_logarithmic_gentler_than_linear(self):
        linear = stat_at_level(100, 10, "linear")
        log = stat_at_level(100, 10, "logarithmic")
        assert log < linear

    def test_unknown_curve_raises(self):
        with pytest.raises(ValueError):
            stat_at_level(100, 5, "bogus_curve")

    def test_all_curves_have_three_entries(self):
        assert len(GROWTH_CURVES) == 3
        for name in ("linear", "exponential", "logarithmic"):
            assert name in GROWTH_CURVES
