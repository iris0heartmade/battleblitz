"""
Abstract base class for hero characters (具名角色).

A hero is a named character derived from one of the base unit classes
(see ``app.classes.units``). It re-uses the base class's combat
framework (HP / ATK / DEF / range / skills) but lets the designer
override individual stat values and provide bespoke art assets
(grid sprite, dialog portrait, dialog crest).

The hero system lives in its own package, parallel to
``classes/units/``, because:

  * Heroes are content (designer / writer facing) — there might be
    hundreds across a long campaign.  Keeping them in their own
    module avoids polluting the unit-class registry.
  * A hero MUST reference an existing base class by ``base_class_id``;
    you cannot create a hero with stats that violate the type
    matrix (e.g. a magic-only stat block on a "physical" base).

To add a new hero:
  1. Create ``game/app/classes/heroes/<hero_id>.py``.
  2. Subclass ``BaseHero`` and fill in every abstract attribute.
  3. Drop the asset files into ``game/app/web/assets/heroes/`` and
     reference them by relative path under ``asset_root``.
  4. The registry auto-discovers the hero on next process start —
     no edits to config / game_logic required.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import ClassVar, List, Mapping, Optional, Tuple

from app.commanders import CommanderPassive, CommanderPower


# ----------------------------------------------------------------
# Compiled hero profile (returned by BaseHero.compile())
# ----------------------------------------------------------------

@dataclass(frozen=True)
class HeroProfile:
    """Immutable snapshot of a hero.  Safe to cache."""
    hero_id: str                # "yun"
    display_cn: str             # "云"
    base_class_id: str          # "swordsman" — must exist in classes/units registry

    # Stat overrides.  None = inherit from base class.
    # Designers can tweak a single stat (e.g. ATK +2) without
    # having to copy every other field.
    hp_override: Optional[int]
    atk_override: Optional[int]
    def_override: Optional[int]
    matk_override: Optional[int]
    mdef_override: Optional[int]
    # Movement tiles per turn (the only movement stat; see spec §9).
    mov_override: Optional[int]
    # Per-stat personal growth modifier (%).  Combined with the base
    # class's class_growth_rates by RolledGrowthPolicy, then clamped
    # to [0, 100].  Positive values = hero is better at this stat
    # than the class baseline; negative values = worse.
    # Keys must be a subset of STAT_KEYS in app.progression.policies.
    personal_growth_modifier: Mapping[str, int]
    terrain_movement: Mapping[str, Mapping[str, int | bool]]

    # ── Skill bindings (P2.6+ reservation) ────────────────────
    # Character-specific skills ON TOP OF the base class's
    # ``default_skills``.  Skills themselves still live in
    # ``app.classes.units.skills`` — heroes only declare WHICH
    # skills they get by ID.  At spawn time the helper computes
    #
    #     final_skills = base.default_skills
    #                  ∪ hero.active_skills
    #                  ∪ hero.passive_skills
    #
    # (deduped, order preserved) and writes the union to
    # ``Unit.skills``.  Unknown skill IDs are warned about at
    # registry load time, not at spawn time, so a mistyped
    # reference can't break a running game.
    active_skills: Tuple[str, ...]
    passive_skills: Tuple[str, ...]

    # Art assets, served by FastAPI under /ui/assets/heroes/<...>.
    # The registry stores them as *relative* paths under
    # ``asset_root``; the API layer joins them with the assets URL.
    sprite_path: str            # "yun.png"        — grid sprite
    portrait_path: str          # "portrait_yun.png"
    crest_path: str             # "crest_yun.png"  — small dialog avatar

    # Optional dialog metadata.  When ``dialogue_name`` is set, the
    # dialog system resolves the speaker by this name (e.g. a scene
    # declaring ``speaker: "云"`` will look up this hero).
    dialogue_name: Optional[str] = None

    # Commander metadata.
    is_commander: bool = False
    commander_passive: Optional[CommanderPassive] = None
    commander_power: Optional[CommanderPower] = None
    power_threshold: Optional[int] = None


# ----------------------------------------------------------------
# Abstract base
# ----------------------------------------------------------------

class BaseHero(ABC):
    """Interface every hero file must implement.

    All attributes are class-level so the registry can read them
    without instantiating.  The hero is deliberately *stat-light*
    (no MP pool, no morale, no exp) — those come from the base
    class at spawn time.
    """

    # ── Identity ───────────────────────────────────────────────
    hero_id: ClassVar[str]              # "yun"
    display_cn: ClassVar[str]           # "云"
    # Which base unit class this hero derives from.  Must be a
    # registered type_id in ``app.classes.units``.
    base_class_id: ClassVar[str]        # "swordsman"

    # ── Stat overrides (None = inherit from base class) ────────
    hp_override: ClassVar[Optional[int]] = None
    atk_override: ClassVar[Optional[int]] = None
    def_override: ClassVar[Optional[int]] = None
    matk_override: ClassVar[Optional[int]] = None
    mdef_override: ClassVar[Optional[int]] = None
    # Movement tiles per turn.  This is the SOLE movement stat — see
    # spec §9 (the previous separate `mp_pool` field was removed
    # in the growth-redesign commit).
    mov_override: ClassVar[Optional[int]] = None
    # Personal growth modifier on top of the base class's
    # class_growth_rates.  See RolledGrowthPolicy and spec §8.
    # Empty dict = no modification (hero grows exactly like the class).
    personal_growth_modifier: ClassVar[Mapping[str, int]] = {}
    # Hero entries override only the specified keys of their base class's
    # terrain movement profile (for example, a river-crossing talent).
    terrain_movement: ClassVar[Mapping[str, Mapping[str, int | bool]]] = {}

    # ── Skill bindings (P2.6+ reservation) ────────────────────
    # IDs of skills this hero gets ON TOP of its base class's
    # default_skills.  Skills are still defined in
    # ``app.classes.units.skills``; the registry validates every
    # ID at load time and warns (does not crash) on unknown ones.
    # The ``active`` / ``passive`` split mirrors the skill
    # package's own split — passive skills auto-trigger in combat,
    # active skills need a manual action via ``POST /skill``.
    active_skills: ClassVar[List[str]] = []    # character-specific active skill IDs
    passive_skills: ClassVar[List[str]] = []   # character-specific passive skill IDs

    # ── Art assets (relative to web/assets/heroes/) ────────────
    sprite_path: ClassVar[str]          # "yun.png"
    portrait_path: ClassVar[str]        # "portrait_yun.png"
    crest_path: ClassVar[str]           # "crest_yun.png"

    # ── Dialog binding ─────────────────────────────────────────
    # When set, dialog scenes declaring ``speaker: <dialogue_name>``
    # resolve to this hero's portrait / crest automatically.
    # If unset, the dialog system falls back to matching by
    # ``display_cn``.
    dialogue_name: ClassVar[Optional[str]] = None

    # Commander metadata.  Safe defaults keep non-commander heroes inert.
    is_commander: ClassVar[bool] = False
    commander_passive: ClassVar[Optional[CommanderPassive]] = None
    commander_power: ClassVar[Optional[CommanderPower]] = None
    power_threshold: ClassVar[Optional[int]] = None

    @classmethod
    def compile(cls) -> HeroProfile:
        """Return an immutable snapshot for use by the engine."""
        return HeroProfile(
            hero_id=cls.hero_id,
            display_cn=cls.display_cn,
            base_class_id=cls.base_class_id,
            hp_override=cls.hp_override,
            atk_override=cls.atk_override,
            def_override=cls.def_override,
            matk_override=cls.matk_override,
            mdef_override=cls.mdef_override,
            mov_override=cls.mov_override,
            personal_growth_modifier=dict(cls.personal_growth_modifier),
            terrain_movement={
                terrain: dict(rule)
                for terrain, rule in cls.terrain_movement.items()
            },
            active_skills=tuple(cls.active_skills),
            passive_skills=tuple(cls.passive_skills),
            sprite_path=cls.sprite_path,
            portrait_path=cls.portrait_path,
            crest_path=cls.crest_path,
            dialogue_name=cls.dialogue_name,
            is_commander=cls.is_commander,
            commander_passive=cls.commander_passive,
            commander_power=cls.commander_power,
            power_threshold=cls.power_threshold,
        )
