"""
Growth-policy abstraction — plug-point for stat growth formulas.

A :class:`GrowthPolicy` decides two things:

  1. **L1 baseline** for a unit (class or hero).  For a plain class the
     baseline is the class's static base stats; for a hero it is
     ``base class.L1 + hero.*_override``.  This is computed ONCE per
     entity.

  2. **stat_at_level()** for that entity at any level in
     ``[1, max_level]``.  Pure function of ``(baseline, level)``.

The whole point of this module is to keep the *formula* out of the
*renderer*.  When the team picks a different formula (FE8 growth-rolled
character growth, linear-with-talent-point, curve-table lookup, …)
the only thing that changes is which ``GrowthPolicy`` subclass is
registered — the rest of the codebase, including the chart tool,
never re-reads ``modes.AUTOEVEL_RATES``.

Why a Protocol and not an ABC?
    - Duck typing: a third-party module can satisfy the interface
      without subclassing our base.  The chart tool does not need
      ``isinstance`` checks; it only reads attributes.
    - No inheritance coupling: ``GROWTH_CURVES`` and ``AUTOEVEL_RATES``
      can stay where they are (no need to relocate).

Public surface (this module's responsibility — additions belong here):
    :class:`ClassBaseline`     — resolved L1 stat block + entity context
    :class:`GrowthPolicy`      — Protocol interface
    :class:`AutolevelPolicy`   — DEPRECATED legacy linear formula
    :class:`BattleLanePolicy`  — DEPRECATED lane-aware linear formula
    :class:`RolledGrowthPolicy`— FE8-style per-stat per-level roll
    :func:`resolve_effective_base` — shared helper for hero override composition
    :func:`infer_tier`              — current best-effort tier heuristic
    :data:`STAT_KEYS`               — canonical stat axis keys
    :data:`STAT_CAPS`               — module-level per-stat caps
    :data:`PROMOTION_BONUSES`       — flat bonus applied at promote()
    :func:`promotion_bonus_for`     — lookup helper
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field, replace
from typing import Callable, ClassVar, Dict, Mapping, Optional, Protocol, Tuple

from app.classes.heroes.base import BaseHero, HeroProfile
from app.classes.units.base import UnitClassProfile

logger = logging.getLogger(__name__)


# ============================================================
# Constants shared with the renderer
# ============================================================

#: The six stat keys every chart axis knows about.  Order is the
#: canonical "physical → magic → utility" reading order used by every
#: small-multiples panel in the render layer.
STAT_KEYS: Tuple[str, ...] = (
    "hp",
    "atk",
    "def",
    "matk",
    "mdef",
    "mov",
)

#: Per-stat caps (max value any unit can reach).  See spec §6.
#: Set generously so L20 t2 units feel meaningfully stronger than
#: L20 t1 units, not because they cap out earlier.
STAT_CAPS: Mapping[str, int] = {
    "hp":   120,
    "atk":   60,
    "def":   55,
    "matk":  60,
    "mdef":  55,
    "mov":   12,
}

#: Tier-2 class type_ids.  Kept as a module-level constant so the
#: renderer and any future policies see the same answer.
TIER2_TYPE_IDS: frozenset[str] = frozenset({
    "blade_master",
    "sniper",
    "paladin",
    "sage",
    "saint",
    "berserker",
})

#: Flat additive bonus applied ONCE at the moment of promote().
#: Keyed by the tier-1 type_id; value is the bonus per stat.  See
#: spec §7.3.  Tier-2 classes that have no entry (dragon_rider,
#: falcon_knight, bard) have no promotion bonus; this is intentional
#: — those classes have no current t2 replacement in the registry.
PROMOTION_BONUSES: Mapping[str, Mapping[str, int]] = {
    "swordsman":     {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 0},
    "archer":        {"hp": 3, "atk": 2, "def": 1, "matk": 0, "mdef": 3, "mov": 0},
    "lancer":        {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 1},
    "knight":        {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 1},
    "warlock":       {"hp": 2, "atk": 0, "def": 2, "matk": 3, "mdef": 4, "mov": 0},
    "healer":        {"hp": 2, "atk": 0, "def": 2, "matk": 2, "mdef": 4, "mov": 0},
    "warrior":       {"hp": 4, "atk": 3, "def": 1, "matk": 0, "mdef": 2, "mov": 0},
    # dragon_rider, falcon_knight, bard → no t2 currently, no bonus.
}


def promotion_bonus_for(type_id: str) -> Mapping[str, int]:
    """Return the flat promotion bonus for a tier-1 class.

    Returns an empty dict if the class has no bonus (e.g. it's already
    a tier-2 class, or it has no current promotion path).  The
    returned dict covers every key in :data:`STAT_KEYS` so callers
    can do `value[stat] += bonus.get(stat, 0)` unconditionally.
    """
    raw = PROMOTION_BONUSES.get(type_id, {})
    return {k: int(raw.get(k, 0)) for k in STAT_KEYS}


# ============================================================
# L1 baseline dataclass
# ============================================================

@dataclass(frozen=True)
class ClassBaseline:
    """Resolved L1 stat block + entity context.

    This is the data contract between the *policy layer* (this module)
    and the *data layer* (``tools/growth_charts/dataset.py``).  The
    renderer reads the resolved ``base_stats``; it never reads raw
    :class:`UnitClassProfile` / :class:`HeroProfile`.

    Attributes:
        type_id:        Stable id used for the output filename.
        label_cn:       Primary Chinese display name.
        label_en:       English display name (fallback: hero_id.title()).
        tier:           Promotion tier (1=base, 2=promoted).
        attack_kind:    "physical" / "magic".
        is_hero:        Whether this entity is a named character.
        base_class_id:  For heroes, the underlying class id; None for classes.
        base_stats:     L1 stat map.  MUST contain every key in :data:`STAT_KEYS`.
        class_growth_rates:
                        Per-stat % growth rate.  Set by the policy
                        (after class+personal merge, clamped to
                        [0, 100]).
        stat_caps:      Per-stat cap; defaults to module-level
                        :data:`STAT_CAPS` when the policy doesn't
                        override per-class.
        formula_note:   Human-readable note stamped onto the chart title.
                        Carries "what formula was used, what is stub" info.
    """

    type_id: str
    label_cn: str
    label_en: str
    tier: int
    attack_kind: str
    is_hero: bool
    base_class_id: Optional[str]
    base_stats: Mapping[str, int]
    class_growth_rates: Mapping[str, int]
    stat_caps: Mapping[str, int]
    formula_note: str

    def __post_init__(self) -> None:
        missing_stats = [k for k in STAT_KEYS if k not in self.base_stats]
        if missing_stats:
            raise ValueError(
                f"ClassBaseline[{self.type_id!r}] missing stat keys: {missing_stats}"
            )
        missing_rates = [k for k in STAT_KEYS if k not in self.class_growth_rates]
        if missing_rates:
            raise ValueError(
                f"ClassBaseline[{self.type_id!r}] missing growth-rate keys: {missing_rates}"
            )


# ============================================================
# Shared helpers
# ============================================================

def resolve_effective_base(
    class_profile: UnitClassProfile,
    hero_profile: Optional[HeroProfile] = None,
) -> Dict[str, int]:
    """L1 stat map for a class.

    Per spec §3 / §5: hero identity no longer overrides initial stat
    values — yun/yuanying/etc. shape their L1–L20 trajectory purely
    through ``personal_growth_modifier`` (added to the class's
    ``class_growth_rates`` for the roll-rate calculation).  The
    hero_profile argument is kept for API compatibility but is
    intentionally unused; future per-hero L1 overrides would be a
    new field on ``HeroProfile``, not a reintroduction of the old
    ``*_override`` family.

    Note: ``mp`` is no longer in the stat block — see spec §9
    (MOV/MP merge).  Runtime ``unit.mov`` and ``unit.mp`` continue
    to be distinct concepts (max vs remaining), but the source-of-truth
    is a single ``base_mov`` per class.
    """
    return {
        "hp":   class_profile.base_hp,
        "atk":  class_profile.base_atk,
        "def":  class_profile.base_def,
        "matk": class_profile.base_matk,
        "mdef": class_profile.base_mdef,
        "mov":  class_profile.base_mov,
    }


def _override(value, fallback):
    return fallback if value is None else value


def infer_tier(*, type_id: str, is_hero: bool) -> int:
    """Best-effort tier inference.

    Currently:
      - Every registered hero is tier-1 (promotions land in a class
        swap, see :mod:`app.hero_domain.promotion`).
      - Classes whose type_id is in :data:`TIER2_TYPE_IDS` are tier-2;
        everything else is tier-1.

    When the codebase gains first-class tier metadata on either
    Profile dataclass, replace this with a direct attribute read.
    """
    if is_hero:
        return 1
    return 2 if type_id in TIER2_TYPE_IDS else 1


def _resolve_effective_growth_rates(
    class_profile: UnitClassProfile,
    hero_profile: Optional[HeroProfile] = None,
) -> Dict[str, int]:
    """Per-stat effective growth rate (class + personal, clamped).

    Falls back to 0 for any stat the class didn't declare (a missing
    key is an authoring error, but we don't want to crash the
    registry on it — the warning is loud in
    ``app.classes.units._validate_class_growth_rates``).
    """
    class_rates = class_profile.class_growth_rates
    personal = hero_profile.personal_growth_modifier if hero_profile else {}
    out: Dict[str, int] = {}
    for s in STAT_KEYS:
        v = int(class_rates.get(s, 0)) + int(personal.get(s, 0))
        if v < 0:
            v = 0
        elif v > 100:
            v = 100
        out[s] = v
    return out


# ============================================================
# Policy Protocol + default impl
# ============================================================

#: Type alias for any object usable as an RNG source by the rolled
#: policy.  Two accepted shapes:
#:   1. ``random.Random`` (or any object with a ``.random()``
#:      method that returns a float in [0, 1)) — used in
#:      production for seeded, deterministic spawn rolls.
#:   2. A bare ``Callable[[], float]`` (e.g. ``random.random``)
#:      — used by the chart tool's CLI default.  We type it as
#:      a Protocol instead of importing ``random.Random`` to
#:      keep the type surface decoupled from the stdlib module.
class _RandomSource(Protocol):
    def random(self) -> float: ...


#: Public alias used by every policy method's ``rng`` kwarg.
#: Mirrors spec §10's "rng: Callable[[], float] = random.random"
#: signature while also accepting ``random.Random`` instances
#: (the production spawn path uses these for per-unit seeding).
RandomSource = Callable[[], float]


class GrowthPolicy(Protocol):
    """Stat growth formula — pluggable.

    Two methods, two responsibilities.  Implementations should be
    pure functions of their arguments (no IO, no global state, no
    monotonic counters) so the same baseline always yields the
    same chart.
    """

    #: Short stable name used by the CLI to pick an implementation.
    name: ClassVar[str]

    def baseline(
        self,
        *,
        class_profile: UnitClassProfile,
        hero_profile: Optional[HeroProfile] = None,
    ) -> ClassBaseline:
        """Resolve an entity's L1 stat block."""
        ...

    def stat_at_level(
        self,
        *,
        baseline_: ClassBaseline,
        level: int,
        rng: Optional[RandomSource] = None,
    ) -> Mapping[str, int]:
        """Compute every stat at ``level``.  ``baseline_`` kwarg name
        avoids shadowing the builtin ``baseline`` (some lint configs
        otherwise complain).  See :data:`RandomSource` for accepted
        ``rng`` shapes."""
        ...


