"""
Main MapGenerator — orchestrates the layered pipeline
(P1.4 / docs/规范/地图生成方案.md §1 + §8).

Public surface:

    gen = MapGenerator(size=15, player_count=4, style="grass_outer", seed=42)
    grid = gen.generate()                  # List[List[Tile]]
    castles = gen.castle_positions         # List[Tuple[int, int]]

The pipeline (see docs/superpowers/specs/2026-07-01-random-map-generation-spec.md §8):

    1. Initialize RNG (independent of global random).
    2. Compute castle positions and safe zones.
    3. Pick the mode from the style ("single_hq", "hq_with_struct",
       "castle_internal") and dispatch.
    4. For outer modes:
         a. Fill the grid with style-weighted terrain (avoiding safe
            zones).
         b. Place HQ structures (single-tile castles or 5×5 / 7×7
            templates).
         c. (Optional) forest clusters, mountain clusters, river
            network, buildings, road network.
         d. Connectivity check + repair (best-effort).
    5. For castle_internal: delegate to ``build_castle_internal_map``.

The generator is **deterministic**: identical ``(seed, size, style,
player_count)`` arguments produce byte-identical grids.  This is
critical for replays and bug reproduction (see spec §11).
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional, Tuple

from app.config import (
    MAP_STYLES,
    MAP_SIZE,
    STYLE_CASTLE_INTERNAL,
    STYLE_GRASS_OUTER,
    TERRAIN_CASTLE,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_SNOW_PEAK,
)
from app.models import Tile

from .castle_layout import (
    build_castle_internal_map,
    build_hq_structure,
    build_single_tile_castle,
)
from .quality import score_map
from .river_network import generate_river_network
from .road_network import generate_road_network, place_buildings
from .symmetry import (
    calculate_castle_positions,
    calculate_safe_zones,
    hq_layouts_for,
    hq_placement_for_biome,
    solo_faction_index,
)
from .terrain_clusters import (
    generate_forest_clusters,
    generate_mountain_clusters,
    verify_connectivity,
)
from .terrain_movement import (
    UNIT_TERRAIN_PREFERENCES,
    local_openness_score,
    reshape_local_terrain,
)

logger = logging.getLogger(__name__)

Coord = Tuple[int, int]


class MapGenerator:
    """Top-level procedural map generator.

    Parameters mirror ``game_logic.generate_map`` so the new module is
    a drop-in replacement.  See ``docs/规范/地图生成方案.md`` for the
    rationale behind the layout choices.
    """

    def __init__(
        self,
        size: int = MAP_SIZE,
        player_count: int = 4,
        style: str = STYLE_GRASS_OUTER,
        seed: Optional[int] = None,
        *,
        # Tunable knobs — all default to "off" so legacy callers see
        # the same maps they always did.  Flip these on for the new
        # richer procedural behaviour.
        use_clusters: bool = True,
        use_rivers: bool = True,
        use_roads: bool = True,
        use_buildings: bool = True,
        use_hq_structure: bool = False,
        # P2.7+ — when True, HQs are placed by terrain affinity
        # (see ``hq_placement_for_biome``) rather than the
        # symmetric corner / triangle layout.  Use this for the
        # "realistic" generator; the hand-authored balanced_*_Np
        # maps keep the symmetric layout.
        realistic_hq: bool = False,
        max_retries: int = 3,
        # terrain_movement — optional per-faction unit hints.  When
        # provided, ``generate()`` runs ``reshape_local_terrain`` for
        # each HQ so the local terrain favors that unit's strengths
        # (e.g. archer gets forest, knight gets road, flier is
        # unconstrained).  ``None`` = no shaping (legacy behaviour).
        unit_hints: Optional[List[str]] = None,
    ) -> None:
        if size < 5:
            raise ValueError(f"size must be >= 5 (got {size})")
        self.size = size
        self.player_count = max(2, min(4, player_count))
        self.style = style if style in MAP_STYLES else STYLE_GRASS_OUTER
        self.seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        self.use_clusters = use_clusters
        self.use_rivers = use_rivers
        # P0-1 — chapter_* styles (road_density < 0.05) skip the
        # road network entirely so the map matches FE's "no
        # explicit roads" aesthetic.  Pass use_roads=True to force.
        style_road_density = MAP_STYLES[self.style].get("road_density", 0.5)
        self.use_roads = use_roads and style_road_density >= 0.05
        self.use_buildings = use_buildings
        self.use_hq_structure = use_hq_structure
        self.realistic_hq = realistic_hq
        self.max_retries = max_retries
        # Pad / truncate unit_hints to player_count; unknown unit
        # types fall back to ``_balanced`` at reshape time.
        if unit_hints is None:
            self.unit_hints: List[str] = ["_balanced"] * self.player_count
        else:
            self.unit_hints = list(unit_hints)[: self.player_count]
            while len(self.unit_hints) < self.player_count:
                self.unit_hints.append("_balanced")

        self.style_cfg: Dict = MAP_STYLES[self.style]
        self.mode: str = self.style_cfg.get("mode", "single_hq")
        # P0-1 — the style's target terrain share (used by quality.score_map
        # to compute S7 "does this map match its style's personality?").
        # Stored on the instance so callers can read it after generate().
        self.target_share: Optional[Dict[str, float]] = self.style_cfg.get("target_share")
        # 学长 2026-07-22:差异化 HQ 摆位
        self.hq_layout: str = self.style_cfg.get("hq_layout", "auto")
        # 学长 2026-07-22:经济点分布参数
        self.economy_per_faction: int = int(
            self.style_cfg.get("economy_per_faction", 0)
        )
        self.neutral_economy: int = int(
            self.style_cfg.get("neutral_economy", 0)
        )
        self.asymmetry: Optional[Dict] = self.style_cfg.get("asymmetry")
        # P2.7+ — when realistic_hq is True, defer the placement to
        # ``generate()`` so we can score against the post-fill
        # terrain.  The list is empty until then; ``generate()``
        # overwrites it.  Otherwise use the legacy symmetric layout.
        self.castle_positions: List[Coord] = []
        if not realistic_hq:
            # 学长新需求:用 hq_layouts_for() 派发到差异化摆位
            # 需要 RNG,所以延迟到 generate() 内,这里只记占位
            self.castle_positions = []
        self.safe_zone_radius: int = int(
            self.style_cfg.get("safe_zone_radius", 2)
        )
        self.safe_zones = calculate_safe_zones(
            self.castle_positions, size, self.safe_zone_radius,
        )
        # terrain_movement bookkeeping: per-HQ openness score is
        # recorded by ``generate()`` so callers (and the front-end)
        # can show "this faction's local terrain favours their army".
        self.local_terrain_scores: Dict[int, float] = {}

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------

    def generate(self) -> List[List[Tile]]:
        """Build and return a Tile grid for the configured parameters."""
        logger.info(
            f"MapGenerator: generating {self.size}×{self.size} map, "
            f"style={self.style}, mode={self.mode}, seed={self.seed}, "
            f"players={self.player_count}, "
            f"features=(clusters={self.use_clusters}, rivers={self.use_rivers}, "
            f"roads={self.use_roads}, buildings={self.use_buildings})"
        )
        rng = random.Random(self.seed)
        if self.mode == "castle_internal":
            return self._generate_castle_internal(rng)
        return self._generate_outer(rng)

    # ------------------------------------------------------------------
    # Connectivity rescue (P0-5)
    # ------------------------------------------------------------------

    def _carve_connectivity(self, grid: List[List[Tile]]) -> None:
        """For every castle that is unreachable from castles[0] via
        passable terrain, BFS from that castle and replace the first
        impassable (mountain) cell along each BFS step with forest
        (still passable, just slower).  Repeat until either all castles
        are reachable or no more mountain-to-forest conversions help.
        """
        from collections import deque
        from .quality import _IMPASSABLE
        size = self.size
        castles = self.castle_positions
        if len(castles) < 2:
            return

        def _bfs(start, blocked):
            seen = {start}
            q = deque([start])
            while q:
                x, y = q.popleft()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < size and 0 <= ny < size):
                        continue
                    if (nx, ny) in seen or (nx, ny) in blocked:
                        continue
                    seen.add((nx, ny))
                    q.append((nx, ny))
            return seen

        for _ in range(20):  # cap iterations
            mountain_cells = {
                (x, y) for y in range(size) for x in range(size)
                if grid[y][x].terrain in _IMPASSABLE
            }
            start = castles[0]
            seen = _bfs(start, mountain_cells)
            unreachable = [c for c in castles if c not in seen]
            if not unreachable:
                return  # all connected
            carved = 0
            for castle in unreachable:
                # BFS from this castle through everything (no blocked)
                # until we hit a reachable cell.
                frontier = deque([castle])
                came_from = {castle: None}
                target = None
                while frontier and target is None:
                    cx, cy = frontier.popleft()
                    if (cx, cy) in seen:
                        target = (cx, cy)
                        break
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if not (0 <= nx < size and 0 <= ny < size):
                            continue
                        if (nx, ny) in came_from:
                            continue
                        came_from[(nx, ny)] = (cx, cy)
                        frontier.append((nx, ny))
                if target is None:
                    continue  # completely boxed in (shouldn't happen)
                # Walk back from target to castle, carving mountains
                # into forest.
                cur = target
                while came_from[cur] is not None:
                    prev = came_from[cur]
                    if grid[prev[1]][prev[0]].terrain in _IMPASSABLE:
                        grid[prev[1]][prev[0]] = Tile(
                            x=prev[0], y=prev[1], terrain=TERRAIN_FOREST,
                        )
                        carved += 1
                    cur = prev
                if carved:
                    return  # re-BFS on next iteration
            if carved == 0:
                return  # nothing more to do

    # P0-5 — dense styles (chapter_*) need more retries to satisfy
    # the H3 connectivity constraint.  Default is 3, bump to 10 for
    # any style with target_share mountain > 0.4.
    @property
    def _effective_max_retries(self) -> int:
        target = self.target_share or {}
        try:
            mountain_target = float(target.get(TERRAIN_MOUNTAIN, 0))
        except (TypeError, ValueError):
            mountain_target = 0.0
        if mountain_target > 0.4:
            return 10
        return self.max_retries

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------
    def score(self, grid: List[List[Tile]]) -> "QualityReport":
        """Run ``quality.score_map`` on ``grid`` using the generator's
        configured castles, size and target_share.  Convenience for
        callers that want a one-liner report after ``generate()``.

        Returns a ``QualityReport`` with soft scores (S1..S8) and any
        hard violations (H1..H5).  学长 2026-07-22 新加 H4/H5 + S8。
        """
        from .quality import score_map  # local import to avoid cycle
        return score_map(
            grid,
            self.castle_positions,
            self.size,
            target_share=self.target_share,
            per_faction_min=self.economy_per_faction,
            neutral_min=self.neutral_economy,
            asymmetry=self.asymmetry,
        )

    # ------------------------------------------------------------------
    # castle_internal — every tile is a castle_* sub-feature.
    # ------------------------------------------------------------------

    def _generate_castle_internal(self, rng: random.Random) -> List[List[Tile]]:
        return build_castle_internal_map(
            rng=rng,
            style_cfg=self.style_cfg,
            castles=self.castle_positions,
            size=self.size,
        )

    # ------------------------------------------------------------------
    # Outer modes: single_hq / hq_with_struct.
    # ------------------------------------------------------------------

    def _weighted_choice(
        self,
        rng: random.Random,
        weights: Dict[str, int],
    ) -> str:
        terrain_types = list(weights.keys())
        weight_values = list(weights.values())
        return rng.choices(terrain_types, weights=weight_values, k=1)[0]

    def _fill_base_terrain(
        self,
        rng: random.Random,
        weights: Dict[str, int],
    ) -> List[List[Tile]]:
        """Fill the grid with style-weighted terrain outside safe zones.

        P2.7+ — enforces the biome allow-list from
        ``docs/superpowers/specs/2026-07-08-realistic-terrain-spec.md``
        so we never put, e.g., a brown ``mountain`` in a snow biome or
        a green ``forest`` in a desert.  If the weighted sample violates
        the allow list, we re-sample up to ``_BIOME_MAX_REROLL`` times
        before falling back to the biome's primary terrain (plain in
        most cases) so we always make forward progress.
        """
        castle_set = set(self.castle_positions)
        # Default fallback: plain.  Picked per-biome so re-roll still
        # produces a sensible cell.
        primary_fallback = {
            "grass": TERRAIN_PLAIN,
            "snow": TERRAIN_PLAIN,
            "desert": TERRAIN_PLAIN,
            "compact": TERRAIN_PLAIN,
        }.get(self.style_cfg.get("biome", "grass"), TERRAIN_PLAIN)

        grid: List[List[Tile]] = []
        for y in range(self.size):
            row: List[Tile] = []
            for x in range(self.size):
                if (x, y) in castle_set:
                    row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE))
                    continue
                if (x, y) in self.safe_zones:
                    # Safe zone is plain (override any weighted sample).
                    row.append(Tile(x=x, y=y, terrain=TERRAIN_PLAIN))
                    continue
                t = self._sample_biome_ok_terrain(rng, weights, primary_fallback)
                row.append(Tile(x=x, y=y, terrain=t))
            grid.append(row)
        return grid

    # P2.7 — try the weighted sample; if it violates the biome allow
    # list, re-sample a few times before falling back to plain.  This
    # keeps the per-style weights meaningful (still drives the
    # majority of picks) while making it impossible to leak forbidden
    # terrain into a biome.
    _BIOME_MAX_REROLL = 6
    _BIOME_FORBIDDEN: Dict[str, Set[str]] = {
        "grass":  set(),
        "snow":   {TERRAIN_MOUNTAIN},                   # brown mountain doesn't match snow
        "desert": {TERRAIN_FOREST, TERRAIN_SNOW_PEAK},  # lush forest / silver peak don't fit arid
        "compact": set(),
    }

    def _sample_biome_ok_terrain(
        self,
        rng: random.Random,
        weights: Dict[str, int],
        primary_fallback: str,
    ) -> str:
        biome = self.style_cfg.get("biome", "grass")
        forbidden = self._BIOME_FORBIDDEN.get(biome, set())
        # Fast path: no forbidden terrain for this biome.
        if not forbidden:
            return self._weighted_choice(rng, weights)
        for _ in range(self._BIOME_MAX_REROLL):
            t = self._weighted_choice(rng, weights)
            if t not in forbidden:
                return t
        return primary_fallback

    # P2.7+ — when ``realistic_hq`` is set, the symmetric corner
    # layout is wrong for "real-place" maps.  We instead score
    # every cell against a terrain-affinity heuristic and pick the
    # top-N well-separated candidates.  This runs at the *end* of
    # the outer pipeline (after all terrain is in place) and
    # **stamps castle tiles** onto the chosen cells.
    def _stamp_realistic_hqs(
        self,
        grid: List[List[Tile]],
        rng: random.Random,
    ) -> List[Coord]:
        """Pick HQ positions by geographic logic and stamp the grid.

        Returns the list of HQ coords so the caller can also stamp
        a safe-zone ring around them.  The grid's castle tile list
        matches the returned coordinates one-to-one.
        """
        # Build a plain-string view of the grid (the scorer reads by
        # terrain name; we don't need sub-feature detail here).
        str_grid: List[List[str]] = [
            [t.terrain for t in row] for row in grid
        ]
        biome = self.style_cfg.get("biome", "grass")
        positions = hq_placement_for_biome(
            size=self.size,
            player_count=self.player_count,
            grid=str_grid,
            rng=rng,
            biome=biome,
            # Smaller maps need a smaller min distance; cap at 8
            # for big maps.  15x15 with 4p wants ~7-8.
            min_pair_distance=max(5, self.size // 2),
        )
        for (x, y) in positions:
            grid[y][x] = Tile(x=x, y=y, terrain=TERRAIN_CASTLE)
        return positions

    def _generate_outer(self, rng: random.Random) -> List[List[Tile]]:
        """Outer-style pipeline with retry-on-disconnect."""
        weights = self.style_cfg["weights"]

        # 学长 2026-07-22:在 _generate_outer 开头放 HQ(需要 RNG)
        # hq_layouts_for() 根据 style_cfg["hq_layout"] 派发到差异化摆位
        if not self.castle_positions:
            if self.realistic_hq:
                # realistic 模式延迟到地形填完再放,这里占位
                self.castle_positions = []
            else:
                self.castle_positions = hq_layouts_for(
                    self.size, self.player_count,
                    self.hq_layout, rng,
                )
                # 重新计算 safe zones
                self.safe_zones = calculate_safe_zones(
                    self.castle_positions, self.size,
                    self.safe_zone_radius,
                )

        last_grid: Optional[List[List[Tile]]] = None
        for attempt in range(self._effective_max_retries):
            attempt_rng = random.Random(rng.random() + attempt * 9973)
            grid = self._fill_base_terrain(attempt_rng, weights)

            # Forest & mountain clusters (cheap structural upgrade).
            # P2.7+ — skip both cluster types in biomes where the
            # corresponding terrain is biome-forbidden (snow:
            # brown mountain; desert: forest + snow_peak) so the
            # biomes stay pure.  Snow uses ``snow_peak`` (added by
            # the base fill) for its mountain-like look; desert gets
            # a flatter, drier appearance.
            biome = self.style_cfg.get("biome", "grass")
            biome_forbidden = self._BIOME_FORBIDDEN.get(biome, set())
            if self.use_clusters:
                if TERRAIN_FOREST not in biome_forbidden:
                    generate_forest_clusters(
                        attempt_rng, grid, self.size,
                        self.castle_positions, self.safe_zone_radius,
                    )
                if TERRAIN_MOUNTAIN not in biome_forbidden:
                    generate_mountain_clusters(
                        attempt_rng, grid, self.size,
                        self.castle_positions, self.safe_zone_radius,
                    )

            # River network — overwrites anything except protected tiles.
            # P0-3 — water_template comes from the style config so
            # "river" / "lake" / "mixed" can be selected per-style.
            if self.use_rivers:
                water_template = self.style_cfg.get("water_template", "river")
                # P0-3 — lake_size scales with map size; aim for ~10% of
                # cells if the style wants a big water body.
                lake_size = max(20, (self.size * self.size) // 10)
                generate_river_network(
                    attempt_rng, grid, self.size,
                    self.castle_positions, self.safe_zone_radius,
                    seed_count=2, branch_probability=0.3,
                    water_template=water_template,
                    lake_size=lake_size,
                )

            # Buildings (villages / barracks) before roads so the
            # network can connect them in one pass.
            # 学长 2026-07-22:per-faction + neutral 分配
            villages: List[Coord] = []
            barracks: List[Coord] = []
            if self.use_buildings:
                per_faction = self.economy_per_faction or None
                neutral = self.neutral_economy or None
                solo_idx = solo_faction_index(self.style_cfg, self.player_count) \
                    if self.asymmetry else None
                neutral_bias = (
                    (self.asymmetry or {}).get("neutral_bias")
                    if self.asymmetry else None
                )
                villages, barracks = place_buildings(
                    attempt_rng, grid, self.size, self.castle_positions,
                    # 老参数仍传,作为回退
                    village_count=max(2, self.player_count),
                    barracks_count=max(1, self.player_count // 2),
                    # 学长新规则
                    per_faction_count=per_faction,
                    neutral_count=neutral,
                    neutral_bias=neutral_bias,
                    solo_faction_idx=solo_idx,
                )

            # Road network.  For realistic_hq we don't yet know the
            # HQ positions, so defer the road build until after we
            # stamp castles below.
            if self.use_roads and not self.realistic_hq:
                generate_road_network(
                    attempt_rng, grid, self.size,
                    self.castle_positions, villages, barracks,
                    safe_zones=self.safe_zones,
                )

            # P2.7+ — "realistic" HQ placement.  Runs after the
            # terrain pass (so we can score against forest /
            # mountain / river) and overwrites whatever terrain was
            # at the chosen cells.  For non-realistic mode we
            # stamp castles on the legacy symmetric corners.
            if self.realistic_hq:
                self.castle_positions = self._stamp_realistic_hqs(
                    grid, attempt_rng,
                )
                # Recompute safe zones now that we know real HQs.
                self.safe_zones = calculate_safe_zones(
                    self.castle_positions, self.size,
                    self.safe_zone_radius,
                )
            else:
                # Legacy castle/HQ stamping: 5x5 structure (with
                # walls / door / stairs / vault) when
                # ``use_hq_structure`` is set, else a single-tile
                # castle at each corner.
                if self.use_hq_structure:
                    for centre in self.castle_positions:
                        build_hq_structure(grid, centre, self.size)
                else:
                    for centre in self.castle_positions:
                        build_single_tile_castle(grid, centre)

            # Roads after realistic HQ stamping.
            if self.use_roads and self.realistic_hq:
                generate_road_network(
                    attempt_rng, grid, self.size,
                    self.castle_positions, villages, barracks,
                    safe_zones=self.safe_zones,
                )

            # terrain_movement — bias the 5x5 around each HQ toward
            # the unit that faction was hinted to play.  Runs AFTER
            # buildings and AFTER HQ stamping (so we don't disturb
            # economy tiles or the HQ cell itself) but BEFORE
            # connectivity check (so the road network can re-draw
            # naturally toward the new layout on the next attempt).
            for i, centre in enumerate(self.castle_positions):
                unit = self.unit_hints[i] if i < len(self.unit_hints) else "_balanced"
                swaps = reshape_local_terrain(
                    grid, centre, unit,
                    radius=2, safe_zones=self.safe_zones, max_swaps=4,
                )
                if swaps:
                    logger.debug(
                        f"MapGenerator: HQ {i} ({unit}) — {swaps} local terrain swap(s)"
                    )

            # Connectivity check (best-effort, no rollback).
            if verify_connectivity(grid, self.castle_positions):
                last_grid = grid
                break
            # P0-5 — last-resort: carve a 1-cell-wide "guaranteed pass"
            # from each disconnected HQ to the nearest reachable cell.
            # This is a heavy hammer (we replace mountain with forest)
            # but it guarantees the map is playable even when the
            # terrain is dense.
            self._carve_connectivity(grid)
            if verify_connectivity(grid, self.castle_positions):
                last_grid = grid
                break
            logger.debug(f"MapGenerator: attempt {attempt + 1}/{self._effective_max_retries} connectivity FAILED (player_count={self.player_count})")
            last_grid = grid

        # Record per-HQ local openness scores (used by quality.py and
        # surfaced via the front-end "this faction's army fits this
        # terrain" tooltip).  Only meaningful when we have a grid.
        if last_grid is not None:
            for i, centre in enumerate(self.castle_positions):
                unit = self.unit_hints[i] if i < len(self.unit_hints) else "_balanced"
                self.local_terrain_scores[i] = local_openness_score(
                    last_grid, centre, unit, radius=2,
                )

        # If retries failed, just return the last attempt (the
        # generator always produces a grid; connectivity is a
        # diagnostic, not a hard requirement).
        if last_grid is None:
            # Shouldn't happen — even attempt 0 produces a grid — but
            # be defensive.
            last_grid = self._fill_base_terrain(rng, weights)
            for centre in self.castle_positions:
                build_single_tile_castle(last_grid, centre)
        return last_grid


__all__ = ["MapGenerator"]