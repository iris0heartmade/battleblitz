"""
Symmetry helpers — castle positions and safe zones (P1.4 / docs/规范/地图生成方案.md §2 + P2.7).

The number of castles equals the number of players (宁缺勿滥 / "宁缺勿滥"):

    2 → diagonal        (inset, inset)            (far_inset, far_inset)
    3 → 120° triangle   (inset, inset)            (far_inset, inset)
                                                  (mid_x,     far_inset)
    4 → four corners    (inset, inset)            (far_inset, inset)
                       (inset, far_inset)         (far_inset, far_inset)

`inset` defaults to ``max(2, size // 8)`` so the safe-zone radius of 2
keeps castles at least 4 cells from any edge on a 15×15 map and scales
up proportionally for larger maps.

P2.7+ — also provides ``hq_placement_for_biome`` for "real-place" HQ
scoring on procedurally generated maps.  The hand-authored
``balanced_*_Np`` maps keep using the symmetric corner / triangle
layouts above because competitive players expect them.
"""
from __future__ import annotations

import random
from typing import Dict, List, Set, Tuple

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


# ---------------------------------------------------------------------
# P2.7+ — geographic HQ placement.
#
# ``calculate_castle_positions`` (above) gives the symmetric corner /
# triangle layouts that the hand-authored balanced_*_Np maps and the
# older competitive maps use.  But for procedurally generated
# "realistic" maps, those fixed corners feel arbitrary — a castle
# shouldn't sit in the middle of dense forest or in a road's path.
#
# ``hq_placement_for_biome`` scores every cell on the grid by how
# good a "real place for a castle" it would be, then picks the top-N
# ensuring pairwise distance >= ``min_pair_distance`` so two castles
# never spawn 2 cells apart.  The scoring is deterministic for a
# given (size, player_count, grid, seed).
# ---------------------------------------------------------------------


# Per-biome weights tell the scorer what each terrain *means* in that
# biome.  Snow prefers castle near a snow_peak ridge (a "frozen keep");
# desert prefers plain (an "oasis clearing"); grass and compact are
# more flexible.
_BIOME_HQ_AFFINITY: dict[str, dict[str, float]] = {
    # terrain_name -> score delta.  Positive = good for HQ, negative = bad.
    "grass": {
        "plain":    0.0,
        "forest":  -1.5,   # dense forest = bad visibility
        "mountain": +0.5,   # a rocky outcrop is a defensible keep
        "snow_peak": -3.0,  # shouldn't appear in grass anyway
        "river":   +0.4,   # water access is good
        "village":  +0.2,
        "barracks": +0.2,
        "road":    +0.3,
    },
    "snow": {
        "plain":    0.0,
        "forest":  -1.0,   # sparse boreal forest is OK
        "snow_peak": +1.0, # ridge gives defensible high ground
        "river":   +0.3,
        "village":  +0.1,
        "barracks": +0.1,
    },
    "desert": {
        "plain":    0.0,
        "mountain": +0.6,   # rocky plateau
        "river":   +0.8,   # oasis — the classic desert castle
        "village":  +0.2,
        "barracks": +0.2,
    },
    "compact": {
        "plain":    0.0,
        "forest":   0.0,   # any terrain is fine in compact
        "mountain":  0.0,
        "river":    0.0,
        "village":  0.0,
        "barracks": 0.0,
    },
}


