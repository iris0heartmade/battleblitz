"""
terrain_movement.py — connect per-unit terrain movement rules to the generator.

Why this exists
---------------
Real Fire Emblem / Advance Wars maps are not "uniform random terrain" — the
terrain around each faction's HQ is biased toward what that faction's unit
*can use*.  An archer wants a forest; a knight wants a road; a tank wants
plains.  If the generator just sprinkles random terrain, every faction ends
up with the same tactical situation and the map plays flat.

This module:
  1. Defines ``UNIT_TERRAIN_PREFERENCES`` — a per-unit-type score per terrain.
     (Inspired by FE class movement and AW2 unit cost tables.)
  2. Provides ``reshape_local_terrain`` — given a generated grid and a
     per-faction unit hint, swap tiles in the N×N area around the HQ so
     the local terrain matches the unit's preferences.
  3. Provides ``local_openness_score`` and ``local_reachability`` — cheap
     checks used by the generator to *measure* how well the current layout
     fits each faction.

The reshape is *gentle*: it only swaps cells within the HQ radius with
neighbouring cells, and never touches the HQ cell itself or the safe zone.
The generator calls it after the base terrain is laid and before the road
network so the local road still gets drawn toward a sensible neighbor.

All functions are pure (no I/O) so they're easy to unit-test and to
call from the generator's main pipeline.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from app.config import (
    TERRAIN_BARRACKS,
    TERRAIN_BRIDGE,
    TERRAIN_CASTLE,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_RIVER,
    TERRAIN_ROAD,
    TERRAIN_SNOW_PEAK,
    TERRAIN_VILLAGE,
)
from app.models import Tile

Coord = Tuple[int, int]


# ============================================================
# Unit → terrain preferences
# ============================================================
# Score semantics:
#   +1.0  = unit thrives on this terrain (e.g. archer in forest)
#    0.0  = neutral (no bonus/penalty)
#   -1.0  = unit cannot effectively use this terrain (e.g. tank in forest)
#
# Numbers are deliberately on a -1..+1 scale so we can sum across a
# 5x5 area and get a meaningful "local fitness" score in [-25, +25].
# This is also what we feed to the quality score function for "is
# this map fun to play as unit X?".
#
# FE / AW units are mixed in the same table because the generator
# doesn't care which game; it just knows "this unit wants X".  The
# caller picks a unit type per faction.
# ============================================================
UNIT_TERRAIN_PREFERENCES: Dict[str, Dict[str, float]] = {
    # --- Fire Emblem-style classes (FE8/3H) ---
    "swordsman": {  # 剑士 — 步兵,通用
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 0.8, TERRAIN_VILLAGE: 0.5,
        TERRAIN_BARRACKS: 0.4, TERRAIN_BRIDGE: 0.6,
        TERRAIN_FOREST: 0.3,
        TERRAIN_MOUNTAIN: -0.5, TERRAIN_SNOW_PEAK: -0.5,
        TERRAIN_RIVER: -1.0,
    },
    "knight": {  # 重甲 — 走慢但防御高
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 1.0, TERRAIN_BRIDGE: 0.8,
        TERRAIN_CASTLE: 0.5,
        TERRAIN_FOREST: -1.0, TERRAIN_MOUNTAIN: -1.0,
        TERRAIN_SNOW_PEAK: -1.0, TERRAIN_RIVER: -1.0,
    },
    "archer": {  # 弓手 — 远程,爱森林
        TERRAIN_FOREST: 1.0, TERRAIN_MOUNTAIN: 0.9, TERRAIN_SNOW_PEAK: 0.8,
        TERRAIN_PLAIN: 0.4, TERRAIN_BRIDGE: 0.5,
        TERRAIN_ROAD: 0.2,
    },
    "warlock": {  # 法师 — 攻击无视地形,爱平地
        TERRAIN_PLAIN: 0.7, TERRAIN_ROAD: 0.5, TERRAIN_FOREST: 0.4,
        TERRAIN_VILLAGE: 0.3,
    },
    "healer": {  # 治疗 — 走慢但能远程支援
        TERRAIN_PLAIN: 1.0, TERRAIN_VILLAGE: 0.7, TERRAIN_BARRACKS: 0.6,
        TERRAIN_ROAD: 0.6, TERRAIN_BRIDGE: 0.5,
        TERRAIN_FOREST: 0.2,
    },
    "paladin": {  # 圣骑士 — 骑兵,爱开阔地
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 1.0, TERRAIN_BRIDGE: 0.8,
        TERRAIN_VILLAGE: 0.3,
        TERRAIN_FOREST: -0.5, TERRAIN_MOUNTAIN: -1.0,
        TERRAIN_SNOW_PEAK: -1.0, TERRAIN_RIVER: -1.0,
    },
    # --- Advance Wars-style units ---
    "infantry": {  # 步兵 (AW2)
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 0.8, TERRAIN_BRIDGE: 0.7,
        TERRAIN_FOREST: 0.4, TERRAIN_VILLAGE: 0.3, TERRAIN_BARRACKS: 0.3,
        TERRAIN_MOUNTAIN: -0.5, TERRAIN_RIVER: -1.0,
    },
    "tank": {  # 坦克 — 重甲
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 1.0, TERRAIN_BRIDGE: 0.8,
        TERRAIN_VILLAGE: 0.4, TERRAIN_BARRACKS: 0.3,
        TERRAIN_FOREST: -1.0, TERRAIN_MOUNTAIN: -1.0,
        TERRAIN_RIVER: -1.0, TERRAIN_SNOW_PEAK: -0.5,
    },
    "recon": {  # 侦察车 — 轻、快
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 1.0, TERRAIN_FOREST: 0.8,
        TERRAIN_BRIDGE: 0.8, TERRAIN_VILLAGE: 0.4,
        TERRAIN_MOUNTAIN: -0.3,
    },
    "artillery": {  # 炮兵 — 远程
        TERRAIN_PLAIN: 1.0, TERRAIN_ROAD: 0.7, TERRAIN_BRIDGE: 0.5,
        TERRAIN_FOREST: -0.7, TERRAIN_MOUNTAIN: -0.3,
    },
    # --- Fallback "balanced" profile for callers that don't pick one ---
    "_balanced": {
        TERRAIN_PLAIN: 0.5, TERRAIN_ROAD: 0.5, TERRAIN_BRIDGE: 0.5,
        TERRAIN_VILLAGE: 0.3, TERRAIN_BARRACKS: 0.3,
        TERRAIN_FOREST: 0.0, TERRAIN_MOUNTAIN: -0.3,
        TERRAIN_SNOW_PEAK: -0.3, TERRAIN_RIVER: -0.7,
    },
}


def _profile_for(unit_type: str) -> Dict[str, float]:
    """Return the preference dict for a unit type, falling back to
    ``_balanced`` if the unit is unknown so unknown units still get
    *some* shaping (instead of all-zero).
    """
    return UNIT_TERRAIN_PREFERENCES.get(unit_type, UNIT_TERRAIN_PREFERENCES["_balanced"])


def local_preference_score(unit_type: str, terrain: str) -> float:
    """Return the per-cell preference score (-1..+1) for ``unit_type``
    standing on ``terrain``.  Returns 0 for unknown terrain.
    """
    return _profile_for(unit_type).get(terrain, 0.0)


# ============================================================
# Local terrain scoring & reshaping
# ============================================================


def local_openness_score(
    grid: List[List[Tile]],
    hq: Coord,
    unit_type: str,
    radius: int = 2,
) -> float:
    """Sum the preference scores for the (2r+1)² cells around ``hq``.

    Higher = better for the unit.  0 = neutral layout.  Negative =
    the unit is in a really hostile position (lots of forest for a
    tank, etc.).
    """
    size = len(grid)
    profile = _profile_for(unit_type)
    score = 0.0
    cells = 0
    x, y = hq
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            t = grid[ny][nx].terrain
            score += profile.get(t, 0.0)
            cells += 1
    if cells == 0:
        return 0.0
    return score / cells  # normalized to [-1, +1]


def _in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def reshape_local_terrain(
    grid: List[List[Tile]],
    hq: Coord,
    unit_type: str,
    *,
    radius: int = 2,
    safe_zones: Optional[Set[Coord]] = None,
    max_swaps: int = 4,
) -> int:
    """Light-weight pass that biases the cells around ``hq`` toward the
    unit's preferred terrain.  Returns the number of swaps performed.

    Algorithm
    ---------
    For each of the (2r+1)² cells within ``radius`` of the HQ:
      * score = unit's preference for the cell's current terrain
    Sort by score ascending.  For the worst-scoring cells, find a
    "good" swap candidate just outside the radius (1 step past it)
    that has a much higher score, and swap their terrains.  Never
    touches:
      * the HQ cell itself
      * any safe-zone cell (so we don't disturb the spawn)
      * any cell that's already castle / road (we'd corrupt road graph)
    Stops after ``max_swaps`` swaps to keep the global terrain
    distribution stable.
    """
    if safe_zones is None:
        safe_zones = set()
    size = len(grid)
    profile = _profile_for(unit_type)
    x, y = hq

    # Collect cells in radius with their scores
    in_radius: List[Tuple[float, Coord]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue  # never touch the HQ
            nx, ny = x + dx, y + dy
            if not _in_bounds(nx, ny, size):
                continue
            if (nx, ny) in safe_zones:
                continue
            t = grid[ny][nx].terrain
            # Don't move a road / bridge / castle — they're load-bearing
            if t in (TERRAIN_ROAD, TERRAIN_BRIDGE, TERRAIN_CASTLE):
                continue
            score = profile.get(t, 0.0)
            in_radius.append((score, (nx, ny)))
    in_radius.sort(key=lambda t: t[0])  # worst first

    # Build the "good neighbor" pool: cells just outside the radius
    # (distance exactly radius+1 from HQ).  These are what we swap in.
    out_radius: List[Tuple[float, Coord]] = []
    boundary = radius + 1
    for dy in range(-boundary, boundary + 1):
        for dx in range(-boundary, boundary + 1):
            if abs(dx) < boundary and abs(dy) < boundary:
                continue  # not on the boundary ring
            nx, ny = x + dx, y + dy
            if not _in_bounds(nx, ny, size):
                continue
            if (nx, ny) in safe_zones:
                continue
            t = grid[ny][nx].terrain
            if t in (TERRAIN_ROAD, TERRAIN_BRIDGE, TERRAIN_CASTLE):
                continue
            score = profile.get(t, 0.0)
            out_radius.append((score, (nx, ny)))
    out_radius.sort(key=lambda t: -t[0])  # best first

    # Greedy swap: take worst in-radius cell, find best out-radius cell
    # whose terrain would improve the in-radius score.
    swaps_done = 0
    i, j = 0, 0
    while swaps_done < max_swaps and i < len(in_radius) and j < len(out_radius):
        bad_score, bad_pos = in_radius[i]
        good_score, good_pos = out_radius[j]
        # If the "good" cell isn't actually good for this unit, give up
        if good_score <= 0:
            break
        # Don't swap if the bad cell is already at the good cell's level
        if bad_score >= good_score - 0.1:
            i += 1
            continue
        # Do the swap
        bx, by = bad_pos
        gx, gy = good_pos
        grid[by][bx], grid[gy][gx] = grid[gy][gx], grid[by][bx]
        swaps_done += 1
        i += 1
        j += 1
    return swaps_done


def best_unit_hint_for(
    grid: List[List[Tile]], hq: Coord, options: List[str],
    radius: int = 2,
) -> str:
    """Pick the unit_type from ``options`` whose current local terrain
    already fits them best.  Used by the generator when the caller
    didn't pass a hint.
    """
    return max(
        options,
        key=lambda u: local_openness_score(grid, hq, u, radius),
    )


__all__ = [
    "UNIT_TERRAIN_PREFERENCES",
    "best_unit_hint_for",
    "local_openness_score",
    "local_preference_score",
    "reshape_local_terrain",
]