# ============================================================
# Default impl — current production formula
# ============================================================

class AutolevelPolicy:
    """DEPRECATED: replaced by RolledGrowthPolicy.

    Stats grow linearly per level-above-L1, scaled by a per-stat
    rate (units of *percent* of base).  Identical to the formula
    previously used by :func:`app.modes.spawn_generic_stats` so
    the chart tool's --policy=autolevel_boss keeps working for
    A/B comparison PNGs.  New code should use RolledGrowthPolicy.

    Stats NOT in :data:`RATE_KEYS` (mov) grow by 0% — they stay at
    L1 value for the chart's full level range, which honestly tells
    the reader "MOV is static for this class".
    """

    name: ClassVar[str] = "autolevel_boss"

    RATE_KEYS: ClassVar[Dict[str, int]] = {
        "hp":   85,
        "atk":  50,
        "matk": 50,
        "def":  10,
        "mdef": 15,
    }

    def baseline(
        self,
        *,
        class_profile: UnitClassProfile,
        hero_profile: Optional[HeroProfile] = None,
    ) -> ClassBaseline:
        is_hero = hero_profile is not None
        base_stats = resolve_effective_base(class_profile, hero_profile)
        # AutolevelPolicy's RATE_KEYS is fixed; the class's
        # class_growth_rates are ignored on this legacy code path.
        growth_rates = dict(self.RATE_KEYS)
        growth_rates.setdefault("mov", 0)
        if is_hero:
            type_id = hero_profile.hero_id
            label_cn = hero_profile.display_cn
            label_en = type_id.title()
            base_class_id = hero_profile.base_class_id
            note = "DEPRECATED autolevel_boss: 英雄未启用独立公式"
        else:
            type_id = class_profile.type_id
            label_cn = class_profile.display_cn
            label_en = class_profile.display_en
            base_class_id = None
            note = "DEPRECATED FE8 Boss autolevel rates (linear)"

        return ClassBaseline(
            type_id=type_id,
            label_cn=label_cn,
            label_en=label_en,
            tier=infer_tier(type_id=type_id, is_hero=is_hero),
            attack_kind=class_profile.attack_kind,
            is_hero=is_hero,
            base_class_id=base_class_id,
            base_stats=dict(base_stats),
            class_growth_rates=growth_rates,
            stat_caps=dict(STAT_CAPS),
            formula_note=note,
        )

    def stat_at_level(
        self,
        *,
        baseline_: ClassBaseline,
        level: int,
        rng: Callable[[], float] = random.random,  # unused
    ) -> Dict[str, int]:
        if level < 1:
            raise ValueError(f"level must be >= 1, got {level}")
        levels_above = level - 1
        out: Dict[str, int] = {}
        for k in STAT_KEYS:
            base = baseline_.base_stats[k]
            rate = baseline_.class_growth_rates.get(k, 0)
            out[k] = base + int(levels_above * rate / 100)
        return out