def hq_placement_for_biome(
    size: int,
    player_count: int,
    grid: List[List[str]],
    rng: random.Random,
    biome: str = "grass",
    min_pair_distance: int = 8,
) -> List[Coord]:
    """Pick N castle positions scored against a real-place heuristic.

    Args:
        size: grid size (assumes square).
        player_count: number of castles to place (clamped to 2-4).
        grid: the post-fill terrain grid; each cell is a string name
            (e.g. ``"plain"``, ``"forest"``).  We read it to score
            candidates; we don't mutate it.
        rng: a Random instance — used only to break ties.
        biome: name of the biome (``"grass"``, ``"snow"``,
            ``"desert"``, ``"compact"``).
        min_pair_distance: minimum allowed Chebyshev distance
            between any two chosen HQs.  Defaults to 8 (so a 15×15
            map has at most 4 well-separated castles).

    Returns a list of ``(x, y)`` tuples in seat order (seat 0, 1, …).
    The caller is responsible for assigning seats in the order
    returned; the engine in ``routes.game._start_battle_internal``
    picks seat 0 from the row-major scan of the layout, which is
    the same convention we use here (top-left = seat 0).
    """
    import random as _random
    if not isinstance(rng, _random.Random):
        # Defensive: accept any RNG-like object with .random()
        pass

    n = max(2, min(4, player_count))
    affinity = _BIOME_HQ_AFFINITY.get(biome, _BIOME_HQ_AFFINITY["grass"])

    # Score every cell.
    scored: List[Tuple[float, int, Coord]] = []
    for y in range(size):
        for x in range(size):
            score = _cell_score(x, y, size, grid, affinity, biome)
            scored.append((score, rng.randrange(2**31), (x, y)))
    # Sort by score desc, then by tie-breaker for determinism.
    scored.sort(key=lambda t: (-t[0], t[1]))

    # Greedy select top-N with pairwise min distance.
    chosen: List[Coord] = []
    for score, _, pos in scored:
        if len(chosen) >= n:
            break
        if all(_chebyshev(pos, c) >= min_pair_distance for c in chosen):
            chosen.append(pos)

    # Edge case: couldn't find N well-separated cells (e.g. tiny map
    # + max players).  Fall back to the remaining top cells in
    # row-major order, ignoring the min-distance constraint, so the
    # caller always gets exactly N positions.
    if len(chosen) < n:
        for _, _, pos in scored:
            if pos in chosen:
                continue
            chosen.append(pos)
            if len(chosen) >= n:
                break

    return chosen


def _chebyshev(a: Coord, b: Coord) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _cell_score(
    x: int, y: int, size: int,
    grid: List[List[str]],
    affinity: Dict[str, float],
    biome: str,
) -> float:
    """Score how good a HQ candidate cell ``(x, y)`` is.

    Heuristic components:

    1. **Terrain affinity** — the cell's terrain adds (or subtracts)
       a score per ``affinity[terrain]``.  Dense forest is bad; a
       nearby snow_peak ridge is good in a snow biome; a river
       (oasis) is great in a desert biome.
    2. **Distance to map edge** — castles on the frontier feel
       like "own territory".  Score = ``(min(x, y, size-1-x, size-1-y))``
       so cells close to the edge score high.
    3. **Distance from map center** — HQs should be far from each
       other but not in the dead centre (which would be a chaotic
       rush).  We prefer cells in the outer 2/3 of the map.
    4. **Visibility** — prefer cells whose 4-neighbour ring has at
       least 2 plain tiles (a clearing the castle can look out of).
    5. **Resource proximity** — bonus for being within 4 cells of a
       village or barracks (we want castles to *have* a starting
       economy).
    """
    terrain = grid[y][x]
    score = affinity.get(terrain, 0.0)

    # Frontier bonus: closer to the edge = higher score.  Cap at 5.
    edge_dist = min(x, y, size - 1 - x, size - 1 - y)
    score += max(0, 5 - edge_dist) * 0.3

    # Anti-centre penalty: cells in the middle 1/3 of the map get a
    # small penalty (too central = chaos at game start).
    cx, cy = size / 2, size / 2
    radial = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    max_radial = ((cx) ** 2 + (cy) ** 2) ** 0.5
    if radial < max_radial * 0.45:
        score -= 0.5

    # Visibility: count plain neighbours in the 4-connected ring.
    plain_count = 0
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < size and 0 <= ny < size:
            if grid[ny][nx] == "plain":
                plain_count += 1
    if plain_count < 2:
        score -= 1.0  # walled in by forest/mountain

    # Resource proximity: bonus for being within 4 cells of a
    # village or barracks.  We only sample a small window so this
    # stays O(1) per cell instead of O(size²).
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            nx, ny = x + dx, y + dy
            if 0 <= nx < size and 0 <= ny < size:
                t = grid[ny][nx]
                if t in ("village", "barracks"):
                    score += 0.4
    return score
