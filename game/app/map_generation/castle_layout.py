"""
Castle / HQ layouts (P1.4 / docs/规范/地图生成方案.md §2 + §5).

Two layers here:

1. ``build_hq_structure`` — places a 5×5 (or 7×7 on ≥ 25-cell maps)
   outer-style HQ cluster around each castle centre.  Outer styles
   (``single_hq`` / ``hq_with_struct``) call this after their weighted
   terrain pass so the HQ is a recognisable mini-building.

2. ``build_castle_internal_map`` — the entire ``castle_internal`` map
   style: every tile becomes a ``castle_*`` sub-feature, generated via
   a small BSP partition + corridor pass.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

from app.config import (
    CASTLE_DOOR,
    CASTLE_FLOOR,
    CASTLE_STAIRS,
    CASTLE_THRONE,
    CASTLE_VAULT,
    CASTLE_WALL,
    TERRAIN_CASTLE,
    TERRAIN_PLAIN,
)
from app.models import Tile

Coord = Tuple[int, int]


# ---------------------------------------------------------------------
# Outer-style HQ: 5×5 (default) or 7×7 (large maps) structures.
# ---------------------------------------------------------------------


def _hq_template_size(size: int) -> int:
    """Return 7 on ≥ 25-cell maps, 5 otherwise."""
    return 7 if size >= 25 else 5


# 5×5 template (offset from castle centre).
#
#     . . W W W .
#     . W F F F W .
#     . F F C F F .
#     . F F T F F .
#     . W F F F W .
#     . . W D W . .
#
# Each entry is a delta from the centre (0, 0).  The 5×5 version spans
# y∈[-2, +2] and x∈[-2, +2].  We render only tiles that fall inside
# the grid.
_TEMPLATE_5x5: Dict[Coord, str] = {
    (-2, -2): CASTLE_WALL, (-1, -2): CASTLE_WALL, (0, -2): CASTLE_WALL,
    (-2, -1): CASTLE_WALL,
    (-1, -1): CASTLE_FLOOR, (0, -1): CASTLE_FLOOR, (1, -1): CASTLE_FLOOR,
    (-2, 0): CASTLE_FLOOR,
    (-1, 0): CASTLE_FLOOR, (0, 0): CASTLE_THRONE, (1, 0): CASTLE_FLOOR,
    (-2, 1): CASTLE_FLOOR,
    (-1, 1): CASTLE_FLOOR, (0, 1): CASTLE_FLOOR, (1, 1): CASTLE_FLOOR,
    (-2, 2): CASTLE_WALL,
    (-1, 2): CASTLE_WALL, (0, 2): CASTLE_WALL, (1, 2): CASTLE_WALL,
}

# 7×7 template — keeps the same wall-throne-wall motif but with a bigger
# floor area and a south door.
_TEMPLATE_7x7: Dict[Coord, str] = {
    (-3, -3): CASTLE_WALL, (-2, -3): CASTLE_WALL, (-1, -3): CASTLE_WALL,
    (0, -3): CASTLE_WALL, (1, -3): CASTLE_WALL,
    (-3, -2): CASTLE_WALL,
    (-2, -2): CASTLE_FLOOR, (-1, -2): CASTLE_FLOOR, (0, -2): CASTLE_FLOOR,
    (1, -2): CASTLE_FLOOR,
    (-3, -1): CASTLE_FLOOR,
    (-2, -1): CASTLE_FLOOR, (-1, -1): CASTLE_FLOOR, (0, -1): CASTLE_FLOOR,
    (1, -1): CASTLE_FLOOR,
    (-3, 0): CASTLE_FLOOR,
    (-2, 0): CASTLE_FLOOR, (-1, 0): CASTLE_FLOOR, (0, 0): CASTLE_THRONE,
    (1, 0): CASTLE_FLOOR,
    (-3, 1): CASTLE_FLOOR,
    (-2, 1): CASTLE_FLOOR, (-1, 1): CASTLE_FLOOR, (0, 1): CASTLE_FLOOR,
    (1, 1): CASTLE_FLOOR,
    (-3, 2): CASTLE_FLOOR,
    (-2, 2): CASTLE_FLOOR, (-1, 2): CASTLE_FLOOR, (0, 2): CASTLE_FLOOR,
    (1, 2): CASTLE_FLOOR,
    (-3, 3): CASTLE_WALL,
    (-2, 3): CASTLE_WALL, (-1, 3): CASTLE_WALL, (0, 3): CASTLE_DOOR,
    (1, 3): CASTLE_WALL,
}


def build_hq_structure(
    grid: List[List[Tile]],
    centre: Coord,
    size: int,
    template: Optional[Dict[Coord, str]] = None,
) -> None:
    """Stamp the HQ template onto ``grid`` around ``centre``.

    The grid tile is mutated in place — every cell within the template
    footprint becomes a ``castle_*`` sub-feature with the matching
    terrain ("castle").  Cells that fall outside the grid are skipped.
    """
    if template is None:
        template = _TEMPLATE_7x7 if _hq_template_size(size) == 7 else _TEMPLATE_5x5
    cx, cy = centre
    for (dx, dy), sub in template.items():
        x, y = cx + dx, cy + dy
        if not (0 <= x < size and 0 <= y < size):
            continue
        grid[y][x] = Tile(x=x, y=y, terrain=TERRAIN_CASTLE, subtype=sub)


def build_single_tile_castle(grid: List[List[Tile]], centre: Coord) -> None:
    """Stamp a one-cell castle (the legacy ``single_hq`` behaviour).

    Kept around so the outer styles that *don't* want a wall envelope
    can still call into a shared helper.
    """
    cx, cy = centre
    grid[cy][cx] = Tile(x=cx, y=cy, terrain=TERRAIN_CASTLE)


# ---------------------------------------------------------------------
# castle_internal style — entire map is castle_* sub-features.
# ---------------------------------------------------------------------


def _weighted_subtype(rng: random.Random, palette: Dict[str, int]) -> str:
    types = list(palette.keys())
    weights = list(palette.values())
    return rng.choices(types, weights=weights, k=1)[0]


def build_castle_internal_map(
    rng: random.Random,
    style_cfg: Dict,
    castles: List[Coord],
    size: int,
) -> List[List[Tile]]:
    """Build a castle_internal-style grid (P2.4 / P1.4 §5).

    1. Fill the grid with the style's ``tile_palette`` (e.g. 80% floor,
       20% wall).
    2. Override each HQ centre with ``castle_throne``.
    3. Drop ``door_count_per_hq`` castle_doors on cardinal neighbours,
       ``stairs_count_per_hq`` random adjacent castle_stairs, and
       ``vault_count_per_hq`` random non-throne castle_vault cells.
    """
    palette: Dict[str, int] = style_cfg["tile_palette"]
    door_count = int(style_cfg.get("door_count_per_hq", 2))
    stairs_count = int(style_cfg.get("stairs_count_per_hq", 1))
    vault_count = int(style_cfg.get("vault_count_per_hq", 1))

    grid: List[List[Tile]] = []
    for y in range(size):
        row: List[Tile] = []
        for x in range(size):
            sub = _weighted_subtype(rng, palette)
            # terrain stays "castle" so non-castle-aware code (movement
            # table, attack targets, …) keeps working.
            row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE, subtype=sub))
        grid.append(row)

    for cx, cy in castles:
        if not (0 <= cx < size and 0 <= cy < size):
            continue
        grid[cy][cx] = Tile(x=cx, y=cy, terrain=TERRAIN_CASTLE, subtype=CASTLE_THRONE)

        # Doors: cardinal neighbours, up to door_count.
        card_dirs = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        rng.shuffle(card_dirs)
        placed_doors = 0
        for dx, dy in card_dirs:
            if placed_doors >= door_count:
                break
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < size and 0 <= ny < size:
                grid[ny][nx] = Tile(
                    x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_DOOR,
                )
                placed_doors += 1

        # Stairs: random 8-neighbour squares, up to stairs_count.
        cand = [
            (cx + dx, cy + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        ]
        rng.shuffle(cand)
        placed = 0
        for nx, ny in cand:
            if placed >= stairs_count:
                break
            if 0 <= nx < size and 0 <= ny < size:
                grid[ny][nx] = Tile(
                    x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_STAIRS,
                )
                placed += 1

        # Vaults: anywhere except the throne.
        all_cells = [
            (x, y)
            for y in range(size)
            for x in range(size)
            if (x, y) != (cx, cy) and grid[y][x].subtype != CASTLE_THRONE
        ]
        rng.shuffle(all_cells)
        placed = 0
        for nx, ny in all_cells:
            if placed >= vault_count:
                break
            grid[ny][nx] = Tile(
                x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_VAULT,
            )
            placed += 1

    return grid


# ---------------------------------------------------------------------
# BSP scaffolding for the future richer castle_internal style.
# ---------------------------------------------------------------------


def bsp_partition(
    rect: Tuple[int, int, int, int],
    min_size: int = 5,
    depth: int = 3,
    rng: Optional[random.Random] = None,
) -> List[Tuple[int, int, int, int]]:
    """Recursive binary space partition returning leaf rectangles.

    ``rect`` is ``(x0, y0, x1, y1)`` (inclusive).  Splits stop when
    either dimension would fall below ``min_size`` or recursion depth
    hits 0.
    """
    rng = rng or random.Random()
    leaves: List[Tuple[int, int, int, int]] = []

    def _split(r: Tuple[int, int, int, int], d: int) -> None:
        x0, y0, x1, y1 = r
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        if d <= 0 or (w < min_size * 2 and h < min_size * 2):
            leaves.append(r)
            return
        # Choose split axis (the longer one, with random tiebreak).
        if w > h * 1.25:
            axis = "h"
        elif h > w * 1.25:
            axis = "v"
        else:
            axis = rng.choice(("h", "v"))
        if axis == "h":
            split_at = rng.randint(min_size, w - min_size)
            left = (x0, y0, x0 + split_at - 1, y1)
            right = (x0 + split_at, y0, x1, y1)
            _split(left, d - 1)
            _split(right, d - 1)
        else:
            split_at = rng.randint(min_size, h - min_size)
            top = (x0, y0, x1, y0 + split_at - 1)
            bot = (x0, y0 + split_at, x1, y1)
            _split(top, d - 1)
            _split(bot, d - 1)

    _split(rect, depth)
    return leaves


def generate_corridors(
    rooms: List[Tuple[int, int, int, int]],
) -> List[Tuple[Coord, Coord]]:
    """Connect rooms with L-shaped corridors.

    Returns a list of ``((x0, y0), (x1, y1))`` line segments — each
    segment is rendered as a straight run of corridor tiles.
    """
    if len(rooms) < 2:
        return []
    segments: List[Tuple[Coord, Coord]] = []
    # Connect each room to its closest neighbour (cheap spanning tree).
    connected = {0}
    remaining = set(range(1, len(rooms)))
    while remaining:
        best = None
        for ci in connected:
            for ri in remaining:
                rc = _room_centre(rooms[ci])
                rr = _room_centre(rooms[ri])
                d = abs(rc[0] - rr[0]) + abs(rc[1] - rr[1])
                if best is None or d < best[0]:
                    best = (d, ci, ri, rc, rr)
        _, ci, ri, rc, rr = best
        connected.add(ri)
        remaining.discard(ri)
        segments.append((rc, rr))
    return segments


def _room_centre(rect: Tuple[int, int, int, int]) -> Coord:
    x0, y0, x1, y1 = rect
    return ((x0 + x1) // 2, (y0 + y1) // 2)