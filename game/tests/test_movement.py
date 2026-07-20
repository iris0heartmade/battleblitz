"""Regression tests for data-driven terrain movement profiles."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.classes.units import get as get_unit
from app.movement import (
    can_end_on_terrain,
    can_traverse_terrain,
    profile_from_rules,
    terrain_cost_x2,
    movement_key,
)
from app.utils import bfs_reachable, pathfind


@pytest.mark.unit
def test_dragon_rider_crosses_wall_without_ending_on_it() -> None:
    profile = profile_from_rules(get_unit("dragon_rider").terrain_movement)
    terrain = {(x, 0): "plain" for x in range(3)}
    terrain[(1, 0)] = "castle_wall"
    owners = {(x, 0): None for x in range(3)}

    assert can_traverse_terrain(profile, "castle_wall") is True
    assert can_end_on_terrain(profile, "castle_wall") is False
    assert (1, 0) not in bfs_reachable(
        (0, 0), terrain, owners, mov=3, viewer_owner_id=None,
        movement_profile=profile, size=3,
    )
    assert pathfind(
        (0, 0), (2, 0), terrain, owners, mov=3, viewer_owner_id=None,
        movement_profile=profile, size=3,
    ) == [(0, 0), (1, 0), (2, 0)]


@pytest.mark.unit
def test_later_hero_rule_overrides_only_the_specified_field() -> None:
    profile = profile_from_rules(
        {"river": {"cost_override_x2": 4, "can_end_on": True}},
        {"river": {"cost_delta_x2": -2}},
    )
    assert can_end_on_terrain(profile, "river") is True
    assert terrain_cost_x2(profile, "river") == 2


@pytest.mark.unit
def test_castle_subtype_is_the_effective_movement_key() -> None:
    tile = SimpleNamespace(terrain="castle", subtype="castle_wall")
    assert movement_key(tile) == "castle_wall"
