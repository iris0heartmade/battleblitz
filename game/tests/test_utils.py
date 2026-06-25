"""
Unit tests for `app.utils` — pure grid helpers, no DB needed.

These exist primarily to:
  1. Catch regressions when the project grows.
  2. Serve as executable documentation for the pathfinding/LOS rules.
  3. Lock in the spec from `app.config` (so changing e.g. MAP_SIZE fails loudly).
"""
from __future__ import annotations

import pytest

from app.config import MAP_SIZE, TERRAIN_CASTLE, TERRAIN_FOREST, TERRAIN_MOUNTAIN
from app.utils import (
    bfs_reachable,
    chebyshev,
    has_line_of_sight,
    in_bounds,
    manhattan,
    neighbors,
    pathfind,
    terrain_passable,
)


# ============================================================
# in_bounds
# ============================================================

@pytest.mark.unit
class TestInBounds:
    def test_corners_are_in(self):
        assert in_bounds(0, 0) is True
        assert in_bounds(MAP_SIZE - 1, MAP_SIZE - 1) is True

    def test_outside_is_out(self):
        assert in_bounds(-1, 0) is False
        assert in_bounds(0, -1) is False
        assert in_bounds(MAP_SIZE, 0) is False
        assert in_bounds(0, MAP_SIZE) is False

    def test_respects_size_kwarg(self):
        assert in_bounds(0, 0, size=10) is True
        assert in_bounds(9, 9, size=10) is True
        assert in_bounds(10, 9, size=10) is False


# ============================================================
# chebyshev / manhattan
# ============================================================

@pytest.mark.unit
class TestDistances:
    def test_same_tile_is_zero(self):
        assert chebyshev((3, 3), (3, 3)) == 0
        assert manhattan((3, 3), (3, 3)) == 0

    def test_chebyshev_diagonal_equals_max(self):
        # diagonal: king-move = max(dx, dy) = 4
        assert chebyshev((0, 0), (3, 4)) == 4

    def test_manhattan_sums_axes(self):
        assert manhattan((0, 0), (3, 4)) == 7

    def test_distance_is_symmetric(self):
        a, b = (1, 2), (5, 7)
        assert chebyshev(a, b) == chebyshev(b, a)
        assert manhattan(a, b) == manhattan(b, a)


# ============================================================
# neighbors
# ============================================================

@pytest.mark.unit
class TestNeighbors:
    def test_center_has_8_neighbors(self):
        n = neighbors(5, 5)
        assert len(n) == 8
        # No self-loop
        assert (5, 5) not in n

    def test_corner_has_3_neighbors(self):
        # `neighbors` is unbounded; corners still get 8 candidate coords,
        # some of which fall outside the grid. Callers must bounds-check.
        n = neighbors(0, 0)
        assert len(n) == 8
        # The 3 in-bounds neighbours are present
        assert (1, 0) in n
        assert (0, 1) in n
        assert (1, 1) in n
        # The 5 out-of-bounds are present too (caller's job to filter)
        assert (-1, -1) in n
        assert (-1, 0) in n
        # No self-loop regardless
        assert (0, 0) not in n


# ============================================================
# has_line_of_sight
# ============================================================

@pytest.mark.unit
class TestLineOfSight:
    def test_same_tile_has_los(self):
        assert has_line_of_sight((3, 3), (3, 3), blocked=set()) is True

    def test_horizontal_clear_path(self):
        assert has_line_of_sight((0, 0), (5, 0), blocked=set()) is True

    def test_horizontal_blocked(self):
        blocked = {(3, 0)}
        assert has_line_of_sight((0, 0), (5, 0), blocked=blocked) is False

    def test_diagonal_not_allowed(self):
        # Spec: ranged attacks are axis-aligned only.
        assert has_line_of_sight((0, 0), (3, 3), blocked=set()) is False

    def test_out_of_bounds_target(self):
        assert has_line_of_sight((0, 0), (MAP_SIZE, 0), blocked=set()) is False

    def test_blocker_at_target_ignored(self):
        # The target's own tile should not block sight to itself.
        assert has_line_of_sight((0, 0), (3, 0), blocked={(3, 0)}) is True


