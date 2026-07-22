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
    :class:`AutolevelPolicy`   — current default (FE8 Boss autolevel rates)
    :func:`resolve_effective_base` — shared helper for hero override composition
    :func:`infer_tier`              — current best-effort tier heuristic
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Dict, Mapping, Optional, Protocol, Tuple

from app.classes.heroes.base import BaseHero, HeroProfile
from app.classes.units.base import UnitClassProfile


# ============================================================
# Constants shared with the renderer
# ============================================================

#: The seven stat keys every chart axis knows about.  Order is the
#: canonical "physical → magic → utility" reading order used by every
#: small-multiples panel in the render layer.
STAT_KEYS: Tuple[str, ...] = (
    "hp",
    "atk",
    "def",
    "matk",
    "mdef",
    "mov",
    "mp",
)

#: Tier-2 class type_ids.  Kept as a module-level constant so the
#: renderer and any future policies see the same answer.
TIER2_TYPE_IDS: frozenset[str] = frozenset({
    "blade_master",
    "sniper",
    "paladin",
    "sage",
    "saint",
    "dragon_rider",
})


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
    formula_note: str

    def __post_init__(self) -> None:
        missing = [k for k in STAT_KEYS if k not in self.base_stats]
        if missing:
            raise ValueError(
                f"ClassBaseline[{self.type_id!r}] missing stat keys: {missing}"
            )


# ============================================================
# Shared helpers
# ============================================================

def resolve_effective_base(
    class_profile: UnitClassProfile,
    hero_profile: Optional[HeroProfile] = None,
) -> Dict[str, int]:
    """L1 stat map for a class, optionally with a hero's overrides.

    Resolution rules:
      - ``hp``     = hero.hp_override ?? class.base_hp
      - ``atk``    = hero.atk_override ?? class.base_atk
      - ``def``    = hero.def_override ?? class.base_def
      - ``matk``   = hero.matk_override ?? class.base_matk
      - ``mdef``   = hero.mdef_override ?? class.base_mdef
      - ``mov``    = hero.mov_override ?? class.base_mov
      - ``mp``     = hero.mp_pool_override ?? class.mp_pool

    A ``None`` override ALWAYS inherits from the base class; this
    matches the design intent of :class:`BaseHero` ("None = inherit").
    Same rules live in :func:`app.hero_domain.legacy_bridge
    .build_hero_character_template` — duplicated here so the chart
    tool doesn't need to import the HeroCampaignState machinery.
    """
    return {
        "hp":   _override(hero_profile.hp_override   if hero_profile else None, class_profile.base_hp),
        "atk":  _override(hero_profile.atk_override  if hero_profile else None, class_profile.base_atk),
        "def":  _override(hero_profile.def_override  if hero_profile else None, class_profile.base_def),
        "matk": _override(hero_profile.matk_override if hero_profile else None, class_profile.base_matk),
        "mdef": _override(hero_profile.mdef_override if hero_profile else None, class_profile.base_mdef),
        "mov":  _override(hero_profile.mov_override  if hero_profile else None, class_profile.base_mov),
        "mp":   _override(hero_profile.mp_pool_override if hero_profile else None, class_profile.mp_pool),
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


# ============================================================
# Policy Protocol + default impl
# ============================================================

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
    ) -> Mapping[str, int]:
        """Compute every stat at ``level``.  ``baseline_`` kwarg name
        avoids shadowing the builtin ``baseline`` (some lint configs
        otherwise complain)."""
        ...


# ============================================================
# Default impl — current production formula
# ============================================================

class AutolevelPolicy:
    """FE8 Boss autolevel growth.

    Stats grow linearly per level-above-L1, scaled by a per-stat
    rate (units of *percent* of base).  Identical to the formula
    currently used by :func:`app.modes.spawn_generic_stats` so the
    chart tool's numbers match the spawn path's numbers.

    Stats NOT in :data:`RATE_KEYS` (mov, mp) grow by 0% — they
    stay at L1 value for the chart's full level range, which
    honestly tells the reader "MOV/MP are static for this class".
    """

    name: ClassVar[str] = "autolevel_boss"

    # Same dict as app.modes.AUTOEVEL_RATES — duplicated here so
    # this module is self-contained; if the rate set changes, both
    # must update together.  Future refactor: lift to a single
    # constants module.
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
        if is_hero:
            type_id = hero_profile.hero_id
            label_cn = hero_profile.display_cn
            label_en = type_id.title()  # HeroProfile has no display_en yet
            base_class_id = hero_profile.base_class_id
            note = (
                "英雄暂沿用 generic 公式 (autolevel_boss),"
                "等待 HeroDesign 落地后切到独立公式"
            )
        else:
            type_id = class_profile.type_id
            label_cn = class_profile.display_cn
            label_en = class_profile.display_en
            base_class_id = None
            note = "FE8 Boss autolevel rates (app.modes.AUTOEVEL_RATES)"

        return ClassBaseline(
            type_id=type_id,
            label_cn=label_cn,
            label_en=label_en,
            tier=infer_tier(type_id=type_id, is_hero=is_hero),
            attack_kind=class_profile.attack_kind,  # heroes inherit attack_kind from base class
            is_hero=is_hero,
            base_class_id=base_class_id,
            base_stats=dict(base_stats),
            formula_note=note,
        )

    def stat_at_level(
        self,
        *,
        baseline_: ClassBaseline,
        level: int,
    ) -> Dict[str, int]:
        if level < 1:
            raise ValueError(f"level must be >= 1, got {level}")
        levels_above = level - 1
        out: Dict[str, int] = {}
        for k in STAT_KEYS:
            base = baseline_.base_stats[k]
            rate = self.RATE_KEYS.get(k, 0)
            out[k] = base + int(levels_above * rate / 100)
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
    if name == AutolevelPolicy.name:
        return AutolevelPolicy()
    raise KeyError(
        f"unknown growth policy: {name!r}. "
        f"Known: {[AutolevelPolicy.name]}"
    )


__all__ = [
    "STAT_KEYS",
    "TIER2_TYPE_IDS",
    "ClassBaseline",
    "GrowthPolicy",
    "AutolevelPolicy",
    "resolve_effective_base",
    "infer_tier",
    "get_policy",
]
