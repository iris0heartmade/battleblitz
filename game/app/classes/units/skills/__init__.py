"""
Skill registry — auto-discovers every subclass of `BaseSkill` in this package.

Usage:
    from app.classes.units.skills import get, list_all, get_passive_for

    heal = get("heal")
    heal.can_use(ctx)   → True/False
    heal.describe(ctx)  → "💚+20 Sword"
    await heal.execute(session, ctx)  → SkillResult

    # Passive skills that auto-modify combat
    for sk in get_passive_for(unit):
        range = sk.modify_attack_range(range, unit)
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional

from app.classes.units.skills.base import BaseSkill

# ----------------------------------------------------------------
# Auto-discovery
# ----------------------------------------------------------------

_registry: Dict[str, type[BaseSkill]] = {}
_instances: Dict[str, BaseSkill] = {}
_initialized: bool = False


def _discover() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    pkg_path = Path(__file__).resolve().parent
    for _, module_name, _is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if module_name.startswith("_") or module_name in ("base",):
            continue
        try:
            mod = importlib.import_module(f"app.classes.units.skills.{module_name}")
        except ImportError:
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not isinstance(attr, type):
                continue
            if not issubclass(attr, BaseSkill):
                continue
            if attr is BaseSkill:
                continue

            inst = attr()
            _registry[inst.skill_id] = attr
            _instances[inst.skill_id] = inst


# ── Public API ──────────────────────────────────────────────


def get(skill_id: str) -> BaseSkill:
    _discover()
    return _instances[skill_id]


def get_or_none(skill_id: str) -> Optional[BaseSkill]:
    _discover()
    return _instances.get(skill_id)


def list_all() -> List[BaseSkill]:
    _discover()
    return list(_instances.values())


def get_passive_for(unit) -> List[BaseSkill]:
    """Return all passive skills owned by `unit`."""
    _discover()
    return [
        inst for inst in _instances.values()
        if inst.is_passive and inst.skill_id in (unit.skills or [])
    ]


def get_active_for(unit) -> List[BaseSkill]:
    """Return all active skills owned by `unit`."""
    _discover()
    return [
        inst for inst in _instances.values()
        if not inst.is_passive and inst.skill_id in (unit.skills or [])
    ]


def default_skills_for(unit_type_id: str) -> List[str]:
    """Which skill IDs does a unit class start with?"""
    _discover()
    return [
        inst.skill_id for inst in _instances.values()
        if unit_type_id in inst.default_users
    ]
