"""
Terrain cluster generators (P1.4 / MAP_GENERATION_PLAN.md §3).

Forest and mountain clusters are placed with a Poisson-disk-style
sampler: pick a seed, then walk to a random neighbour until the cluster
reaches its target size.  Each cluster keeps at least ``safe_distance``
cells away from every castle safe-zone to avoid trapping spawn tiles.

Cluster target counts follow the spec:

    forests:  size // 10    cluster size 3–8
    mountains: size // 15   cluster size 2–6

``verify_connectivity`` runs an A*-flavoured BFS from one castle and
returns True iff every other castle is reachable through passable
cells (anything except mountains / castle_walls).
"""
from __future__ import annotations

import random
from collections import deque
from typing import List, Optional, Set, Tuple

from app.config import (
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
)
from app.models import Tile
from app.utils import manhattan as _manhattan

from .symmetry import is_in_safe_zone

Coord = Tuple[int, int]


# ---------------------------------------------------------------------
# Poisson-disk / flood-fill cluster helpers.
# ---------------------------------------------------------------------


def _in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def _neighbors4(x: int, y: int) -> List[Coord]:
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _pick_seed(
    rng: random.Random,
    size: int,
    castles: List[Coord],
    safe_radius: int,
) -> Optional[Coord]:
    """Pick a random in-bounds seed that isn't inside any safe zone.

    Up to 200 random attempts; fall back to a brute scan if all fail.
    Returns ``None`` only on truly pathological sizes.
    """
    for _ in range(200):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        if not is_in_safe_zone((x, y), castles, safe_radius):
            return (x, y)
    # Fallback: scan the grid and pick the first free cell.
    for y in range(size):
        for x in range(size):
            if not is_in_safe_zone((x, y), castles, safe_radius):
                return (x, y)
    return None


def _grow_cluster(
    rng: random.Random,
    grid: List[List[Tile]],
    seed: Coord,
    target_size: int,
    safe_zones: Set[Coord],
    size: int,
    terrain: str,
) -> int:
    """Grow a cluster from ``seed`` up to ``target_size`` cells.

    Returns the number of cells actually placed.  Stops early if no
    frontier candidates are available (the cluster is boxed in).
    """
    placed: Set[Coord] = {seed}
    grid[seed[1]][seed[0]] = Tile(x=seed[0], y=seed[1], terrain=terrain)
    frontier: List[Coord] = [n for n in _neighbors4(*seed) if _in_bounds(*n, size)]
    rng.shuffle(frontier)

    while len(placed) < target_size and frontier:
        idx = rng.randrange(len(frontier))
        x, y = frontier[idx]
        frontier[idx] = frontier[-1]
        frontier.pop()
        if (x, y) in placed:
            continue
        if (x, y) in safe_zones:
            continue
        # Avoid doubling up if the cell is already a member of the
        # same terrain family.
        cur = grid[y][x].terrain
        if cur == terrain:
            continue
        # Reject cells that would orphan the cluster (i.e. none of
        # their neighbours is already a cluster member) — this keeps
        # the shape compact instead of producing disconnected spurs.
        if not any(
            (nx, ny) in placed
            for nx, ny in _neighbors4(x, y)
            if _in_bounds(nx, ny, size)
        ):
            continue
        grid[y][x] = Tile(x=x, y=y, terrain=terrain)
        placed.add((x, y))
        for nx, ny in _neighbors4(x, y):
            if (
                _in_bounds(nx, ny, size)
                and (nx, ny) not in placed
                and (nx, ny) not in safe_zones
            ):
                frontier.append((nx, ny))

    return len(placed)


# ---------------------------------------------------------------------
# Public API: forest and mountain clusters.
# ---------------------------------------------------------------------


