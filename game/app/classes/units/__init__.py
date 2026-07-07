"""
Unit class registry — the SINGLE source of truth for all unit types.

Usage:
    from app.classes.units import get, list_all, type_advantage

    knight = get("knight")
    knight.base_atk          # 22
    knight.strong_against    # frozenset({"archer"})

    type_advantage("swordsman", "knight")   # 1.20
    type_advantage("archer", "swordsman")   # 1.0

Adding a new unit type is a one-file change:
    1. Create `game/app/classes/units/<id>.py`
    2. Subclass `BaseUnitClass`, fill in all attributes
    3. Restart — auto-discovered.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.classes.units.base import BaseUnitClass, UnitClassProfile

# ----------------------------------------------------------------
# Auto-discovery
# ----------------------------------------------------------------

_registry: Dict[str, type[BaseUnitClass]] = {}
_profiles: Dict[str, UnitClassProfile] = {}
_advantage_table: Dict[Tuple[str, str], float] = {}
_initialized: bool = False


def _discover() -> None:
    """Walk `classes/units/` and register every `BaseUnitClass` subclass."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    pkg_path = Path(__file__).resolve().parent
    for _, module_name, _is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if module_name.startswith("_") or module_name in ("base",):
            continue
        try:
            mod = importlib.import_module(f"app.classes.units.{module_name}")
        except ImportError:
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not isinstance(attr, type):
                continue
            if not issubclass(attr, BaseUnitClass):
                continue
            if attr is BaseUnitClass:
                continue

            profile = attr.compile()
            _registry[profile.type_id] = attr
            _profiles[profile.type_id] = profile

    # Build type-advantage table (bidirectional: A→B = 1.20, B→A = 1.0)
    for pid, cls in _registry.items():
        for target in getattr(cls, "strong_against", []):
            _advantage_table[(pid, target)] = 1.20


# ── Public API ──────────────────────────────────────────────


def get(type_id: str) -> UnitClassProfile:
    """Return the immutable profile for a unit type.  Raises KeyError if unknown."""
    _discover()
    return _profiles[type_id]


def get_or_none(type_id: str) -> Optional[UnitClassProfile]:
    _discover()
    return _profiles.get(type_id)


def list_all() -> List[UnitClassProfile]:
    """All registered unit class profiles."""
    _discover()
    return list(_profiles.values())


def type_ids() -> List[str]:
    _discover()
    return list(_profiles.keys())


def type_advantage(attacker_type: str, defender_type: str) -> float:
    """Multiplier when `attacker_type` attacks `defender_type` (1.0 = neutral)."""
    _discover()
    return _advantage_table.get((attacker_type, defender_type), 1.0)
