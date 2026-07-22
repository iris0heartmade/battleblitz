"""Game-mode configuration + generic-unit spawn helpers.

Defines how the two game modes (mainline campaign + free skirmish) compute
*generic* unit stats from their class base.  Per Phase 2 of the dual-track
design (docs/规范/双轨制单位模型设计方案.md §6.5):

  - Mainline:  Generic spawns at L1 → result == class.L1 base.
  - Free:      Generic spawns at L10 → class.base + 9 × Boss-autolevel rate.

Hero spawn is NOT implemented here — that depends on the user's design
draft for the 10 named heroes (FE8-style per-character growth).
See :func:`spawn_hero_stats` (intentionally raises NotImplementedError).

Auto-level rate table (FE8 Boss pattern)
----------------------------------------
Boss-class units in FE8 don't roll per-character growth; they get a
fixed per-level autolevel bump on each stat:

    HP  85  /  Atk 50  /  Skl 10  /  Spd 10
    Def 10  /  Res 15  /  Lck 30

This caps variance and keeps the generic roster *predictable* on each
chapter — chapter multiplier (attack_modifier / level_offset) is the
real knob for difficulty, not random rolls.

For Skl/Spd/Res/Lck we currently only have HP/Atk/Def/MAtk/MDef on the
:class:`UnitClassProfile` — the missing four stats are filled with 0 as
TODO.  They will gain first-class fields in Phase 1 step 4 (Hero roster),
which needs the full 7-stat surface anyway.

Module surface
-------------
- :class:`GameMode` enum                 — mainline / free / tutorial
- :class:`ModeConfig` dataclass (frozen) — start_level + chapter_multiplier
- :func:`ModeConfig.mainline()`           — campaign default
- :func:`ModeConfig.free()`               — free-for-all default at L10
- :data:`AUTOEVEL_RATES`                 — FE8 Boss autolevel per stat
- :func:`spawn_generic_stats()`           — bulk stats for a generic unit
- :func:`spawn_hero_stats()`              — STUB / raises NotImplementedError
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from app.classes.units import get
from app.progression.policies import lane_growth_rates


# ============================================================
# Game-mode enum
# ============================================================

class GameMode(str, Enum):
    """Three top-level game modes (Phase 2 双轨制)."""

    MAINLINE = "mainline"
    FREE = "free"
    TUTORIAL = "tutorial"


# ============================================================
# Per-mode configuration (frozen — set once at session start)
# ============================================================

@dataclass(frozen=True)
class ModeConfig:
    """How a particular game-mode's spawn helper computes stats.

    Frozen: configure once at session start and pass to spawn helpers.
    Phase 2 §6.5.5 — implemented here, spawned below in :func:`spawn_generic_stats`.
    """

    name: GameMode
    start_level: int = 1
    chapter_multiplier: float = 1.0
    autolevel_pace: Literal["boss", "class"] = "boss"

    # ---------------------------------------------------------------
    # Builders for the two supported modes.
    # ---------------------------------------------------------------

    @classmethod
    def mainline(cls) -> "ModeConfig":
        """Campaign-mode default: L1 spawns, no chapter multiplier.

        Hero at L1 ≈ FE8 L4 expected (class.base + 3×growth/100).  Generic
        at L1 = class.base directly.  Player/Enemy spawn from the same
        base — Hero starts slightly weaker but grows.
        """
        return cls(name=GameMode.MAINLINE, start_level=1, chapter_multiplier=1.0)

    @classmethod
    def free(cls, start_level: int = 10) -> "ModeConfig":
        """Free-for-all mode: every unit spawns at `start_level` (default 10).

        Generic gets class.base + 9 × Boss autolevel rate (see AUTOEVEL_RATES).
        Hero gets class.base + 9 × char_growth (per Phase 2 §6.5.2).
        """
        return cls(name=GameMode.FREE, start_level=start_level, chapter_multiplier=1.0)


# ============================================================
# Generic spawn
# ============================================================

# FE8 Boss autolevel rates — FE8 generic class (boss-tier) units gain a
# fixed per-level bump on each stat, NOT class growth.  Used by
# spawn_generic_stats at levels above L1.
AUTOEVEL_RATES: dict[str, int] = {
    "hp":   85,
    "atk":  50,
    "matk": 50,
    "def":  10,
    "mdef": 15,
}


def spawn_generic_stats(
    type_id: str,
    start_level: int = 1,
) -> dict[str, int]:
    """Compute generic unit stats at the given starting level.

    Per Phase 2 §6.5.3:

      - At L1 (= Mainline default): result == class.base.
      - At L+ (Free / Skirmish):
          result[hp] += (start_level - 1) × 85 / 100
          result[atk] += (start_level - 1) × 50 / 100
          result[def] += (start_level - 1) × 10 / 100
          …etc per AUTOEVEL_RATES.

    Returns a Dict of stat-name → int value.
    mov and attack_range are NOT scaled — they're class-static.

    Generic does NOT level up at runtime; this function is called once
    when the unit joins a battle.  Chapter-modifier (attack/defense
    multipliers) is applied separately by the spawn caller.
    """

    profile = get(type_id)
    levels_above_l1 = max(0, start_level - 1)
    rates = lane_growth_rates(profile.attack_kind)

    def grow(base: int, rate_key: str) -> int:
        rate = rates.get(rate_key, 0)
        return base + int(levels_above_l1 * rate / 100)

    return {
        # Core combat stats — autolevel-capable.
        "hp":   grow(profile.base_hp,   "hp"),
        "atk":  grow(profile.base_atk,  "atk"),
        "def":  grow(profile.base_def,  "def"),
        "matk": grow(profile.base_matk, "matk"),
        "mdef": grow(profile.base_mdef, "mdef"),
        # Static class metadata (never scales).
        "mov":          profile.base_mov,
        "attack_range": profile.attack_range,
    }


# ============================================================
# Apply-to-Unit helper (Phase 2 Step 2)
# ============================================================

def apply_spawn_generic_to_unit(
    unit,
    type_id: str,
    start_level: int = 1,
) -> None:
    """Mutate a Unit row in-place with generic spawn stats.

    Writes only the fields a generic unit cares about (hp/max_hp/atk/def/
    matk/mdef/mov).  Leaves hero_id, name, x/y, morale, skills, co_state
    etc. alone — those are populated by the caller.

    Per Phase 2 §6.5.3:
      start_level = 1 → fields == class.base
      start_level = N → fields += (N-1) × Boss autolevel rate.

    Notes:
      - Type-erased: takes ``unit`` as opaque object so this module
        doesn't need to import the Unit model (avoids circular import
        with app.models).
      - Skills are NOT applied here; :func:`spawn_generic_stats`
        doesn't carry skill info, and the existing spawn path adds
        ``list(uc.default_skills)`` separately.
      - Unit level is preserved from the caller's input — caller sets
        ``unit.level`` if needed before invoking this.
    """
    stats = spawn_generic_stats(type_id, start_level=start_level)
    unit.hp = stats["hp"]
    unit.max_hp = stats["hp"]
    unit.atk = stats["atk"]
    unit.def_ = stats["def"]
    unit.matk = stats["matk"]
    unit.mdef = stats["mdef"]
    unit.mov = stats["mov"]


# ============================================================
# Class-surface helper — also used during spawn to keep non-Generic
# fields honest.
# ============================================================

def unit_default_mp_pool(type_id: str) -> int:
    """Fallback mp_pool used when the spawn path needs an mp_pool number
    but the caller hasn't picked one explicitly.

    Pulled from :func:`app.classes.units.get` (the canonical mp_pool
    per class) — wrappers exist so future callers can override mp_pool
    via chapter config without editing game.py.
    """
    return get(type_id).mp_pool


# ============================================================
# Hero spawn — DEFERRED pending user's design draft
# ============================================================

def spawn_hero_stats(
    type_id: str,
    char_growth: dict[str, int],
    level: int = 1,
) -> dict[str, int]:
    """Compute hero unit stats at the given level.

    ⚠️  STUB — implementation pending user's Hero design draft.

    Per Phase 2 §4.2 the formula is::

        hero_l1_stat = class.base + 3 × class.growth / 100
        # (level - 4) additional levels at character-specific growth.

    But character growth depends on what the user chooses — e.g. whether
    the `char_growth` dict is anchored on class growth or character
    growth, whether Skl/Spd/Res/Lck ride class.base or Zero, etc.  Per
    the in-flight scope (Hero held back until design draft lands), this
    function deliberately raises rather than guess.
    """
    raise NotImplementedError(
        "spawn_hero_stats awaiting Hero design draft (per Phase 2 §4). "
        "Implement once character growth semantics are finalised."
    )
