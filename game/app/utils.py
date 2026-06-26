"""
Grid helpers: distance, line-of-sight, BFS pathfinding (terrain-cost aware).

All functions are pure (no DB) so they're easy to unit-test.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.config import (
    MAP_SIZE,
    TERRAIN_CASTLE,
    TERRAIN_MOVE_COST,
    TERRAIN_RIVER,
)


logger = logging.getLogger(__name__)


Coord = Tuple[int, int]


def in_bounds(x: int, y: int, size: int = MAP_SIZE) -> bool:
    return 0 <= x < size and 0 <= y < size


def chebyshev(a: Coord, b: Coord) -> int:
    """King-move distance (diagonal counts as 1)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors(x: int, y: int) -> List[Coord]:
    """8-neighbour king moves (allows diagonals)."""
    return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]


def has_line_of_sight(
    a: Coord,
    b: Coord,
    blocked: Set[Coord],
    size: int = MAP_SIZE,
) -> bool:
    """Straight (axis-aligned) line of sight, used for ranged attacks.

    Mountains, rivers, and forests are listed in `blocked`. Castles are NOT
    blockers (a unit on a castle should still be targetable). Same-tile is OK.
    """
    if a == b:
        return True
    ax, ay = a
    bx, by = b
    if ax != bx and ay != by:
        # No LOS through diagonals (simplification: no diagonal shots).
        return False
    step_x = 0 if ax == bx else (1 if bx > ax else -1)
    step_y = 0 if ay == by else (1 if by > ay else -1)
    cx, cy = ax + step_x, ay + step_y
    while (cx, cy) != (bx, by):
        if not in_bounds(cx, cy, size):
            return False
        if (cx, cy) in blocked:
            return False
        cx += step_x
        cy += step_y
    return in_bounds(bx, by, size)


def terrain_passable(
    terrain: str,
    *,
    owner_id: Optional[int],
    viewer_owner_id: Optional[int],
) -> bool:
    """A castle is only passable for its owner (or unowned at game start)."""
    if terrain == TERRAIN_CASTLE:
        return owner_id is None or owner_id == viewer_owner_id
    # River and mountain still passable, just expensive (cost handled in BFS).
    return terrain in TERRAIN_MOVE_COST


def bfs_reachable(
    start: Coord,
    terrain: Dict[Coord, str],
    owners: Dict[Coord, Optional[int]],
    mov: int,
    *,
    viewer_owner_id: Optional[int],
    blocked_units: Optional[Set[Coord]] = None,
    size: int = MAP_SIZE,
) -> Dict[Coord, int]:
    """BFS with terrain cost; returns {coord: cost_so_far} for tiles reachable within `mov`.

    Cost is integer movement points (matches `TERRAIN_MOVE_COST`).
    `blocked_units` excludes the moving unit's own tile.
    """
    blocked_units = blocked_units or set()
    if start not in terrain:
        return {}

    dist: Dict[Coord, int] = {start: 0}
    queue: deque[Coord] = deque([start])

    while queue:
        x, y = queue.popleft()
        cur = dist[(x, y)]
        if cur >= mov:
            continue
        for nx, ny in neighbors(x, y):
            if not in_bounds(nx, ny, size):
                continue
            t = terrain.get((nx, ny))
            if t is None:
                continue
            owner = owners.get((nx, ny))
            if not terrain_passable(t, owner_id=owner, viewer_owner_id=viewer_owner_id):
                continue
            if (nx, ny) in blocked_units:
                continue
            new_cost = cur + TERRAIN_MOVE_COST[t]
            if new_cost > mov:
                continue
            key = (nx, ny)
            if key not in dist or new_cost < dist[key]:
                dist[key] = new_cost
                queue.append(key)

    return dist


def pathfind(
    start: Coord,
    goal: Coord,
    terrain: Dict[Coord, str],
    owners: Dict[Coord, Optional[int]],
    mov: int,
    *,
    viewer_owner_id: Optional[int],
    blocked_units: Optional[Set[Coord]] = None,
    size: int = MAP_SIZE,
) -> Optional[List[Coord]]:
    """Cheapest path from start to goal within `mov` movement points.

    Returns a list of coords from start (inclusive) to goal (inclusive), or
    None if unreachable.
    """
    if start == goal:
        return [start]
    blocked_units = (blocked_units or set()) - {start}  # allow standing on own tile

    # Dijkstra over integer costs (max cost is 3, so BFS by cost bucket works too).
    import heapq

    counter = 0
    pq: List[Tuple[int, int, Coord]] = [(0, counter, start)]
    came_from: Dict[Coord, Coord] = {}
    best: Dict[Coord, int] = {start: 0}

    while pq:
        cost, _, node = heapq.heappop(pq)
        if node == goal:
            # Reconstruct path
            path = [node]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            path.reverse()
            return path
        if cost > best.get(node, float("inf")):
            continue
        if cost >= mov:
            continue
        for nx, ny in neighbors(*node):
            if not in_bounds(nx, ny, size):
                continue
            t = terrain.get((nx, ny))
            if t is None:
                continue
            owner = owners.get((nx, ny))
            if not terrain_passable(t, owner_id=owner, viewer_owner_id=viewer_owner_id):
                continue
            if (nx, ny) in blocked_units:
                continue
            step_cost = TERRAIN_MOVE_COST[t]
            new_cost = cost + step_cost
            if new_cost > mov:
                continue
            key = (nx, ny)
            if new_cost < best.get(key, float("inf")):
                best[key] = new_cost
                came_from[key] = node
                counter += 1
                heapq.heappush(pq, (new_cost, counter, key))
    return None


def coords_iter(size: int = MAP_SIZE) -> Iterable[Coord]:
    for y in range(size):
        for x in range(size):
            yield (x, y)


__all__ = [
    "Coord",
    "in_bounds",
    "chebyshev",
    "manhattan",
    "neighbors",
    "has_line_of_sight",
    "terrain_passable",
    "bfs_reachable",
    "pathfind",
    "coords_iter",
]