class BattleLanePolicy(AutolevelPolicy):
    """DEPRECATED: replaced by RolledGrowthPolicy.

    Lane-aware battle growth.  Kept for chart-tool A/B comparison
    only.  See spec for the rationale of deprecation.
    """

    name: ClassVar[str] = "battle_lane"

    STRONG_OFFENSE_RATE: ClassVar[int] = 50
    WEAK_OFFENSE_RATE: ClassVar[int] = 10
    STRONG_DEFENSE_RATE: ClassVar[int] = 15
    WEAK_DEFENSE_RATE: ClassVar[int] = 10
    HP_RATE: ClassVar[int] = 85

    def baseline(
        self,
        *,
        class_profile: UnitClassProfile,
        hero_profile: Optional[HeroProfile] = None,
    ) -> ClassBaseline:
        bl = super().baseline(class_profile=class_profile, hero_profile=hero_profile)
        if bl.is_hero:
            note = "DEPRECATED battle_lane: 英雄继承基础职业强/弱侧成长"
        else:
            note = "DEPRECATED battle_lane: 按职业 attack_kind 分配强侧/弱侧成长"
        return replace(bl, formula_note=note)

    def stat_at_level(
        self,
        *,
        baseline_: ClassBaseline,
        level: int,
        rng: Callable[[], float] = random.random,  # unused
    ) -> Dict[str, int]:
        if level < 1:
            raise ValueError(f"level must be >= 1, got {level}")
        levels_above = level - 1
        rates = lane_growth_rates(baseline_.attack_kind)
        out: Dict[str, int] = {}
        for k in STAT_KEYS:
            base = baseline_.base_stats[k]
            rate = rates.get(k, 0)
            out[k] = base + int(levels_above * rate / 100)
        return out


