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


# ---------------------------------------------------------------------
# 学长 2026-07-22:差异化 HQ 摆位
# ---------------------------------------------------------------------
# 上面的 calculate_castle_positions 一直是固定模式:
#   2 → 对角,3 → 三角,4 → 四角。学长反馈"位置都比较固定,没有差异化"。
#
# 新加 hq_layouts_for() 函数,根据 style_cfg["hq_layout"] 返回不同的
# HQ 布局。仍然尊重"对角对称"等老传统,但加了 6+ 种新摆法:
#
#   scattered_2  : 2 个 HQ 不在对角,而在两条邻边
#   scattered_3  : 3 个 HQ 三角形但每张图旋转不同角度
#   scattered_4  : 4 个 HQ 不全在角,而是"3 角 + 1 中"或"全边"
#   line_3       : 3 个 HQ 在同一边均匀分布(适合"三国鼎立"图)
#   edge_pair_2  : 2 个 HQ 在对边中点(不是对角)
#   ring_3_vs_1  : 1 HQ 在中心 + 3 HQ 在外围(主线夺王座用)
#   asymmetric_1v2: 1 solo 在一角 + 2 multi 在对侧形成 base(学长新需求)
#   asymmetric_1v3: 1 solo 在一角 + 3 multi 三角围剿
#
# 返回格式跟 calculate_castle_positions 一样:List[(x, y)] in seat order。
# ---------------------------------------------------------------------


def hq_layouts_for(
    size: int,
    player_count: int,
    layout: str,
    rng: random.Random,
    inset: int = None,
) -> List[Coord]:
    """Dispatch to the right HQ layout function based on ``layout``.

    ``layout == "auto"`` falls back to ``calculate_castle_positions``
    (the original symmetric 2/3/4 layouts).  Other strings select
    one of the variants below.
    """
    if inset is None:
        inset = max(2, size // 8)
    far_inset = size - 1 - inset
    mid_x = size // 2
    mid_y = size // 2

    # "auto" → 老的固定对称布局
    if layout == "auto" or not layout:
        return calculate_castle_positions(size, player_count, inset=inset)

    # 学长新需求:差异化摆位
    if layout == "scattered_2":
        # 2 个 HQ 在相邻两条边的中段(不是对角)
        # 让一条边选 inset/2,另一条选 far_inset
        half = max(2, inset // 2)
        edge = rng.choice(["TL", "TR", "BL", "BR", "LR", "TB"])
        if edge == "TL":  # 左上 + 右上
            return [(half, half), (size - 1 - half, half)]
        if edge == "TR":  # 右上 + 左下
            return [(size - 1 - half, half), (half, size - 1 - half)]
        if edge == "BL":  # 左下 + 右上
            return [(half, size - 1 - half), (size - 1 - half, half)]
        if edge == "BR":  # 左下 + 右下
            return [(half, size - 1 - half), (size - 1 - half, size - 1 - half)]
        if edge == "LR":  # 左 + 右(对边中段)
            return [(half, mid_y), (size - 1 - half, mid_y)]
        # TB: 上 + 下
        return [(mid_x, half), (mid_x, size - 1 - half)]

    if layout == "scattered_3":
        # 3 HQ 三角形但每张图随机旋转
        rotation = rng.choice([0, 1, 2, 3])  # 0/90/180/270 度
        base = [(inset, inset), (far_inset, inset), (mid_x, far_inset)]
        if rotation == 0:
            return base
        # 90 度旋转 = (x, y) → (y, size-1-x)
        rot = [(y, size - 1 - x) for (x, y) in base]
        if rotation == 1:
            return rot
        rot2 = [(size - 1 - x, size - 1 - y) for (x, y) in base]
        if rotation == 2:
            return rot2
        return [(size - 1 - y, x) for (x, y) in base]

    if layout == "scattered_4":
        # 4 HQ 不全在角;两种变体随机
        variant = rng.choice(["corners", "3corners_1mid"])
        if variant == "corners":
            return [
                (inset, inset),
                (far_inset, inset),
                (inset, far_inset),
                (far_inset, far_inset),
            ]
        # 3 角 + 1 中
        corner = rng.choice([(inset, inset), (far_inset, inset),
                             (inset, far_inset), (far_inset, far_inset)])
        others = [
            (inset, inset), (far_inset, inset),
            (inset, far_inset), (far_inset, far_inset),
        ]
        others.remove(corner)
        return others + [corner]  # mid 排最后

    if layout == "line_3":
        # 3 个 HQ 沿同一边均匀分布
        side = rng.choice(["top", "bottom"])
        if side == "top":
            return [
                (size // 4, inset),
                (size // 2, inset),
                (3 * size // 4, inset),
            ]
        return [
            (size // 4, size - 1 - inset),
            (size // 2, size - 1 - inset),
            (3 * size // 4, size - 1 - inset),
        ]

    if layout == "edge_pair_2":
        # 2 HQ 在对边中点(不是对角)
        return [(mid_x, inset), (mid_x, size - 1 - inset)]

    if layout == "ring_3_vs_1":
        # 1 HQ 在中心 + 3 HQ 在外围(适合"夺王座"主线)
        return [
            (mid_x, mid_y),
            (inset, inset),
            (far_inset, inset),
            (mid_x, far_inset),
        ]

    if layout == "asymmetric_1v2":
        # 学长需求:1 solo 在一角,2 multi 在对侧成 base
        # solo_seat 默认 0 → 右上角
        solo = (far_inset, inset)
        # multi 在左下形成一对 base(便于配合)
        # 注意:y 用 far_inset - 1(留点空),x 用 inset 和 mid_x
        return [
            solo,                              # seat 0 = solo
            (inset, far_inset),                # seat 1 = multi 左下
            (mid_x, far_inset - 1),            # seat 2 = multi 中下偏内
        ]

    if layout == "asymmetric_1v3":
        # 学长需求:1 solo 在一角,3 multi 围剿
        solo = (far_inset, inset)
        return [
            solo,                              # seat 0 = solo
            (inset, far_inset),                # seat 1 = multi 左下
            (mid_x, far_inset - 1),            # seat 2 = multi 中下
            (inset, mid_y),                    # seat 3 = multi 左中
        ]

    # 未知 layout → 回落到老 auto
    return calculate_castle_positions(size, player_count, inset=inset)


def solo_faction_index(style_cfg: Dict, player_count: int) -> Optional[int]:
    """Return the seat index of the solo faction in 1vN mode, or None.

    学长 2026-07-22:solo 玩家比多人方资源多。如果 style 不是 1vN 模式
    返回 None(对称情况下不需要区分 solo vs multi)。
    """
    asymmetry = style_cfg.get("asymmetry") or {}
    if asymmetry.get("mode") != "1vN":
        return None
    return asymmetry.get("solo_seat", 0)


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
