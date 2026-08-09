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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Mapping, Optional, Protocol

if TYPE_CHECKING:
    # Avoid a runtime import cycle: policies imports nothing from
    # leveling, but leveling calls into policies at runtime via
    # apply_promotion_bonus().  The TYPE_CHECKING block keeps the
    # type hint available to IDEs / mypy without forcing a load.
    from app.progression.policies import promotion_bonus_for  # noqa: F401


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
    # Per-stat delta applied by RolledGrowthPolicy during this
    # award_exp() call.  Reserved by spec §14 ("award_exp() returns
    # the rolled deltas in LevelUpResult.stat_delta"), but NOT
    # populated by :func:`award_exp` in this commit — see "Deferred"
    # note below.  Stays in the dataclass for forward-compat: when
    # the spec lands the runtime-roll behavior, callers can start
    # reading it without an API change.
    #
    # DEFERRED: this would require ``award_exp`` to know the unit's
    # class_profile (for ``class_growth_rates``) and hero_profile
    # (for ``personal_growth_modifier``); the current ``UnitLike``
    # Protocol doesn't carry them.  Plumbing them through is a
    # separate change.  Until then, runtime level-ups DO NOT
    # re-roll stats; stat growth happens exactly once, at spawn,
    # via :func:`app.modes.spawn_generic_stats` (L1..L-N rolled in
    # one shot, seeded by ``unit.growth_seed``).
    stat_delta: Mapping[str, int] = field(default_factory=dict)


def award_exp(unit: UnitLike, amount: int) -> LevelUpResult:
    """Add `amount` EXP to the unit, cascading level-ups as needed.

    Returns a summary; the caller is expected to `await session.commit()`.

    If the unit is already at the tier's level cap, the EXP is **discarded**
    (we don't bank it across promotions, to keep matchmaking balanced).

    Note on RolledGrowthPolicy integration:
        This function is intentionally a pure EXP → level transition.
        It does NOT re-roll per-stat growth on every level-up.  Per-stat
        growth is computed exactly once, at spawn, by
        :func:`app.modes.spawn_generic_stats` (which calls
        :class:`app.progression.policies.RolledGrowthPolicy` once for
        each (L2..L_start_level) and stores the resolved values on the
        ``Unit`` row).  Runtime level-ups only bump ``unit.level`` and
        ``unit.talent_points``; the per-stat fields on the row are
        already pre-grown for that level.

        If a future spec wants level-up-time re-roll, plumb the
        unit's ``class_profile`` + ``hero_profile`` through
        ``UnitLike`` and call :func:`RolledGrowthPolicy.roll_level_up`
        once per level gained, accumulating the deltas into
        ``LevelUpResult.stat_delta``.  See the DEFERRED note on
        ``stat_delta`` above.
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


def apply_promotion_bonus(
    unit,
    unit_type: str,
) -> Mapping[str, int]:
    """Apply the flat promotion bonus for a tier-1 class to a unit.

    Reads ``unit_type`` (the unit's class id BEFORE the tier bump —
    pass the *old* type id here), looks up :func:`promotion_bonus_for`,
    and adds each non-zero entry to the matching ``unit`` attribute
    (e.g. ``unit.hp += bonus["hp"]``).

    Returns the dict that was applied, so callers can echo it back
    in API responses / log lines.  Mutates the unit in place.

    Note: this assumes the unit has a ``unit_type`` attribute.  In
    practice the service layer reads ``unit.unit_type`` BEFORE calling
    ``promote(unit)`` so the old class id is available.
    """
    # Local import: keeps the import-time graph clean (policies does
    # NOT import leveling; leveling → policies is a one-way edge).
    from app.progression.policies import promotion_bonus_for

    bonus = promotion_bonus_for(unit_type)
    if not any(bonus.values()):
        return bonus
    for stat, delta in bonus.items():
        if delta == 0:
            continue
        current = getattr(unit, stat, None)
        if current is None:
            # stat not on this unit (e.g. legacy column absent); skip
            continue
        setattr(unit, stat, int(current) + int(delta))
    return bonus


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
    "apply_promotion_bonus",
    "stat_at_level",
]
