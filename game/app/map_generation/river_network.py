"""
River network generator (P1.4 / MAP_GENERATION_PLAN.md §4).

Algorithm (two-phase):

  1. ``main_trunks`` — pick ``seed_count`` starting points on the map
     edge and random-walk them toward the centre, occasionally
     branching.

  2. ``repair_isolated`` — find 1-2 cell river fragments with no
     passable neighbour and either bridge them to the nearest trunk
     (within a 3-cell window) or delete them.

Constraints:

  * Rivers never overwrite castles or their 2-tile safe zone.
  * Rivers never overwrite roads.
  * Width is always 1 cell (the spec calls for lakes only as a future
    extension — see random-map-generation-spec.md §13.C).
"""
from __future__ import annotations

import random
from collections import deque
from typing import List, Optional, Set, Tuple

from app.config import TERRAIN_RIVER
from app.models import Tile
from app.utils import manhattan as _manhattan

from .symmetry import is_in_safe_zone

Coord = Tuple[int, int]


def _in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def _neighbors4(x: int, y: int) -> List[Coord]:
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _pick_edge_seed(rng: random.Random, size: int) -> Coord:
    """Pick a random coord on one of the four map edges."""
    side = rng.choice(("top", "bottom", "left", "right"))
    if side == "top":
        return (rng.randint(0, size - 1), 0)
    if side == "bottom":
        return (rng.randint(0, size - 1), size - 1)
    if side == "left":
        return (0, rng.randint(0, size - 1))
    return (size - 1, rng.randint(0, size - 1))


def _river_step(
    rng: random.Random,
    pos: Coord,
    target: Coord,
    size: int,
    branch_probability: float,
) -> Tuple[Coord, bool]:
    """Single random-walk step toward ``target``.

    Returns ``(next_pos, branched)``.  The walker prefers the direction
    that reduces Manhattan distance to ``target`` but has a 30% chance
    of going perpendicular for natural curves.  ``branched`` is True
    when the walker forked (caller can spawn an extra walker).
    """
    x, y = pos
    tx, ty = target
    candidates: List[Coord] = []
    # Cardinal neighbours that stay in bounds.
    for nx, ny in _neighbors4(x, y):
        if _in_bounds(nx, ny, size):
            candidates.append((nx, ny))
    if not candidates:
        return pos, False
    # Score each candidate by (a) -manhattan to target, (b) prefer
    # straight-line continuity.
    best = min(candidates, key=lambda c: _manhattan(c, target))
    branched = False
    if rng.random() < branch_probability:
        # 30% chance: take a perpendicular step to introduce a curve.
        perpendicular: List[Coord] = []
        for nx, ny in _neighbors4(x, y):
            if nx == tx and ny == ty:
                continue  # going toward target; not perpendicular
            if (nx - x) != 0 and (ty - y) != 0 and (nx - x) == (tx - x):
                continue
            if (ny - y) != 0 and (tx - x) != 0 and (ny - y) == (ty - y):
                continue
            perpendicular.append((nx, ny))
        if perpendicular:
            branched = True
            best = rng.choice(perpendicular)
    return best, branched


