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


@pytest.mark.asyncio
async def test_move_route_accepts_tiles_beyond_legacy_15_on_20x20_map(client, db_session) -> None:
    from sqlalchemy import select

    from app.models import Tile, Unit

    resp = await client.post("/games", json={
        "name": "20x20 movement bounds",
        "map_preset": "red_full_roster_4p_20",
    })
    assert resp.status_code == 201, resp.text
    game_id = resp.json()["id"]

    join = await client.post(f"/games/{game_id}/join", json={"user_name": "host"})
    assert join.status_code == 201, join.text
    player_id = join.json()["id"]
    for _ in range(3):
        ai = await client.post(f"/games/{game_id}/add-ai", json={})
        assert ai.status_code == 201, ai.text
    start = await client.post(f"/games/{game_id}/start")
    assert start.status_code == 200, start.text

    unit = (await db_session.execute(
        select(Unit).where(Unit.player_id == player_id, Unit.unit_type == "dragon_rider")
    )).scalars().first()
    assert unit is not None

    old_tile = (await db_session.execute(
        select(Tile).where(Tile.game_id == game_id, Tile.x == unit.x, Tile.y == unit.y)
    )).scalars().first()
    new_tile = (await db_session.execute(
        select(Tile).where(Tile.game_id == game_id, Tile.x == 14, Tile.y == 10)
    )).scalars().first()
    assert old_tile is not None and new_tile is not None
    old_tile.occupied_unit_id = None
    new_tile.occupied_unit_id = unit.id
    unit.x = 14
    unit.y = 10
    unit.mp = unit.mov
    unit.has_moved = False
    unit.has_acted = False
    await db_session.commit()

    move = await client.post(f"/games/{game_id}/move", json={
        "player_id": player_id,
        "unit_id": unit.id,
        "to_x": 15,
        "to_y": 10,
    })

    assert move.status_code == 200, move.text
    assert move.json()["to_x"] == 15
    assert move.json()["to_y"] == 10
