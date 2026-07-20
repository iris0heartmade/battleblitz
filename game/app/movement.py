"""Data-driven terrain movement rules shared by every movement caller."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.config import TERRAIN_MOVE_COST

Rule = Mapping[str, int | bool]
RuleMap = Mapping[str, Rule]


@dataclass(frozen=True)
class MovementProfile:
    """Resolved class + hero terrain rules for one battle unit."""

    rules: dict[str, dict[str, int | bool]]

    def as_dict(self) -> dict[str, dict[str, int | bool]]:
        return {terrain: dict(rule) for terrain, rule in self.rules.items()}


def movement_key(tile_or_terrain: Any, subtype: Optional[str] = None) -> str:
    """Return the terrain key relevant to movement, preferring tile subtype."""
    if isinstance(tile_or_terrain, str):
        return subtype or tile_or_terrain
    return getattr(tile_or_terrain, "subtype", None) or getattr(tile_or_terrain, "terrain")


def _merge_rules(*rule_maps: RuleMap) -> MovementProfile:
    merged: dict[str, dict[str, int | bool]] = {}
    for rule_map in rule_maps:
        for terrain, rule in (rule_map or {}).items():
            target = merged.setdefault(str(terrain), {})
            for key, value in rule.items():
                if key not in {"cost_override_x2", "cost_delta_x2", "can_traverse", "can_end_on"}:
                    raise ValueError(f"unknown terrain movement key {key!r}")
                if key.startswith("cost_") and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ValueError(f"{terrain}.{key} must be an integer")
                if key.startswith("can_") and not isinstance(value, bool):
                    raise ValueError(f"{terrain}.{key} must be a boolean")
                target[key] = value
    return MovementProfile(merged)


def profile_from_rules(*rule_maps: RuleMap) -> MovementProfile:
    """Build a profile from ordered rule maps; later maps override earlier ones."""
    return _merge_rules(*rule_maps)


def resolve_movement_profile(unit: Any) -> MovementProfile:
    """Merge base-class rules with optional hero rules for an ORM unit."""
    from app.classes.units import get as get_unit
    from app.classes.heroes import get_or_none as get_hero

    unit_profile = get_unit(unit.unit_type)
    hero_profile = get_hero(unit.hero_id) if getattr(unit, "hero_id", None) else None
    return _merge_rules(
        unit_profile.terrain_movement or {},
        hero_profile.terrain_movement if hero_profile else {},
    )


def can_traverse_terrain(profile: MovementProfile, terrain: str) -> bool:
    rule = profile.rules.get(terrain, {})
    default = terrain in TERRAIN_MOVE_COST and TERRAIN_MOVE_COST[terrain] < 9999
    return bool(rule.get("can_traverse", default))


def can_end_on_terrain(profile: MovementProfile, terrain: str) -> bool:
    if not can_traverse_terrain(profile, terrain):
        return False
    return bool(profile.rules.get(terrain, {}).get("can_end_on", True))


def terrain_cost_x2(profile: MovementProfile, terrain: str) -> Optional[int]:
    """Return the resolved entering cost, or None for an untraversable tile."""
    if not can_traverse_terrain(profile, terrain):
        return None
    rule = profile.rules.get(terrain, {})
    cost = int(rule.get("cost_override_x2", TERRAIN_MOVE_COST.get(terrain, 9999)))
    cost += int(rule.get("cost_delta_x2", 0))
    return max(1, cost)


DEFAULT_MOVEMENT_PROFILE = MovementProfile({})


__all__ = [
    "DEFAULT_MOVEMENT_PROFILE", "MovementProfile", "can_end_on_terrain",
    "can_traverse_terrain", "movement_key", "profile_from_rules", "resolve_movement_profile",
    "terrain_cost_x2",
]