def lane_growth_rates(attack_kind: str) -> Dict[str, int]:
    """Return per-stat fixed growth rates for a combat lane."""
    if attack_kind == "magic":
        return {
            "hp": BattleLanePolicy.HP_RATE,
            "atk": BattleLanePolicy.WEAK_OFFENSE_RATE,
            "def": BattleLanePolicy.WEAK_DEFENSE_RATE,
            "matk": BattleLanePolicy.STRONG_OFFENSE_RATE,
            "mdef": BattleLanePolicy.STRONG_DEFENSE_RATE,
        }
    return {
        "hp": BattleLanePolicy.HP_RATE,
        "atk": BattleLanePolicy.STRONG_OFFENSE_RATE,
        "def": BattleLanePolicy.STRONG_DEFENSE_RATE,
        "matk": BattleLanePolicy.WEAK_OFFENSE_RATE,
        "mdef": BattleLanePolicy.WEAK_DEFENSE_RATE,
    }


# ============================================================
# RolledGrowthPolicy — FE8-style per-stat per-level roll
# ============================================================

class RolledGrowthPolicy:
    """FE8-style per-stat per-level roll, with three-tier outcome.

    Per level-up, per stat, two rolls:
      r1 = rng() * 100
      if r1 < rate:                 # "did this stat grow?"
          r2 = rng() * 100
          if r2 < 25: delta = 2
          elif r2 < 95: delta = 1
          else:       delta = 0
          value = min(value + delta, cap)

    The first roll's "hit" rate is the per-stat growth rate.  The
    second roll is the magnitude distribution (25% +2 / 70% +1 /
    5% +0).  The 5% +0 is a knob for future tuning even though the
    spec calls for "no 0"; preserving it costs nothing.

    `rng` is injected per call so unit tests can pass a seeded
    ``Random()`` instance for deterministic deltas.  No global RNG
    mutation, matching the GrowthPolicy Protocol's "no IO, no
    monotonic counters" contract.
    """

    name: ClassVar[str] = "rolled"

    #: Probability of triggering the "amount" roll (the "did it grow?" check).
    #: Always 100 at the start of a stat_at_level call — `rate` is the
    #: per-stat growth rate resolved by baseline() (in [0, 100]).
    #: Kept as a class constant so the two-roll mechanic is searchable
    #: in one place.
    HIT_THRESHOLD: ClassVar[int] = 100
    #: Magnitude distribution breakpoints (cumulative, in [0, 100)).
    P2_THRESHOLD: ClassVar[int] = 25
    P1_THRESHOLD: ClassVar[int] = 95

    def baseline(
        self,
        *,
        class_profile: UnitClassProfile,
        hero_profile: Optional[HeroProfile] = None,
    ) -> ClassBaseline:
        is_hero = hero_profile is not None
        base_stats = resolve_effective_base(class_profile, hero_profile)
        # Growth rate = class's class_growth_rates + hero's personal
        # modifier, clamped to [0, 100].  See _resolve_effective_growth_rates.
        growth_rates = _resolve_effective_growth_rates(class_profile, hero_profile)
        # Per-class stat_caps override the module-level default.
        caps = dict(class_profile.stat_caps) if class_profile.stat_caps else dict(STAT_CAPS)
        if is_hero:
            type_id = hero_profile.hero_id
            label_cn = hero_profile.display_cn
            label_en = type_id.title()
            base_class_id = hero_profile.base_class_id
            note = "rolled: 职业成长率 + 个人成长 modifier(clamp 0~100)"
        else:
            type_id = class_profile.type_id
            label_cn = class_profile.display_cn
            label_en = class_profile.display_en
            base_class_id = None
            note = "rolled: 职业 class_growth_rates,每级每项独立掷骰"

        return ClassBaseline(
            type_id=type_id,
            label_cn=label_cn,
            label_en=label_en,
            tier=infer_tier(type_id=type_id, is_hero=is_hero),
            attack_kind=class_profile.attack_kind,
            is_hero=is_hero,
            base_class_id=base_class_id,
            base_stats=dict(base_stats),
            class_growth_rates=growth_rates,
            stat_caps=caps,
            formula_note=note,
        )

    def stat_at_level(
        self,
        *,
        baseline_: ClassBaseline,
        level: int,
        rng: Optional[RandomSource] = None,
    ) -> Dict[str, int]:
        if level < 1:
            raise ValueError(f"level must be >= 1, got {level}")
        if rng is None:
            rng = random.random
        out = dict(baseline_.base_stats)
        for _ in range(2, level + 1):
            out = self.roll_level_up(
                current_stats=out, baseline_=baseline_, rng=rng,
            )
        return out

    def roll_level_up(
        self,
        *,
        current_stats: Mapping[str, int],
        baseline_: ClassBaseline,
        rng: Optional[RandomSource] = None,
    ) -> Dict[str, int]:
        """Apply one level-up's rolls to ``current_stats`` and return
        a new dict (does not mutate the input).  Useful for runtime
        level-up events that don't have an L1 baseline handy.

        `rng` may be a bare callable returning a float in [0, 1)
        (e.g. ``random.random``) or any object exposing a
        ``.random()`` method with the same contract (e.g.
        ``random.Random(seed)``).  Pass ``None`` to fall back to
        ``random.random`` (non-deterministic; intended for the
        chart tool's CLI default, NOT for production spawn paths).
        """
        if rng is None:
            rng = random.random
        out = dict(current_stats)
        for s in STAT_KEYS:
            rate = baseline_.class_growth_rates.get(s, 0)
            if rate <= 0:
                continue
            if rng.random() * 100 >= rate:  # type: ignore[union-attr]
                continue
            # Hit: roll magnitude.
            r2 = rng.random() * 100  # type: ignore[union-attr]
            if r2 < self.P2_THRESHOLD:
                delta = 2
            elif r2 < self.P1_THRESHOLD:
                delta = 1
            else:
                delta = 0
            if delta == 0:
                continue
            cap = baseline_.stat_caps.get(s, STAT_CAPS.get(s, 999))
            out[s] = min(out[s] + delta, cap)
        return out


