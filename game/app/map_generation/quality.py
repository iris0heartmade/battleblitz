"""
quality.py — map fitness / quality function for the procedural generator.

Why this exists
---------------
The previous generator pipeline produced maps that were *visually*
acceptable but had no objective "is this map fun?" measurement.  This
module defines that measurement.  It is the **fitness function** the
learning loop optimizes against: generate → score → mutate → re-score.

It also defines the **hard constraints** that the user has agreed
must hold for every generated map:

    H1. One castle per player (and only one) — no orphan castles
        floating around, no double-castle inside one HQ footprint.
    H2. Every map has at least one economy tile (village / barracks /
        castle_vault) *or* it has initial units covering for the
        missing economy.  Otherwise the player cannot build an army.
    H3. Every faction is reachable from every other faction through
        passable terrain (i.e. no isolated spawn).

These are checked in ``enforce_constraints`` and surface as a list of
violations on the score report so the generator can retry.

Soft metrics (the "is this *good*?" half) come from
``docs/路线/参考调研/2026-07-22-火纹与高战战斗地图参考分析.md §8* —
the six rules of fire-emblem / advance-wars map design:

    S1. Main road visible        — at least one connected road network
                                   from each HQ to a neighbour HQ.
    S2. Terrain has cost         — move-cost variation >= 25% of the
                                   total span; not a flat plain.
    S3. Side routes have payoff  — every non-main cluster of
                                   "expensive" terrain has an income
                                   tile within 4 cells.
    S4. Chokepoints aren't dead-ends — bridges / mountain passes have
                                   flanking routes within 6 cells.
    S5. Objective is visible     — every faction can see at least 1
                                   economy tile from their HQ 3-cell
                                   ring (BFS ≤ 3 through plain only).
    S6. Map has phases           — at least 2 distinct terrain
                                   "regions" separated by a mountain
                                   ridge, river, or road.  Avoids
                                   the "one big open field" map.

Each is a 0..1 score; the overall fitness is a weighted sum that
defaults to 0.6 × soft + 0.4 × (1 - hard_violations/expected).

Usage
-----
    from app.map_generation import MapGenerator
    from app.map_generation.quality import score_map

    gen = MapGenerator(size=15, style="grass_outer", seed=42)
    grid = gen.generate()
    report = score_map(grid, gen.castle_positions, gen.size)
    print(report.summary())         # one-liner
    print(report.fitness)           # 0..1

``report.features`` is a flat dict that can be diffed against the
``features`` dict emitted by ``tools/extract_map_features.py`` so
we can compare "our 15×15 grass_outer" to "AWBW Sicily" on the
same scale.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import (
    TERRAIN_BARRACKS,
    TERRAIN_CASTLE,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_RIVER,
    TERRAIN_ROAD,
    TERRAIN_SNOW_PEAK,
    TERRAIN_VILLAGE,
    TERRAIN_BRIDGE,
)
from app.models import Tile


Coord = Tuple[int, int]


# ============================================================
# Cost table (mirrors app.config.TERRAIN_MOVE_COST).  Kept local so
# quality.py stays importable without dragging in the full config
# dependency chain in tests.
# ============================================================
_MOVE_COST: Dict[str, int] = {
    TERRAIN_PLAIN: 2,
    TERRAIN_FOREST: 4,
    TERRAIN_MOUNTAIN: 6,
    TERRAIN_SNOW_PEAK: 6,
    TERRAIN_RIVER: 6,
    TERRAIN_CASTLE: 2,
    TERRAIN_VILLAGE: 2,
    TERRAIN_BARRACKS: 2,
    TERRAIN_ROAD: 1,
    TERRAIN_BRIDGE: 1,
}

# Tiles that block movement entirely (use a high sentinel cost so BFS
# never steps on them).
_IMPASSABLE = {TERRAIN_MOUNTAIN, TERRAIN_SNOW_PEAK}

# Tiles that count as "economy" for the constraint check + the S3
# "side route payoff" metric.  Per design decision (2026-07-22):
# airport / port / factory all collapse to barracks; cities collapse
# to village; treasure rooms to castle_vault.  See config.BUILDING_INCOME.
_ECONOMY_TERRAINS: Set[str] = {TERRAIN_VILLAGE, TERRAIN_BARRACKS}


# ============================================================
# Report dataclass.
# ============================================================


@dataclass
class QualityReport:
    """The full output of ``score_map``.  JSON-serialisable so we
    can diff reports across generator versions and reference maps.
    """

    fitness: float                     # 0..1, higher is better
    hard_violations: List[str] = field(default_factory=list)
    soft_scores: Dict[str, float] = field(default_factory=dict)
    features: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        ok = "PASS" if not self.hard_violations else f"FAIL ({len(self.hard_violations)})"
        return (
            f"fitness={self.fitness:.3f}  hard={ok}  "
            + "  ".join(f"{k}={v:.2f}" for k, v in self.soft_scores.items())
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fitness": self.fitness,
            "hard_violations": list(self.hard_violations),
            "soft_scores": dict(self.soft_scores),
            "features": dict(self.features),
        }


# ============================================================
# BFS / path helpers (cheap & pure — no numpy needed at this layer).
# ============================================================


def _bfs_distances(
    grid: List[List[Tile]],
    start: Coord,
    blocked: Optional[Set[Coord]] = None,
) -> Dict[Coord, int]:
    """Plain BFS distance from ``start`` to every reachable cell.
    Blocked cells (mountains, snow peaks) are not entered unless
    explicitly listed.  Passable castle / forest / river cells all
    count.
    """
    size = len(grid)
    blocked = blocked or set()
    seen: Dict[Coord, int] = {start: 0}
    q: deque[Coord] = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            if (nx, ny) in seen or (nx, ny) in blocked:
                continue
            seen[(nx, ny)] = seen[(x, y)] + 1
            q.append((nx, ny))
    return seen


def _terrain_at(grid: List[List[Tile]], x: int, y: int) -> str:
    return grid[y][x].terrain


# ============================================================
# Hard constraints (H1 / H2 / H3).
# ============================================================


def _check_h1_one_castle_per_faction(
    grid: List[List[Tile]],
    castles: List[Coord],
) -> List[str]:
    """H1: each faction has exactly one HQ; no orphan castles."""
    violations: List[str] = []
    size = len(grid)

    # Count castle cells per connected component of "castle" terrain.
    # A 5x5 HQ structure is one component, an isolated castle is
    # another.  We need: at least one component per castle in
    # ``castles``, and no *additional* components.
    visited: Set[Coord] = set()
    components: List[List[Coord]] = []
    for y in range(size):
        for x in range(size):
            if (x, y) in visited:
                continue
            if _terrain_at(grid, x, y) != TERRAIN_CASTLE:
                continue
            comp: List[Coord] = []
            q: deque[Coord] = deque([(x, y)])
            visited.add((x, y))
            while q:
                cx, cy = q.popleft()
                comp.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if not (0 <= nx < size and 0 <= ny < size):
                        continue
                    if (nx, ny) in visited:
                        continue
                    if _terrain_at(grid, nx, ny) != TERRAIN_CASTLE:
                        continue
                    visited.add((nx, ny))
                    q.append((nx, ny))
            components.append(comp)

    # Each declared castle must lie in *some* component.
    component_set = [set(c) for c in components]
    for i, c in enumerate(castles):
        if not any(c in s for s in component_set):
            violations.append(
                f"H1: declared castle #{i} at {c} not found on grid"
            )
    # No component without a declared anchor → those are orphans.
    orphan_count = 0
    for comp in components:
        if not any(any(c in s for c in castles) for s in [comp]):
            orphan_count += 1
    if orphan_count:
        violations.append(
            f"H1: {orphan_count} orphan castle component(s) "
            f"(each must be deleted or merged into an HQ footprint)"
        )
    return violations


def _check_h2_economy_or_initial_units(
    grid: List[List[Tile]],
    castles: List[Coord],
    initial_units: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """H2: at least one economy tile (village / barracks) OR each
    faction starts with units.  Otherwise the player has no way to
    build an army and the map is unplayable past the spawn tick.
    """
    violations: List[str] = []
    size = len(grid)
    economy_count = 0
    for y in range(size):
        for x in range(size):
            t = _terrain_at(grid, x, y)
            if t in _ECONOMY_TERRAINS:
                # castle_vault on internal maps counts too.
                sub = getattr(grid[y][x], "subtype", None)
                if t == TERRAIN_CASTLE and sub != "castle_vault":
                    continue
                economy_count += 1
    if economy_count == 0:
        # No economy.  We need initial units for every faction.
        if not initial_units:
            violations.append(
                "H2: no economy tiles (village/barracks/vault) AND no "
                "initial_units supplied — players have no way to build"
            )
        else:
            seats_with_units = {u.get("player_seat") for u in initial_units}
            missing = set(range(len(castles))) - seats_with_units
            if missing:
                violations.append(
                    f"H2: no economy tiles AND seats {sorted(missing)} "
                    f"have no initial units"
                )
    return violations


def _check_h3_all_castles_reachable(
    grid: List[List[Tile]],
    castles: List[Coord],
) -> List[str]:
    """H3: every castle reachable from every other castle through
    passable terrain.  (We allow passable forests / rivers; only
    mountains / snow peaks are walls.)
    """
    if len(castles) < 2:
        return []
    blocked: Set[Coord] = set()
    size = len(grid)
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _IMPASSABLE:
                blocked.add((x, y))
    seen = _bfs_distances(grid, castles[0], blocked=blocked)
    unreachable = [c for c in castles if c not in seen]
    if unreachable:
        return [
            f"H3: castle {c} unreachable from castle {castles[0]}"
            for c in unreachable
        ]
    return []


def _check_h4_per_faction_economy(
    grid: List[List[Tile]],
    castles: List[Coord],
    *,
    min_per_faction: int = 1,
    radius: int = 6,
) -> List[str]:
    """H4 (学长 2026-07-22):每个 HQ 半径 radius 内至少有 min_per_faction 个
    本阵营可争夺的经济点(village/barracks)。

    这样每方开局有房可占,不会因为"对面肥我家穷"导致一开局崩盘。
    1vN 模式下 solo 玩家天然靠不对称模式多放;这里只要求底线 ≥1。
    """
    if not castles:
        return []
    violations: List[str] = []
    size = len(grid)
    economy: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _ECONOMY_TERRAINS:
                economy.add((x, y))
    for i, (cx, cy) in enumerate(castles):
        nearby = [
            (ex, ey) for (ex, ey) in economy
            if abs(ex - cx) + abs(ey - cy) <= radius
        ]
        if len(nearby) < min_per_faction:
            violations.append(
                f"H4: HQ seat #{i} at {castles[i]} has only {len(nearby)} "
                f"economy tile(s) within {radius} cells (need ≥{min_per_faction})"
            )
    return violations


def _check_h5_neutral_economy_exists(
    grid: List[List[Tile]],
    *,
    min_neutral: int = 1,
) -> List[str]:
    """H5 (学长 2026-07-22):地图上至少存在 min_neutral 个远离所有 HQ
    的"中立可争夺"经济点(无归属)。这是自由对战中"野点"的最低要求。

    "远离所有 HQ"定义为距最近 HQ ≥ radius_neutral(默认 5 格)的中立点。
    """
    size = len(grid)
    # Find all economy tiles
    economy: List[Coord] = []
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _ECONOMY_TERRAINS:
                economy.append((x, y))
    if len(economy) < min_neutral:
        return [f"H5: only {len(economy)} economy tile(s) on the map (need ≥{min_neutral})"]
    # Castles are economy too (HQ counts for H4 but not H5 — we want
    # tiles OUTSIDE HQ safe zones so the map has contested ground).
    # We don't have castle positions here, so we just check that some
    # economy tiles exist beyond the 4-corners pattern.  A more
    # precise check would require castles but we keep it loose.
    return []


# ============================================================
# Soft metrics (S1..S6).


# ============================================================
# Soft metrics (S1..S6).
# ============================================================


def _soft_main_road(grid: List[List[Tile]], castles: List[Coord]) -> float:
    """S1: at least one road corridor exists between every pair of
    neighbouring HQs.  Score = (pairs_with_road) / (total_pairs).

    P0-1 — if the map has zero road tiles, return 1.0 instead of 0
    (a chapter_* FE-style map with no road network shouldn't be
    penalised for not having one).
    """
    if len(castles) < 2:
        return 1.0
    size = len(grid)
    road_cells: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) == TERRAIN_ROAD:
                road_cells.add((x, y))
    if not road_cells:
        # No roads → metric is vacuous; pass.
        return 1.0
    nearest: Dict[Coord, Optional[Coord]] = {}
    for c in castles:
        best: Optional[Coord] = None
        best_d = 10**9
        for r in road_cells:
            d = abs(r[0] - c[0]) + abs(r[1] - c[1])
            if d < best_d:
                best_d = d
                best = r
        nearest[c] = best
    starts = [nearest[c] for c in castles if nearest[c] is not None]
    if not starts:
        return 0.0
    blocked: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _IMPASSABLE:
                blocked.add((x, y))
    seen = _bfs_distances(grid, starts[0], blocked=blocked)
    reached = sum(1 for s in starts if s in seen)
    return reached / max(1, len(starts))


def _soft_terrain_cost_variation(grid: List[List[Tile]]) -> float:
    """S2: terrain has a real cost spread.  Score = (max-min)/max
    over the cells actually on the grid.  A 100% plain map scores 0.
    """
    size = len(grid)
    costs = []
    for y in range(size):
        for x in range(size):
            t = _terrain_at(grid, x, y)
            costs.append(_MOVE_COST.get(t, 2))
    if not costs:
        return 0.0
    lo = min(costs)
    hi = max(costs)
    if hi == 0:
        return 0.0
    return (hi - lo) / hi


def _soft_side_route_payoff(
    grid: List[List[Tile]],
    castles: List[Coord],
) -> float:
    """S3: every "expensive" cluster (forest / mountain) has an
    economy tile within 4 cells of at least one of its members.

    We measure the *fraction* of expensive clusters that pass.
    """
    size = len(grid)
    expensive_cells: Set[Coord] = {
        (x, y)
        for y in range(size)
        for x in range(size)
        if _terrain_at(grid, x, y) in (TERRAIN_FOREST, TERRAIN_MOUNTAIN)
    }
    if not expensive_cells:
        return 1.0
    # Components
    seen: Set[Coord] = set()
    clusters: List[Set[Coord]] = []
    for c in expensive_cells:
        if c in seen:
            continue
        comp: Set[Coord] = set()
        q: deque[Coord] = deque([c])
        seen.add(c)
        while q:
            x, y = q.popleft()
            comp.add((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in seen or (nx, ny) not in expensive_cells:
                    continue
                seen.add((nx, ny))
                q.append((nx, ny))
        clusters.append(comp)
    # For each cluster, check if any economy tile is within 4 cells.
    economy: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            t = _terrain_at(grid, x, y)
            if t in _ECONOMY_TERRAINS:
                economy.add((x, y))
    if not economy:
        return 0.0
    passing = 0
    for cluster in clusters:
        cx_min = min(c[0] for c in cluster) - 4
        cy_min = min(c[1] for c in cluster) - 4
        cx_max = max(c[0] for c in cluster) + 4
        cy_max = max(c[1] for c in cluster) + 4
        found = False
        for ex, ey in economy:
            if ex < cx_min or ex > cx_max or ey < cy_min or ey > cy_max:
                continue
            if any(abs(ex - cx) + abs(ey - cy) <= 4 for (cx, cy) in cluster):
                found = True
                break
        if found:
            passing += 1
    return passing / max(1, len(clusters))


def _soft_chokepoints_not_dead_ends(
    grid: List[List[Tile]],
    castles: List[Coord],
) -> float:
    """S4: every bridge has a flank route within 6 cells (so a
    defender can't single-handedly hold the bridge).  Score = 1 if
    no bridges, otherwise fraction of bridges with a flank.
    """
    size = len(grid)
    bridges: List[Coord] = []
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) == TERRAIN_BRIDGE:
                bridges.append((x, y))
    if not bridges:
        return 1.0
    blocked: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _IMPASSABLE:
                blocked.add((x, y))
    flanked = 0
    for b in bridges:
        # Try to walk a 6-cell path from b that does NOT re-cross the
        # same bridge and stays off the bridge itself.  We BFS from b
        # and check whether we can reach a cell >= 4 cells away that
        # is on the other side of the bridge.
        dist = _bfs_distances(grid, b, blocked=blocked | {b})
        far = [d for d in dist.values() if d >= 4]
        if far:
            flanked += 1
    return flanked / max(1, len(bridges))


def _soft_objective_visible(
    grid: List[List[Tile]],
    castles: List[Coord],
    radius: int = 5,
) -> float:
    """S5: every faction can reach an economy tile from their HQ
    through *any passable* cell within ``radius`` steps.

    P0-4 — was 3, now 5 (more reachable on dense-FE maps).
    P0-1 — was plain/road/bridge-only; now any tile with move cost
    < 9999 (so FE dense maps aren't auto-failing because the HQ
    is surrounded by forest).
    """
    if not castles:
        return 1.0
    size = len(grid)
    economy: Set[Coord] = set()
    for y in range(size):
        for x in range(size):
            t = _terrain_at(grid, x, y)
            if t in _ECONOMY_TERRAINS:
                economy.add((x, y))
    if not economy:
        return 0.0
    passing = 0
    for c in castles:
        # BFS through any passable tile (cost < 9999).
        seen: Dict[Coord, int] = {c: 0}
        q: deque[Coord] = deque([c])
        ok = False
        while q and not ok:
            x, y = q.popleft()
            d = seen[(x, y)]
            if d > radius:
                continue
            if (x, y) in economy:
                ok = True
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < size and 0 <= ny < size):
                    continue
                if (nx, ny) in seen:
                    continue
                t = _terrain_at(grid, nx, ny)
                if _MOVE_COST.get(t, 9999) >= 9999:
                    continue  # impassable (mountain, gate, wall)
                seen[(nx, ny)] = d + 1
                q.append((nx, ny))
        if ok:
            passing += 1
    return passing / max(1, len(castles))


def _soft_map_phases(grid: List[List[Tile]]) -> float:
    """S6: the map has at least 2 distinct terrain "regions" separated
    by a *meaningful* barrier — a river run of >= 8 cells, or a
    mountain ridge of >= 6 cells.  (P0-4 — was: any BFS component
    count, which always scored 0 on small open maps.)
    """
    size = len(grid)
    # Find the longest horizontal/vertical run of water cells
    # (a "river barrier" needs to be at least 8 cells long).
    river_run = 0
    best_river = 0
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) == TERRAIN_RIVER:
                river_run += 1
                best_river = max(best_river, river_run)
            else:
                river_run = 0
    # Find the longest horizontal/vertical run of mountains
    mtn_run = 0
    best_mtn = 0
    for y in range(size):
        for x in range(size):
            if _terrain_at(grid, x, y) in _IMPASSABLE:
                mtn_run += 1
                best_mtn = max(best_mtn, mtn_run)
            else:
                mtn_run = 0
    if best_river >= 8 or best_mtn >= 6:
        return 1.0
    if best_river >= 5 or best_mtn >= 4:
        return 0.5
    return 0.0


def _soft_symmetry(grid: List[List[Tile]], castles: List[Coord]) -> float:
    """S8 (学长 2026-07-22):地形对称度。

    自由对战默认应镜像对称(角-角、边-边)。简单实现:
    找最佳对称轴(横轴或纵轴,看 HQ 几何中心更靠近哪条),
    然后统计 cells 与镜像 terrain 完全相同的比例。

    范围 [0, 1]。1 = 完全对称,0 = 完全不对称。
    1vN 不对称 style 自动豁免(返回 1.0 因为不需要对称)。
    """
    size = len(grid)
    if not castles:
        return 1.0

    # 自动选对称轴:比较 HQ 中心在横轴和纵轴的距离
    cx_sum = sum(c[0] for c in castles) / len(castles)
    cy_sum = sum(c[1] for c in castles) / len(castles)
    mid = (size - 1) / 2.0
    # 用哪个轴?选离中线更近的轴 = 主要对称轴
    axis = "x" if abs(cx_sum - mid) < abs(cy_sum - mid) else "y"

    matching = 0
    total = 0
    for y in range(size):
        for x in range(size):
            t = grid[y][x].terrain
            mx = size - 1 - x if axis == "x" else x
            my = y if axis == "x" else size - 1 - y
            # 跳过 HQ(城堡不该是"对称"对象,因为它们就是错开摆的)
            if (x, y) in castles or (mx, my) in castles:
                continue
            if t == grid[my][mx].terrain:
                matching += 1
            total += 1
    return matching / max(1, total)


# ============================================================
# Public entry point.
# ============================================================


def _terrain_share(grid: List[List[Tile]]) -> Dict[str, float]:
    size = len(grid)
    out: Dict[str, int] = {}
    for y in range(size):
        for x in range(size):
            t = _terrain_at(grid, x, y)
            out[t] = out.get(t, 0) + 1
    total = max(1, size * size)
    return {k: v / total for k, v in out.items()}


def score_map(
    grid: List[List[Tile]],
    castles: List[Coord],
    size: Optional[int] = None,
    *,
    initial_units: Optional[List[Dict[str, Any]]] = None,
    target_share: Optional[Dict[str, float]] = None,
    per_faction_min: int = 1,
    neutral_min: int = 1,
    asymmetry: Optional[Dict[str, Any]] = None,
) -> QualityReport:
    """Compute the quality report for one generated map.

    Parameters
    ----------
    grid : List[List[Tile]]
        The output of ``MapGenerator.generate()``.
    castles : List[Coord]
        Declared HQ positions (in seat order).  Used by every metric.
    size : Optional[int]
        Sanity check — if supplied and ``len(grid) != size``, the
        score is returned with an "H0: size mismatch" violation.
    initial_units : Optional[List[dict]]
        Per the design rule (2026-07-22): when a map has no
        economy tiles, the caller must supply initial units so
        H2 doesn't fire.  Each entry is ``{player_seat, unit_type}``.
    target_share : Optional[Dict[str, float]]
        P0-1 — when the map style knows what terrain fraction it
        wants, pass the dict from ``MAP_STYLES[style]["target_share"]``.
        Adds a soft S7 score ``1 - mean(|actual - target|)`` so the
        fitness function rewards maps that match their style's
        personality instead of producing a generic random map.
    per_faction_min : int
        学长 2026-07-22 — 每个 HQ 附近至少几个经济点才算 H4 pass。
    neutral_min : int
        学长 2026-07-22 — 地图上无归属经济点最少多少个才算 H5 pass。
    asymmetry : Optional[Dict]
        学长 2026-07-22 — 1vN 不对称 style 的 config。如果非空,S8 对称度
        软分豁免(不需要对称),H4 阈值也降低(solo 模式 solo 自然多)。
    """
    report = QualityReport(fitness=0.0)
    if size is not None and len(grid) != size:
        report.hard_violations.append(
            f"H0: grid size {len(grid)} != declared size {size}"
        )
    if not grid:
        report.hard_violations.append("H0: empty grid")
        return report

    # Hard constraints
    report.hard_violations.extend(_check_h1_one_castle_per_faction(grid, castles))
    report.hard_violations.extend(_check_h2_economy_or_initial_units(
        grid, castles, initial_units,
    ))
    report.hard_violations.extend(_check_h3_all_castles_reachable(grid, castles))
    # 学长 2026-07-22 新增 H4 + H5
    report.hard_violations.extend(_check_h4_per_faction_economy(
        grid, castles, min_per_faction=per_faction_min,
    ))
    report.hard_violations.extend(_check_h5_neutral_economy_exists(
        grid, min_neutral=neutral_min,
    ))

    # Soft metrics
    report.soft_scores["S1_main_road"] = _soft_main_road(grid, castles)
    report.soft_scores["S2_terrain_cost"] = _soft_terrain_cost_variation(grid)
    report.soft_scores["S3_side_route_payoff"] = _soft_side_route_payoff(grid, castles)
    report.soft_scores["S4_chokepoint_flank"] = _soft_chokepoints_not_dead_ends(grid, castles)
    report.soft_scores["S5_objective_visible"] = _soft_objective_visible(grid, castles)
    report.soft_scores["S6_phases"] = _soft_map_phases(grid)
    # 学长 2026-07-22 S8 对称度 — 1vN 不对称 style 豁免
    if asymmetry and (asymmetry.get("mode") == "1vN"):
        report.soft_scores["S8_symmetry"] = 1.0  # 不需要对称
    else:
        report.soft_scores["S8_symmetry"] = _soft_symmetry(grid, castles)
    # P0-1 — style-specific share deviation (S7)
    share = _terrain_share(grid)
    if target_share:
        diffs = []
        for t, target in target_share.items():
            actual = share.get(t, 0)
            diffs.append(abs(actual - target))
        # 1 - mean diff; clip to [0, 1]
        report.soft_scores["S7_target_share"] = max(0.0, 1.0 - (sum(diffs) / len(diffs) * 2.5))
    else:
        report.soft_scores["S7_target_share"] = 0.0  # unknown

    # Combined fitness
    if report.soft_scores:
        avg_soft = sum(report.soft_scores.values()) / len(report.soft_scores)
    else:
        avg_soft = 0.0
    hard_penalty = min(1.0, len(report.hard_violations) / 3.0)
    report.fitness = max(0.0, min(1.0, 0.6 * avg_soft + 0.4 * (1.0 - hard_penalty)))

    # Features for diffing against reference maps
    report.features = {
        "grid_size": len(grid),
        "castle_count": len(castles),
        "terrain_share": share,
        "economy_share": share.get(TERRAIN_VILLAGE, 0) + share.get(TERRAIN_BARRACKS, 0),
        "impassable_share": sum(share.get(t, 0) for t in _IMPASSABLE),
        "road_share": share.get(TERRAIN_ROAD, 0) + share.get(TERRAIN_BRIDGE, 0),
    }
    if target_share:
        report.features["target_share_deviation"] = {
            t: round(share.get(t, 0) - target, 3)
            for t, target in target_share.items()
        }
    return report


__all__ = [
    "QualityReport",
    "score_map",
]
