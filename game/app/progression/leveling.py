"""
Leveling math — pure functions, no DB access.

Design principles:
  - All formulas are data-driven (XP_CURVE, TIER_LEVEL_CAP) so balance
    changes don't require code changes.
  - Mutations are explicit (functions take + return, not magic).
  - The unit can be any object with `.level`, `.exp`, `.tier` attributes
    (we use a Protocol so we don't depend on the ORM type).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Protocol


# ============================================================
# Constants
# ============================================================

# XP required to ADVANCE from level N to level N+1.
# Lv 1→2 costs 100, Lv 2→3 costs 200, ... (cubic-ish growth)
XP_CURVE: Final[dict[int, int]] = {
    1: 100, 2: 200, 3: 350, 4: 550, 5: 800,
    6: 1100, 7: 1450, 8: 1850, 9: 2300, 10: 2800,
    11: 3350, 12: 3950, 13: 4600, 14: 5300, 15: 6050,
    16: 6850, 17: 7700, 18: 8600, 19: 9550, 20: 10550,
    21: 11600, 22: 12700, 23: 13850, 24: 15050, 25: 16300,
    26: 17600, 27: 18950, 28: 20350, 29: 21800, 30: 23300,
    31: 24850, 32: 26450, 33: 28100, 34: 29800, 35: 31550,
    36: 33350, 37: 35200, 38: 37100, 39: 39050, 40: 41050,
    41: 43100, 42: 45200, 43: 47350, 44: 49550, 45: 51800,
    46: 54100, 47: 56450, 48: 58850, 49: 61300, 50: 63800,
}

# Per-tier max level (you must promote to exceed this).
TIER_LEVEL_CAP: Final[dict[int, int]] = {1: 20, 2: 35, 3: 50}

# XP needed to *promote* from tier N to tier N+1.
TIER_PROMO_LEVEL_REQ: Final[dict[int, int]] = {1: 20, 2: 35}  # tier 3 is max

# Talent points awarded per level-up.
TALENT_POINTS_PER_LEVEL: Final[int] = 1


# ============================================================
# Attribute scaling curves
# ============================================================

# Linear:     base * (1 + 0.05 * (level - 1))
# Exp:        base * (1.1 ** (level - 1))
# Log:        base * (1 + 0.1 * log2(max(level, 1)))
GROWTH_CURVES: Final[dict[str, callable]] = {
    "linear":      lambda base, lv: int(base * (1 + 0.05 * (lv - 1))),
    "exponential": lambda base, lv: int(base * (1.1 ** (lv - 1))),
    "logarithmic": lambda base, lv: int(base * (1 + 0.1 * math.log2(max(lv, 1)))),
}


# ============================================================
# UnitLike protocol (so we don't have to import the ORM here)
# ============================================================

class UnitLike(Protocol):
    level: int
    exp: int
    tier: int
    talent_points: int


# ============================================================
# Public API
# ============================================================

def xp_to_next(level: int) -> int | None:
    """XP required to advance from `level` to `level + 1`. None if at cap."""
    if level in XP_CURVE:
        return XP_CURVE[level]
    if level > max(XP_CURVE.keys()):
        return None
    return XP_CURVE[max(XP_CURVE.keys())]


def max_level_for_tier(tier: int) -> int:
    return TIER_LEVEL_CAP.get(tier, TIER_LEVEL_CAP[max(TIER_LEVEL_CAP.keys())])


def can_level_up(unit: UnitLike) -> bool:
    """True if the unit still has room to gain a level (not at tier cap)."""
    if unit.level >= max_level_for_tier(unit.tier):
        return False
    return xp_to_next(unit.level) is not None


def can_promote(unit: UnitLike) -> bool:
    """True if the unit meets the level requirement to advance a tier."""
    if unit.tier >= max(TIER_PROMO_LEVEL_REQ.keys()):
        return False  # already at max tier
    return unit.level >= TIER_PROMO_LEVEL_REQ.get(unit.tier, 99)


@dataclass(frozen=True)
class LevelUpResult:
    levels_gained: int
    new_level: int
    talent_points_awarded: int


def award_exp(unit: UnitLike, amount: int) -> LevelUpResult:
    """Add `amount` EXP to the unit, cascading level-ups as needed.

    Returns a summary; the caller is expected to `await session.commit()`.

    If the unit is already at the tier's level cap, the EXP is **discarded**
    (we don't bank it across promotions, to keep matchmaking balanced).
    """
    if amount < 0:
        raise ValueError("amount must be non-negative")

    cap = max_level_for_tier(unit.tier)
    # Already at cap: no level-ups possible, drop the EXP on the floor.
    if unit.level >= cap:
        return LevelUpResult(
            levels_gained=0,
            new_level=unit.level,
            talent_points_awarded=0,
        )

    unit.exp += amount
    levels_gained = 0

    while can_level_up(unit):
        needed = xp_to_next(unit.level)
        if needed is None:
            break
        if unit.exp < needed:
            break
        unit.exp -= needed
        unit.level += 1
        levels_gained += 1
        unit.talent_points += TALENT_POINTS_PER_LEVEL
        if unit.level >= cap:
            # Hit the cap exactly; discard any leftover EXP
            unit.level = cap
            unit.exp = 0
            break

    return LevelUpResult(
        levels_gained=levels_gained,
        new_level=unit.level,
        talent_points_awarded=levels_gained * TALENT_POINTS_PER_LEVEL,
    )


def promote(unit: UnitLike) -> int:
    """Advance the unit one tier (1→2 or 2→3). Returns the new tier.

    Raises:
      ValueError: if not eligible (use can_promote() first).
    """
    if not can_promote(unit):
        raise ValueError(
            f"unit not eligible for promotion: tier={unit.tier} level={unit.level}"
        )
    unit.tier += 1
    # At promotion, any leftover EXP rolls into the new tier's XP pool
    # (caller's call — current implementation keeps it; could reset)
    return unit.tier


def stat_at_level(base: int, level: int, curve: str = "linear") -> int:
    """Compute a base stat at a given level using the named growth curve."""
    if curve not in GROWTH_CURVES:
        raise ValueError(f"unknown growth curve: {curve!r}")
    return GROWTH_CURVES[curve](base, level)


__all__ = [
    "XP_CURVE",
    "TIER_LEVEL_CAP",
    "TIER_PROMO_LEVEL_REQ",
    "TALENT_POINTS_PER_LEVEL",
    "GROWTH_CURVES",
    "UnitLike",
    "LevelUpResult",
    "xp_to_next",
    "max_level_for_tier",
    "can_level_up",
    "can_promote",
    "award_exp",
    "promote",
    "stat_at_level",
]