# ============================================================
# Registry — single entry-point for the CLI & dataset layer
# ============================================================

def get_policy(name: str) -> GrowthPolicy:
    """Resolve a policy by short name.  Used by the CLI's --policy flag.

    The registry is a flat dict — adding a new policy means
    (1) implementing the Protocol, (2) registering it here.  No
    ABC, no metaclass trickery.
    """
    if name == RolledGrowthPolicy.name:
        return RolledGrowthPolicy()
    if name == BattleLanePolicy.name:
        return BattleLanePolicy()
    if name == AutolevelPolicy.name:
        return AutolevelPolicy()
    raise KeyError(
        f"unknown growth policy: {name!r}. "
        f"Known: {[RolledGrowthPolicy.name, BattleLanePolicy.name, AutolevelPolicy.name]}"
    )


__all__ = [
    "STAT_KEYS",
    "STAT_CAPS",
    "TIER2_TYPE_IDS",
    "PROMOTION_BONUSES",
    "promotion_bonus_for",
    "ClassBaseline",
    "GrowthPolicy",
    "AutolevelPolicy",
    "BattleLanePolicy",
    "RolledGrowthPolicy",
    "RandomSource",
    "lane_growth_rates",
    "resolve_effective_base",
    "infer_tier",
    "get_policy",
]