def cluster_target_count(size: int, kind: str) -> int:
    """Number of clusters to attempt for the given terrain kind."""
    if kind == TERRAIN_FOREST:
        return max(2, size // 10)
    if kind == TERRAIN_MOUNTAIN:
        return max(1, size // 15)
    raise ValueError(f"unknown cluster kind: {kind!r}")


def _generate_clusters(
    rng: random.Random,
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    safe_radius: int,
    safe_zones: Set[Coord],
    terrain: str,
    size_range: Tuple[int, int],
    count: int,
) -> None:
    for _ in range(count):
        target = rng.randint(size_range[0], size_range[1])
        seed = _pick_seed(rng, size, castles, safe_radius)
        if seed is None:
            return
        _grow_cluster(
            rng=rng,
            grid=grid,
            seed=seed,
            target_size=target,
            safe_zones=safe_zones,
            size=size,
            terrain=terrain,
        )


def generate_forest_clusters(
    rng: random.Random,
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    safe_radius: int = 2,
    size_range: Tuple[int, int] = (3, 8),
    count: Optional[int] = None,
) -> int:
    """Place forest clusters; returns the number of clusters placed."""
    if count is None:
        count = cluster_target_count(size, TERRAIN_FOREST)
    safe_zones: Set[Coord] = set()
    for cx, cy in castles:
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                x, y = cx + dx, cy + dy
                if _in_bounds(x, y, size):
                    safe_zones.add((x, y))
    placed = 0
    for _ in range(count):
        target = rng.randint(size_range[0], size_range[1])
        seed = _pick_seed(rng, size, castles, safe_radius)
        if seed is None:
            return placed
        if _grow_cluster(
            rng=rng,
            grid=grid,
            seed=seed,
            target_size=target,
            safe_zones=safe_zones,
            size=size,
            terrain=TERRAIN_FOREST,
        ) > 0:
            placed += 1
    return placed


def generate_mountain_clusters(
    rng: random.Random,
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    safe_radius: int = 2,
    size_range: Tuple[int, int] = (2, 6),
    count: Optional[int] = None,
) -> int:
    """Place mountain clusters; returns the number of clusters placed.

    Mountains must not block castles from each other — ``verify_connectivity``
    is the gatekeeper.  This function only places the geometry.
    """
    if count is None:
        count = cluster_target_count(size, TERRAIN_MOUNTAIN)
    safe_zones: Set[Coord] = set()
    for cx, cy in castles:
        for dx in range(-(safe_radius + 1), safe_radius + 2):
            for dy in range(-(safe_radius + 1), safe_radius + 2):
                x, y = cx + dx, cy + dy
                if _in_bounds(x, y, size):
                    safe_zones.add((x, y))
    placed = 0
    for _ in range(count):
        target = rng.randint(size_range[0], size_range[1])
        seed = _pick_seed(rng, size, castles, safe_radius + 1)
        if seed is None:
            return placed
        if _grow_cluster(
            rng=rng,
            grid=grid,
            seed=seed,
            target_size=target,
            safe_zones=safe_zones,
            size=size,
            terrain=TERRAIN_MOUNTAIN,
        ) > 0:
            placed += 1
    return placed


# ---------------------------------------------------------------------
# Connectivity verification.
# ---------------------------------------------------------------------


_IMPASSABLE_FOR_CONNECTIVITY = {
    TERRAIN_MOUNTAIN,
    # castle_wall is checked via the Tile.subtype at call sites; we
    # look it up dynamically because the constant lives in app.config
    # (avoiding a circular import here).
}


def _is_passable(tile: Tile) -> bool:
    """Loose passability check — anything except mountains and walls.

    Used by ``verify_connectivity`` to decide whether a BFS step is
    allowed.  Mirrors ``app.utils.terrain_passable`` minus the per-
    owner castle rule (castles must always be reachable from another
    castle, regardless of ownership at gen time).
    """
    if tile.terrain in _IMPASSABLE_FOR_CONNECTIVITY:
        return False
    sub = getattr(tile, "subtype", None)
    if sub == "castle_wall":
        return False
    return True


def verify_connectivity(
    grid: List[List[Tile]],
    castles: List[Coord],
) -> bool:
    """BFS from the first castle; True iff every other castle is reachable."""
    if not castles:
        return True
    size = len(grid)
    start = castles[0]
    if not (0 <= start[0] < size and 0 <= start[1] < size):
        return False
    seen: Set[Coord] = {start}
    queue: deque[Coord] = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in _neighbors4(x, y):
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            if (nx, ny) in seen:
                continue
            if not _is_passable(grid[ny][nx]):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return all(c in seen for c in castles)