"""
Grid helpers: distance, line-of-sight, BFS pathfinding (terrain-cost aware).

All functions are pure (no DB) so they're easy to unit-test.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.config import (
    MAP_SIZE,
    TERRAIN_CASTLE,
    TERRAIN_RIVER,
)
from app.movement import (
    DEFAULT_MOVEMENT_PROFILE,
    MovementProfile,
    can_end_on_terrain,
    can_traverse_terrain,
    terrain_cost_x2,
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
    """4-neighbour orthogonal moves (Manhattan adjacency — no diagonals).

    Units move one tile at a time using only the four cardinal directions
    (up / down / left / right). Diagonals are intentionally disallowed so
    that movement and attack ranges are measured in Manhattan distance
    (Fire-Emblem / Advance-Wars style).
    """
    return [(x + dx, y + dy) for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))]


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
    """Whether a unit may stand on this terrain.

    Rules:
      - castles are passable so a unit can enter an enemy HQ and seize it.
      - castle_wall, gate, and any terrain missing from TERRAIN_MOVE_COST
        are impassable for everyone.
      - everything else: passable.
    """
    del owner_id, viewer_owner_id  # ownership does not affect terrain movement.
    return can_end_on_terrain(DEFAULT_MOVEMENT_PROFILE, terrain)


def bfs_reachable(
    start: Coord,
    terrain: Dict[Coord, str],
    owners: Dict[Coord, Optional[int]],
    mov: int,
    *,
    viewer_owner_id: Optional[int],
    blocked_units: Optional[Set[Coord]] = None,
    movement_profile: Optional[MovementProfile] = None,
    size: int = MAP_SIZE,
) -> Dict[Coord, int]:
    """BFS with terrain cost; returns {coord: cost_so_far} for tiles reachable within `mov`.

    `mov` is the unit's MP pool (integer). Internally we work in
    "half-MP" units (TERRAIN_MOVE_COST values × 2) so road=1 (real cost
    0.5) can be represented without floats. The internal budget is
    `mov * 2`, and returned costs are also in "half-MP" units — callers
    that want to compare to MP should divide by 2.
    """
    blocked_units = blocked_units or set()
    movement_profile = movement_profile or DEFAULT_MOVEMENT_PROFILE
    if start not in terrain:
        return {}

    budget = mov * 2
    dist: Dict[Coord, int] = {start: 0}
    # Dijkstra is required because terrain costs are not uniform.
    import heapq
    queue: list[tuple[int, int, Coord]] = [(0, 0, start)]
    counter = 0
    reachable: Dict[Coord, int] = {start: 0}

    while queue:
        cur, _, (x, y) = heapq.heappop(queue)
        if cur != dist.get((x, y)):
            continue
        if cur >= budget:
            continue
        for nx, ny in neighbors(x, y):
            if not in_bounds(nx, ny, size):
                continue
            t = terrain.get((nx, ny))
            if t is None:
                continue
            if not can_traverse_terrain(movement_profile, t):
                continue
            if (nx, ny) in blocked_units:
                continue
            step_cost = terrain_cost_x2(movement_profile, t)
            if step_cost is None:
                continue
            new_cost = cur + step_cost
            if new_cost > budget:
                continue
            key = (nx, ny)
            if key not in dist or new_cost < dist[key]:
                dist[key] = new_cost
                counter += 1
                heapq.heappush(queue, (new_cost, counter, key))
                if can_end_on_terrain(movement_profile, t):
                    reachable[key] = new_cost

    return reachable


def pathfind(
    start: Coord,
    goal: Coord,
    terrain: Dict[Coord, str],
    owners: Dict[Coord, Optional[int]],
    mov: int,
    *,
    viewer_owner_id: Optional[int],
    blocked_units: Optional[Set[Coord]] = None,
    movement_profile: Optional[MovementProfile] = None,
    size: int = MAP_SIZE,
) -> Optional[List[Coord]]:
    """Cheapest path from start to goal within `mov` movement points.

    MP-to-cost conversion: internal cost budget is `mov * 2` (so road's
    cost=1 means "half a MP"). Returns the list of coords from start to
    goal, or None if unreachable.
    """
    if start == goal:
        return [start]
    blocked_units = (blocked_units or set()) - {start}  # allow standing on own tile
    movement_profile = movement_profile or DEFAULT_MOVEMENT_PROFILE
    budget = mov * 2

    # Dijkstra over integer costs.
    import heapq

    counter = 0
    pq: List[Tuple[int, int, Coord]] = [(0, counter, start)]
    came_from: Dict[Coord, Coord] = {}
    best: Dict[Coord, int] = {start: 0}

    while pq:
        cost, _, node = heapq.heappop(pq)
        if cost > best.get(node, float("inf")):
            continue
        # P2.5 — must check budget BEFORE accepting the goal, otherwise
        # `_ai_move` lets a unit teleport across the map (pathfind
        # returned a path even when the cost was > mov).
        if node == goal and cost <= budget and can_end_on_terrain(movement_profile, terrain[goal]):
            # Reconstruct path
            path = [node]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            path.reverse()
            return path
        if cost >= budget:
            continue  # no MP left to expand this node's neighbors
        for nx, ny in neighbors(*node):
            if not in_bounds(nx, ny, size):
                continue
            t = terrain.get((nx, ny))
            if t is None:
                continue
            if not can_traverse_terrain(movement_profile, t):
                continue
            if (nx, ny) in blocked_units:
                continue
            step_cost = terrain_cost_x2(movement_profile, t)
            if step_cost is None:
                continue
            new_cost = cost + step_cost
            if new_cost > budget:
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
