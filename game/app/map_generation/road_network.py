"""
Road network and building placement (P1.4 / docs/规范/地图生成方案.md §4).

Roads use a simple A* over the terrain-cost table.  Each "important
node" (castle centre, village, barracks) gets connected to its two
nearest neighbours from the same node class.  Roads avoid rivers and
mountains by treating them as blocked cells.

Villages / barracks are placed before roads so the network can connect
them in a single pass.
"""
from __future__ import annotations

import heapq
import random
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from app.config import (
    TERRAIN_BARRACKS,
    TERRAIN_BRIDGE,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_RIVER,
    TERRAIN_ROAD,
    TERRAIN_VILLAGE,
)
from app.models import Tile

from .symmetry import is_in_safe_zone

Coord = Tuple[int, int]


# ---------------------------------------------------------------------
# Movement cost & blockers — kept local to avoid touching utils.py.
# ---------------------------------------------------------------------

# ``TERRAIN_MOVE_COST`` from app.config is the canonical source but we
# mirror the relevant subset here so road_network has no circular
# dependency on app.utils.  Roads are the cheapest terrain (half MP).
_LOCAL_COST: Dict[str, int] = {
    TERRAIN_PLAIN: 2,
    TERRAIN_ROAD: 1,
    TERRAIN_VILLAGE: 2,
    TERRAIN_BARRACKS: 2,
    # Castles (incl. all castle_* sub-features) are walkable.
    "castle": 2,
    TERRAIN_MOUNTAIN: 99,
    TERRAIN_RIVER: 6,
    # Bridge: same cost as road (1) so the A* naturally prefers to
    # cross via existing bridges when the road network already has
    # one, which keeps new roads aligned with old ones.
    TERRAIN_BRIDGE: 1,
}

# Cells that A* will not enter for the road builder.  Rivers used to
# be here, but P2.8+ lets roads cross rivers — the cell becomes a
# ``bridge`` instead.  Mountains stay impassable (no mountain tunnel).
_BLOCKED = {TERRAIN_MOUNTAIN, "castle_wall"}


def _in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def _neighbors4(x: int, y: int) -> List[Coord]:
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


# ---------------------------------------------------------------------
# A* pathfinder — terrain-aware, integer costs.
# ---------------------------------------------------------------------


def a_star_path(
    start: Coord,
    goal: Coord,
    terrain: Dict[Coord, str],
    size: int,
    blocked: Optional[Set[Coord]] = None,
) -> Optional[List[Coord]]:
    """Cheapest A* path between two coords on the terrain map.

    ``terrain`` is a dict of ``(x, y) -> terrain_id``.  ``blocked`` is
    an optional set of coords that are completely impassable (e.g.
    rivers when planning a road network that must avoid water).
    """
    blocked = blocked or set()
    if start not in terrain or goal not in terrain:
        return None
    if start == goal:
        return [start]

    def _h(p: Coord) -> int:
        return abs(p[0] - goal[0]) + abs(p[1] - goal[1])

    counter = 0
    pq: List[Tuple[int, int, Coord]] = [(_h(start), counter, start)]
    came_from: Dict[Coord, Coord] = {}
    best: Dict[Coord, int] = {start: 0}

    while pq:
        f, _, cur = heapq.heappop(pq)
        if cur == goal:
            path = [cur]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            path.reverse()
            return path
        if f > best.get(cur, float("inf")) + _h(cur):
            continue
        for nx, ny in _neighbors4(*cur):
            if not _in_bounds(nx, ny, size):
                continue
            np = (nx, ny)
            if np in blocked:
                continue
            t = terrain.get(np, TERRAIN_PLAIN)
            if t in _BLOCKED:
                continue
            step = _LOCAL_COST.get(t, 2)
            new_cost = best[cur] + step
            if new_cost < best.get(np, float("inf")):
                best[np] = new_cost
                came_from[np] = cur
                counter += 1
                heapq.heappush(pq, (new_cost + _h(np), counter, np))
    return None


# ---------------------------------------------------------------------
# Building placement.
# ---------------------------------------------------------------------