def generate_river_network(
    rng: random.Random,
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    safe_radius: int = 2,
    seed_count: int = 2,
    branch_probability: float = 0.3,
    max_steps: int = 200,
) -> int:
    """Carve rivers into ``grid``.  Returns the number of river tiles placed.

    The grid is mutated in place.  Castle tiles, safe-zone cells, and
    road tiles are protected (rivers won't overwrite them).
    """
    if size < 5:
        return 0  # too small for meaningful rivers

    safe_zones: Set[Coord] = set()
    for cx, cy in castles:
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                x, y = cx + dx, cy + dy
                if _in_bounds(x, y, size):
                    safe_zones.add((x, y))

    def _is_protected(coord: Coord) -> bool:
        x, y = coord
        if not (0 <= x < size and 0 <= y < size):
            return True
        if (x, y) in safe_zones:
            return True
        t = grid[y][x].terrain
        # Don't run rivers over roads or existing rivers (so we don't
        # double-write), and don't write rivers on impassable tiles.
        if t == "road":
            return True
        if t == TERRAIN_RIVER:
            return True
        if t == "mountain":
            return True  # mountains are walls; we can't flow through them
        return False

    # Phase 1 — main trunks.
    rivers: Set[Coord] = set()
    walkers: List[Coord] = []
    for _ in range(seed_count):
        seed = _pick_edge_seed(rng, size)
        # Make sure seed isn't on a safe zone.
        attempts = 0
        while seed in safe_zones and attempts < 10:
            seed = _pick_edge_seed(rng, size)
            attempts += 1
        if seed in safe_zones:
            continue
        walkers.append(seed)
        rivers.add(seed)
        grid[seed[1]][seed[0]] = Tile(x=seed[0], y=seed[1], terrain=TERRAIN_RIVER)

    centre = (size // 2, size // 2)
    new_walker_cap = 8
    # Snapshot the initial walkers so the inner for-loop's iteration
    # bound stays stable; otherwise re-populating ``walkers`` from
    # inside the for-loop causes an unbounded loop.
    initial_walkers: List[Coord] = list(walkers)
    total_steps = 0
    for start_pos in initial_walkers:
        pos = start_pos
        for step in range(max_steps):
            if total_steps >= max_steps * seed_count:
                break
            nxt, branched = _river_step(rng, pos, centre, size, branch_probability)
            if nxt == pos:
                break  # boxed in
            pos = nxt
            total_steps += 1
            # Reached an edge opposite the original side?  Park here.
            edge_exit = (
                pos[0] == 0
                or pos[0] == size - 1
                or pos[1] == 0
                or pos[1] == size - 1
            )
            if not _is_protected(pos):
                rivers.add(pos)
                grid[pos[1]][pos[0]] = Tile(
                    x=pos[0], y=pos[1], terrain=TERRAIN_RIVER,
                )
            if edge_exit and step > 5:
                break
            if branched and len(walkers) < new_walker_cap and pos not in walkers:
                walkers.append(pos)
            if total_steps >= max_steps * seed_count:
                break

    # Phase 2 — repair isolated 1-2 cell fragments.
    _repair_isolated(grid, rivers, size, castles, safe_zones)

    return len(rivers)


def _repair_isolated(
    grid: List[List[Tile]],
    rivers: Set[Coord],
    size: int,
    castles: List[Coord],
    safe_zones: Set[Coord],
) -> None:
    """Bridge or delete 1-2 cell river fragments with no river neighbour.

    "No river neighbour" means the cell is isolated (≤ 1 river cell in
    its 4-neighbourhood).  We bridge by drawing a short straight line
    toward the nearest trunk; if no trunk is within 3 cells, we delete
    the fragment.
    """
    # Identify candidates: river cells with ≤ 1 river neighbour.
    candidates: List[Coord] = []
    for r in list(rivers):
        nb = sum(1 for n in _neighbors4(*r) if n in rivers)
        if nb <= 1:
            candidates.append(r)

    for cell in candidates:
        # Try to bridge to the nearest river within a 3-cell window.
        target: Optional[Coord] = None
        target_dist = 99
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = cell[0] + dx, cell[1] + dy
                if not _in_bounds(nx, ny, size):
                    continue
                if (nx, ny) == cell:
                    continue
                if (nx, ny) in rivers and (nx, ny) != cell:
                    d = _manhattan(cell, (nx, ny))
                    if 1 < d <= 3 and d < target_dist:
                        target = (nx, ny)
                        target_dist = d

        if target is None:
            # Lonely fragment — delete it back to plain.
            grid[cell[1]][cell[0]] = Tile(
                x=cell[0], y=cell[1], terrain="plain",
            )
            rivers.discard(cell)
            continue

        # Draw a Manhattan line between cell and target.
        x, y = cell
        tx, ty = target
        while (x, y) != (tx, ty):
            if x < tx:
                x += 1
            elif x > tx:
                x -= 1
            elif y < ty:
                y += 1
            elif y > ty:
                y -= 1
            if (x, y) in safe_zones:
                break
            if not _in_bounds(x, y, size):
                break
            if (x, y) in rivers:
                continue
            rivers.add((x, y))
            grid[y][x] = Tile(x=x, y=y, terrain=TERRAIN_RIVER)


def find_river_segments(rivers: Set[Coord]) -> List[List[Coord]]:
    """Group river cells into connected components (4-connected)."""
    seen: Set[Coord] = set()
    segs: List[List[Coord]] = []
    for r in rivers:
        if r in seen:
            continue
        comp: List[Coord] = []
        q: deque[Coord] = deque([r])
        seen.add(r)
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nb in _neighbors4(*cur):
                if nb in rivers and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        segs.append(comp)
    return segs