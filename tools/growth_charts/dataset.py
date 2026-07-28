"""Pure-data layer: enumerate subjects, compute growth curves.

No matplotlib.  Importable without any GUI dependency — used by
tests AND the renderer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping

from app.classes.heroes import list_all as list_all_heroes
from app.classes.units import list_all as list_all_classes
from app.progression.policies import (
    ClassBaseline,
    GrowthPolicy,
    STAT_KEYS,
)


# ============================================================
# Output dataclass
# ============================================================

@dataclass(frozen=True)
class ClassGrowthCurve:
    """A single subject's growth curve across Lv 1..max_level.

    The renderer consumes this and nothing else.  Carrying the
    whole snapshot on a frozen dataclass keeps the render call
    pure-functional (no I/O, no late-binding registry reads in
    the middle of a render).
    """

    baseline: ClassBaseline
    max_level: int
    #: level (int, 1..max_level) → stat-key → integer value
    values: Mapping[int, Mapping[str, int]]

    # ── convenience accessors ─────────────────────────────────────

    def total_at(self, level: int) -> int:
        return sum(self.values[level][k] for k in STAT_KEYS)

    def totals_curve(self) -> Dict[int, int]:
        return {lv: self.total_at(lv) for lv in range(1, self.max_level + 1)}

    def delta_pct(self, level: int) -> Mapping[str, float]:
        """(value_at(level) - L1_value) / L1_value × 100.
        Returns 0.0 for stats whose L1 is 0 (avoids div-by-zero)."""
        baseline_l1 = self.values[1]
        out: Dict[str, float] = {}
        for k in STAT_KEYS:
            l1 = baseline_l1[k]
            if l1 == 0:
                out[k] = 0.0
            else:
                out[k] = round((self.values[level][k] - l1) / l1 * 100.0, 1)
        return out


# ============================================================
# Pure functions
# ============================================================

def compute_class_growth(
    *,
    class_profile,
    max_level: int,
    policy: GrowthPolicy,
) -> ClassGrowthCurve:
    """Build a curve for a class entity (no hero overrides).

    ``class_profile`` is typed loosely so this module doesn't need
    to import :class:`UnitClassProfile` (which would couple it to
    the registry side-effects)."""
    baseline = policy.baseline(class_profile=class_profile, hero_profile=None)
    return _curve_from_baseline(baseline=baseline, max_level=max_level, policy=policy)


def compute_hero_growth(
    *,
    hero_profile,
    max_level: int,
    policy: GrowthPolicy,
) -> ClassGrowthCurve:
    """Build a curve for a hero: base class + overrides."""
    from app.classes.units import get as get_class

    baseline = policy.baseline(
        class_profile=get_class(hero_profile.base_class_id),
        hero_profile=hero_profile,
    )
    return _curve_from_baseline(baseline=baseline, max_level=max_level, policy=policy)


def _curve_from_baseline(
    *, baseline: ClassBaseline, max_level: int, policy: GrowthPolicy,
) -> ClassGrowthCurve:
    if max_level < 1:
        raise ValueError(f"max_level must be >= 1, got {max_level}")
    values: Dict[int, Dict[str, int]] = {}
    for lv in range(1, max_level + 1):
        values[lv] = dict(policy.stat_at_level(baseline_=baseline, level=lv))
    return ClassGrowthCurve(baseline=baseline, max_level=max_level, values=values)


# ============================================================
# High-level enumeration
# ============================================================

def all_class_curves(*, max_level: int, policy: GrowthPolicy) -> List[ClassGrowthCurve]:
    """Every registered unit class.

    Sort by ``tier`` then ``type_id`` so the output folder order is
    stable across runs (important for diff-able index.json)."""
    curves = []
    for cls in list_all_classes():
        # Skip duplicates: classes module contains a sub-package
        # ``skills`` which is also walked; its ``skills/__init__.py``
        # might export python classes — but list_all() already filters.
        curves.append(compute_class_growth(
            class_profile=cls, max_level=max_level, policy=policy,
        ))
    curves.sort(key=lambda c: (c.baseline.tier, c.baseline.type_id))
    return curves


def all_hero_curves(*, max_level: int, policy: GrowthPolicy) -> List[ClassGrowthCurve]:
    curves = []
    for hero in list_all_heroes():
        curves.append(compute_hero_growth(
            hero_profile=hero, max_level=max_level, policy=policy,
        ))
    curves.sort(key=lambda c: c.baseline.type_id)
    return curves


__all__ = [
    "ClassGrowthCurve",
    "compute_class_growth",
    "compute_hero_growth",
    "all_class_curves",
    "all_hero_curves",
]