def place_buildings(
    rng: random.Random,
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    village_count: int = 4,
    barracks_count: int = 2,
    village_min_distance: int = 3,
    village_castle_distance: int = 4,
    barracks_min_distance: int = 4,
    barracks_castle_distance: int = 5,
    *,
    # 学长 2026-07-22:经济点分布规则
    # 默认 None = 用老逻辑(village_count/barracks_count 均匀分布)
    # 非 None = 按 style_cfg 给的规则放置
    per_faction_count: Optional[int] = None,   # 每个 HQ 附近保证 N 个经济点
    neutral_count: Optional[int] = None,       # 无归属经济点(地图中央)
    neutral_bias: Optional[str] = None,        # "toward_multi" / "toward_solo" / None
    solo_faction_idx: Optional[int] = None,    # 1vN 模式下 solo 的 seat
    seat_to_faction: Optional[Dict[int, str]] = None,  # seat → "solo"/"multi"/"neutral"
) -> Tuple[List[Coord], List[Coord]]:
    """Drop villages and barracks on passable tiles.

    Returns ``(villages, barracks)`` — lists of placed coords in
    seat order when ``per_faction_count`` is set, otherwise in
    placement order.  Tiles are mutated in place.  No-op when
    counts are zero or the map is too small.

    学长 2026-07-22 新规则:
    - ``per_faction_count=N``:每个 HQ 附近至少放 N 个经济点
      (1 个 village + N-1 个 barracks,或全 village 看空间)。
    - ``neutral_count=M``:另外放 M 个无归属经济点。
    - ``neutral_bias="toward_multi"``:neutral 偏向多人方一侧(1vN 公平性)。
    """
    villages: List[Coord] = []
    barracks: List[Coord] = []

    def _candidate_passes(
        coord: Coord,
        others: Iterable[Coord],
        other_dist: int,
        castle_dist: int,
    ) -> bool:
        if is_in_safe_zone(coord, castles, radius=2):
            return False
        x, y = coord
        t = grid[y][x].terrain
        if t in (TERRAIN_MOUNTAIN, TERRAIN_RIVER, "castle_wall", TERRAIN_ROAD):
            return False
        if any(_md(coord, o) < other_dist for o in others):
            return False
        if any(_md(coord, c) < castle_dist for c in castles):
            return False
        return True

    def _try_place(
        kind: str,
        others: List[Coord],
        other_dist: int,
        castle_dist: int,
        limit: int,
        # 偏置:从指定方向采样更多次(学长 neutral 偏置需求)
        preferred_sampler: Optional[Callable[[], Coord]] = None,
    ) -> Optional[Coord]:
        terrain_id = TERRAIN_VILLAGE if kind == "village" else TERRAIN_BARRACKS
        attempts = max(limit, 50) if preferred_sampler is None else limit
        for _ in range(attempts):
            if preferred_sampler is not None and rng.random() < 0.6:
                x, y = preferred_sampler()
            else:
                x = rng.randint(0, size - 1)
                y = rng.randint(0, size - 1)
            if not _candidate_passes(
                (x, y), others, other_dist, castle_dist,
            ):
                continue
            grid[y][x] = Tile(x=x, y=y, terrain=terrain_id)
            return (x, y)
        return None

    attempts_per_building = max(50, size * 5)

    # ============================================================
    # 学长 2026-07-22 新规则:per-faction + neutral 分配
    # ============================================================
    if per_faction_count is not None and castles:
        # 1) 每个 HQ 附近先放 per_faction_count 个本阵营经济点
        #    规则:第 1 个放 village(收入低/安全),第 2+ 放 barracks(出兵)
        per_castle = list(castles)
        for i, castle in enumerate(per_castle):
            nearby: List[Coord] = []
            for j in range(per_faction_count):
                kind = "village" if j == 0 else "barracks"
                # 学长 2026-07-22:per-faction 模式给更多尝试次数
                # 因为周围可能已经被山/河占了
                attempts = attempts_per_building * 4
                placed = _try_place(
                    kind, villages + barracks + nearby,
                    other_dist=3, castle_dist=3,   # castle_dist 3 让城周围稍密
                    limit=attempts,
                )
                if placed is not None:
                    nearby.append(placed)
                    if kind == "village":
                        villages.append(placed)
                    else:
                        barracks.append(placed)

        # 2) 放 neutral_count 个无归属经济点,带偏置
        if neutral_count:
            multi_centroid: Optional[Coord] = None
            if neutral_bias == "toward_multi" and castles and solo_faction_idx is not None:
                multi_coords = [c for i, c in enumerate(castles) if i != solo_faction_idx]
                if multi_coords:
                    mx = sum(c[0] for c in multi_coords) / len(multi_coords)
                    my = sum(c[1] for c in multi_coords) / len(multi_coords)
                    multi_centroid = (mx, my)

            def _biased_sampler():
                # 从 multi_centroid 周围 ±size/4 的方块内采样
                if multi_centroid is None:
                    return (rng.randint(0, size - 1), rng.randint(0, size - 1))
                bx = int(multi_centroid[0]) + rng.randint(-size // 4, size // 4)
                by = int(multi_centroid[1]) + rng.randint(-size // 4, size // 4)
                bx = max(0, min(size - 1, bx))
                by = max(0, min(size - 1, by))
                return (bx, by)

            for j in range(neutral_count):
                kind = "village" if j % 2 == 0 else "barracks"
                placed = _try_place(
                    kind, villages + barracks,
                    other_dist=3, castle_dist=4,
                    limit=attempts_per_building * 2,
                    preferred_sampler=_biased_sampler
                    if neutral_bias == "toward_multi"
                    else None,
                )
                if placed is not None:
                    if kind == "village":
                        villages.append(placed)
                    else:
                        barracks.append(placed)
        return villages, barracks

    # ============================================================
    # 老的均匀分布逻辑(village_count/barracks_count 模式)
    # ============================================================
    for _ in range(village_count):
        placed = _try_place(
            "village", villages, village_min_distance,
            village_castle_distance, attempts_per_building,
        )
        if placed is not None:
            villages.append(placed)

    for _ in range(barracks_count):
        placed = _try_place(
            "barracks", villages + barracks, barracks_min_distance,
            barracks_castle_distance, attempts_per_building,
        )
        if placed is not None:
            barracks.append(placed)

    return villages, barracks


# ---------------------------------------------------------------------
# Road network — connect every castle ↔ nearest village ↔ nearest
# barracks.  Roads overwrite plains/forest but never rivers/mountains.
# ---------------------------------------------------------------------


def _terrain_map(grid: List[List[Tile]]) -> Dict[Coord, str]:
    return {(t.x, t.y): t.terrain for row in grid for t in row}


def generate_road_network(
    rng: random.Random,  # noqa: ARG001 — kept for future stochastic tiebreakers
    grid: List[List[Tile]],
    size: int,
    castles: List[Coord],
    villages: List[Coord],
    barracks: List[Coord],
    safe_zones: Optional[Set[Coord]] = None,
) -> int:
    """Stamp roads along A* paths between every interesting node pair.

    Returns the number of road tiles placed.  Existing road tiles are
    preserved (not double-counted).  Roads never overwrite castle
    centres, mountain tiles, castle_walls, or castle safe-zone cells.

    P2.8+ — roads are now allowed to cross rivers.  When an A* path
    would step on a river tile, the cell is converted to a
    ``bridge`` tile instead of a road, so the river stays
    continuous on either side of the bridge and the player has a
    clear "this is a crossing" visual cue.

    For "attack lines" the road network also explicitly pairs each
    HQ with the village / barracks cluster of its *farthest* enemy
    HQ (when there are 2+ castles), guaranteeing a multi-HQ road
    corridor on every realistic map.
    """
    terrain = _terrain_map(grid)
    blocked: Set[Coord] = {
        (x, y)
        for y in range(size)
        for x in range(size)
        if grid[y][x].terrain == TERRAIN_MOUNTAIN
        or getattr(grid[y][x], "subtype", None) == "castle_wall"
    }
    # Don't draw roads on top of village/barracks/castle centres —
    # those should still be visible.  But do connect *to* them.
    anchor_blocked: Set[Coord] = (
        blocked
        | {c for c in castles}
        | set(villages)
        | set(barracks)
        | (safe_zones or set())
    )

    nodes: List[Coord] = list(castles) + list(villages) + list(barracks)
    if len(nodes) < 2:
        return 0

    # Pair every node with its two nearest neighbours (within the same
    # class), plus castle ↔ castle pairs.  Cheap O(N^2) sweep — maps
    # have at most a few hundred nodes.
    pairs: Set[Tuple[Coord, Coord]] = set()
    for i, a in enumerate(nodes):
        ranked = sorted(
            ((_md(a, b), b) for j, b in enumerate(nodes) if j != i),
            key=lambda t: t[0],
        )
        for _, b in ranked[:2]:
            pair = tuple(sorted((a, b)))
            pairs.add(pair)
    # P2.8+ — also pair every castle with its farthest enemy castle
    # so attack lines (multi-HQ road corridors) are guaranteed.
    # Picked because long-range road corridors are what makes a map
    # feel "driveable" instead of "scattered".
    if len(castles) >= 2:
        for i, a in enumerate(castles):
            ranked = sorted(
                ((_md(a, b), b) for j, b in enumerate(castles) if j != i),
                key=lambda t: -t[0],  # farthest first
            )
            if ranked:
                _, far = ranked[0]
                pairs.add(tuple(sorted((a, far))))

    road_count = 0
    for a, b in pairs:
        path = a_star_path(
            start=a, goal=b, terrain=terrain, size=size, blocked=blocked,
        )
        if path is None:
            continue
        # Skip the endpoints (don't overwrite the anchor tile).
        for step in path[1:-1]:
            if step in anchor_blocked:
                continue
            x, y = step
            existing = grid[y][x].terrain
            # Don't bury a non-plain existing terrain that's not a
            # road — keeps the path readable.
            if existing in (TERRAIN_VILLAGE, TERRAIN_BARRACKS, "castle"):
                continue
            if existing == TERRAIN_MOUNTAIN:
                continue
            if existing == TERRAIN_ROAD:
                continue  # already a road
            if existing == TERRAIN_BRIDGE:
                continue  # already a bridge
            # P2.8+ — river cells along a road path become bridges.
            if existing == TERRAIN_RIVER:
                grid[y][x] = Tile(x=x, y=y, terrain=TERRAIN_BRIDGE)
                terrain[(x, y)] = TERRAIN_BRIDGE
                road_count += 1
                continue
            grid[y][x] = Tile(x=x, y=y, terrain=TERRAIN_ROAD)
            terrain[(x, y)] = TERRAIN_ROAD
            road_count += 1
    return road_count


def _md(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])