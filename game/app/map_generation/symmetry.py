"""
Symmetry helpers — castle positions and safe zones (P1.4 / MAP_GENERATION_PLAN.md §2).

The number of castles equals the number of players (宁缺勿滥 / "宁缺勿滥"):

    2 → diagonal        (inset, inset)            (far_inset, far_inset)
    3 → 120° triangle   (inset, inset)            (far_inset, inset)
                                                  (mid_x,     far_inset)
    4 → four corners    (inset, inset)            (far_inset, inset)
                       (inset, far_inset)         (far_inset, far_inset)

`inset` defaults to ``max(2, size // 8)`` so the safe-zone radius of 2
keeps castles at least 4 cells from any edge on a 15×15 map and scales
up proportionally for larger maps.
"""
from __future__ import annotations

from typing import List, Set, Tuple

Coord = Tuple[int, int]


def calculate_castle_positions(
    size: int,
    player_count: int,
    inset: int = None,
) -> List[Coord]:
    """Return symmetric castle centres for the requested player count.

    Coordinates are returned in seat order (seat 0, 1, …).  ``player_count``
    is clamped to [2, 4]; values outside the range fall back to the 4-player
    layout (matches legacy behaviour from ``game_logic._CASTLE_LAYOUTS``).
    """
    if inset is None:
        inset = max(2, size // 8)
    far_inset = size - 1 - inset
    mid_x = size // 2

    n = max(2, min(4, player_count))
    layouts = {
        2: [(inset, inset), (far_inset, far_inset)],
        3: [(inset, inset), (far_inset, inset), (mid_x, far_inset)],
        4: [
            (inset, inset),
            (far_inset, inset),
            (inset, far_inset),
            (far_inset, far_inset),
        ],
    }
    return list(layouts[n])


def calculate_safe_zones(
    castles: List[Coord],
    size: int,
    radius: int = 2,
) -> Set[Coord]:
    """Return the set of coords inside any castle's safe zone (Chebyshev)."""
    zones: Set[Coord] = set()
    for cx, cy in castles:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    zones.add((x, y))
    return zones


def is_in_safe_zone(coord: Coord, castles: List[Coord], radius: int = 2) -> bool:
    """Cheap predicate: is ``coord`` within ``radius`` of any castle?"""
    cx, cy = coord
    for qx, qy in castles:
        if max(abs(cx - qx), abs(cy - qy)) <= radius:
            return True
    return False


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])