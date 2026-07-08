"""
Main MapGenerator — orchestrates the layered pipeline
(P1.4 / MAP_GENERATION_PLAN.md §1 + §8).

Public surface:

    gen = MapGenerator(size=15, player_count=4, style="grass_outer", seed=42)
    grid = gen.generate()                  # List[List[Tile]]
    castles = gen.castle_positions         # List[Tuple[int, int]]

The pipeline (see random-map-generation-spec.md §8):

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
from .river_network import generate_river_network
from .road_network import generate_road_network, place_buildings
from .symmetry import (
    calculate_castle_positions,
    calculate_safe_zones,
    hq_placement_for_biome,
)
from .terrain_clusters import (
    generate_forest_clusters,
    generate_mountain_clusters,
    verify_connectivity,
)

logger = logging.getLogger(__name__)

Coord = Tuple[int, int]


class MapGenerator:
    """Top-level procedural map generator.

    Parameters mirror ``game_logic.generate_map`` so the new module is
    a drop-in replacement.  See ``MAP_GENERATION_PLAN.md`` for the
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
    ) -> None:
        if size < 5:
            raise ValueError(f"size must be >= 5 (got {size})")
        self.size = size
        self.player_count = max(2, min(4, player_count))
        self.style = style if style in MAP_STYLES else STYLE_GRASS_OUTER
        self.seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        self.use_clusters = use_clusters
        self.use_rivers = use_rivers
        self.use_roads = use_roads
        self.use_buildings = use_buildings
        self.use_hq_structure = use_hq_structure
        self.realistic_hq = realistic_hq
        self.max_retries = max_retries

        self.style_cfg: Dict = MAP_STYLES[self.style]
        self.mode: str = self.style_cfg.get("mode", "single_hq")
        # P2.7+ — when realistic_hq is True, defer the placement to
        # ``generate()`` so we can score against the post-fill
        # terrain.  The list is empty until then; ``generate()``
        # overwrites it.  Otherwise use the legacy symmetric layout.
        self.castle_positions: List[Coord] = []
        if not realistic_hq:
            self.castle_positions = calculate_castle_positions(
                size, self.player_count,
            )
        self.safe_zone_radius: int = int(
            self.style_cfg.get("safe_zone_radius", 2)
        )
        self.safe_zones = calculate_safe_zones(
            self.castle_positions, size, self.safe_zone_radius,
        )

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

        last_grid: Optional[List[List[Tile]]] = None
        for attempt in range(self.max_retries):
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
            if self.use_rivers:
                generate_river_network(
                    attempt_rng, grid, self.size,
                    self.castle_positions, self.safe_zone_radius,
                    seed_count=2, branch_probability=0.3,
                )

            # Buildings (villages / barracks) before roads so the
            # network can connect them in one pass.
            villages: List[Coord] = []
            barracks: List[Coord] = []
            if self.use_buildings:
                villages, barracks = place_buildings(
                    attempt_rng, grid, self.size, self.castle_positions,
                    village_count=max(2, self.player_count),
                    barracks_count=max(1, self.player_count // 2),
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

            # Connectivity check (best-effort, no rollback).
            if verify_connectivity(grid, self.castle_positions):
                last_grid = grid
                break
            logger.debug(f"MapGenerator: attempt {attempt + 1}/{self.max_retries} connectivity FAILED (player_count={self.player_count})")
            last_grid = grid

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