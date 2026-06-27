"""
Abstract base class for all unit types (combat classes).

Each unit type (Swordsman, Archer, Knight, Healer, …) is a single .py file
that declares its identity, base stats, starting skills, and type-advantage
relationships.  The engine reads all unit classes from the registry in
`__init__.py` and never hard-codes unit type strings.

To add a new unit type:
  1. Create `game/app/classes/units/assassin.py`
  2. Subclass `BaseUnitClass`
  3. Set all abstract attributes
  4. The registry auto-discovers it — zero changes to config / game_logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple


# ----------------------------------------------------------------
# Compiled stat block (returned by BaseUnitClass.compile())
# ----------------------------------------------------------------

@dataclass(frozen=True)
class UnitClassProfile:
    """Immutable snapshot of a unit class.  Safe to cache."""
    type_id: str               # "swordsman"
    display_cn: str            # "剑士"
    display_en: str            # "Swordsman"
    glyph: str                 # "剑"
    base_hp: int
    base_atk: int
    base_def: int
    base_mov: int
    mp_pool: int
    default_skills: Tuple[str, ...]
    attack_range: int          # 1 = melee, 2+ = ranged (max Manhattan distance)
    can_move_after_action: bool
    min_attack_range: int = 0 # 0 = can melee at d=1; 1 = must keep distance (ranged-only)
    strong_against: FrozenSet[str] = frozenset()  # e.g. {"knight"}


# ----------------------------------------------------------------
# Abstract base
# ----------------------------------------------------------------

class BaseUnitClass(ABC):
    """Interface every unit type file must implement.

    All attributes are class-level so the registry can read them without
    instantiating.
    """

    # ── Identity ───────────────────────────────────────────────
    type_id: ClassVar[str]               # "swordsman"
    display_cn: ClassVar[str]            # "剑士"
    display_en: ClassVar[str]            # "Swordsman"
    glyph: ClassVar[str]                 # "剑"

    # ── Stats ──────────────────────────────────────────────────
    base_hp: ClassVar[int]               # 45
    base_atk: ClassVar[int]              # 18
    base_def: ClassVar[int]              # 12
    base_mov: ClassVar[int]              # 3
    mp_pool: ClassVar[int]               # 5

    # ── Skills ─────────────────────────────────────────────────
    default_skills: ClassVar[List[str]]  # [] / ["snipe"] / ["heal", "rally"]
    attack_range: ClassVar[int] = 1      # 1 = melee, 2+ = ranged (max Manhattan)
    min_attack_range: ClassVar[int] = 0 # 0 = can attack d=1; 1 = ranged-only (no melee)

    # ── Mobility ───────────────────────────────────────────────
    can_move_after_action: ClassVar[bool] = False

    # ── Type advantage ─────────────────────────────────────────
    strong_against: ClassVar[List[str]] = []  # e.g. ["knight"]  (used by compile() default)

    @classmethod
    def compile(cls) -> UnitClassProfile:
        """Return an immutable snapshot for use by the engine."""
        return UnitClassProfile(
            type_id=cls.type_id,
            display_cn=cls.display_cn,
            display_en=cls.display_en,
            glyph=cls.glyph,
            base_hp=cls.base_hp,
            base_atk=cls.base_atk,
            base_def=cls.base_def,
            base_mov=cls.base_mov,
            mp_pool=cls.mp_pool,
            default_skills=tuple(cls.default_skills),
            attack_range=cls.attack_range,
            min_attack_range=cls.min_attack_range,
            can_move_after_action=cls.can_move_after_action,
            strong_against=frozenset(cls.strong_against),
        )