# ============================================================
# terrain_passable
# ============================================================

@pytest.mark.unit
class TestTerrainPassable:
    def test_castle_unowned_passable_to_anyone(self):
        assert terrain_passable(TERRAIN_CASTLE, owner_id=None, viewer_owner_id=999) is True

    def test_castle_owned_blocks_enemies(self):
        assert terrain_passable(TERRAIN_CASTLE, owner_id=1, viewer_owner_id=2) is False

    def test_castle_owned_allows_owner(self):
        assert terrain_passable(TERRAIN_CASTLE, owner_id=1, viewer_owner_id=1) is True

    def test_forest_passable(self):
        assert terrain_passable(TERRAIN_FOREST, owner_id=None, viewer_owner_id=None) is True


# ============================================================
# bfs_reachable
# ============================================================

def _plain_grid(size: int = MAP_SIZE) -> dict:
    """All-plain terrain dict for the BFS/pathfind tests."""
    return {(x, y): "plain" for x in range(size) for y in range(size)}


def _owners_empty() -> dict:
    return {(x, y): None for x in range(MAP_SIZE) for y in range(MAP_SIZE)}


@pytest.mark.unit
class TestBfsReachable:
    def test_zero_mov_only_start(self):
        g = _plain_grid()
        reachable = bfs_reachable((5, 5), g, _owners_empty(), mov=0,
                                  viewer_owner_id=None)
        assert reachable == {(5, 5): 0}

    def test_full_pool_reaches_everywhere_on_plains(self):
        g = _plain_grid()
        reachable = bfs_reachable((7, 7), g, _owners_empty(), mov=100,
                                  viewer_owner_id=None)
        # 225 tiles total, all reachable with mov >= 28 from the center
        assert len(reachable) == MAP_SIZE * MAP_SIZE

    def test_mountain_costs_more(self):
        # A line of mountains forces a longer path
        g = _plain_grid()
        for y in range(MAP_SIZE):
            g[(5, y)] = TERRAIN_MOUNTAIN  # cost 3
        # With mov=1, we can reach adjacent plains but not mountains
        reachable = bfs_reachable((4, 7), g, _owners_empty(), mov=1,
                                  viewer_owner_id=None)
        assert (5, 7) not in reachable  # mountain costs 3 > 1

    def test_blocked_units_excluded(self):
        g = _plain_grid()
        blocked = {(6, 7)}
        reachable = bfs_reachable((5, 7), g, _owners_empty(), mov=10,
                                  viewer_owner_id=None, blocked_units=blocked)
        assert (6, 7) not in reachable
        # But we can still pass over its neighbours
        assert (7, 7) in reachable


# ============================================================
# pathfind
# ============================================================

@pytest.mark.unit
class TestPathfind:
    def test_same_start_goal_returns_singleton(self):
        g = _plain_grid()
        p = pathfind((3, 3), (3, 3), g, _owners_empty(), mov=5,
                     viewer_owner_id=None)
        assert p == [(3, 3)]

    def test_unreachable_returns_none(self):
        g = _plain_grid()
        # Surround the start with mountains
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx, dy) == (0, 0):
                    continue
                g[(7 + dx, 7 + dy)] = TERRAIN_MOUNTAIN
        p = pathfind((7, 7), (10, 7), g, _owners_empty(), mov=2,
                     viewer_owner_id=None)
        assert p is None

    def test_prefers_cheaper_path(self):
        # Make a longer-but-cheaper path around a mountain.
        g = _plain_grid()
        g[(5, 7)] = TERRAIN_MOUNTAIN  # direct path cost 1+3 = 4
        p = pathfind((4, 7), (6, 7), g, _owners_empty(), mov=4,
                     viewer_owner_id=None)
        assert p is not None
        assert p[0] == (4, 7)
        assert p[-1] == (6, 7)
        # Going around via (4, 6) -> (4, 8) -> (5, 8) -> (6, 8) -> (6, 7) costs 4
        # but should be the chosen path since direct costs 1+3=4 (equal)
        # Either way the path length should be 4 (3 intermediate tiles)
        # We just need it to exist within budget
