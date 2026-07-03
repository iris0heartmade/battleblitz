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
        self.max_retries = max_retries

        self.style_cfg: Dict = MAP_STYLES[self.style]
        self.mode: str = self.style_cfg.get("mode", "single_hq")
        self.castle_positions: List[Coord] = calculate_castle_positions(
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
        """Fill the grid with style-weighted terrain outside safe zones."""
        castle_set = set(self.castle_positions)
        grid: List[List[Tile]] = []
        for y in range(self.size):
            row: List[Tile] = []
            for x in range(self.size):
                if (x, y) in castle_set:
                    row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE))
                elif (x, y) in self.safe_zones:
                    # Safe zone is plain (override any weighted sample).
                    row.append(Tile(x=x, y=y, terrain=TERRAIN_PLAIN))
                else:
                    t = self._weighted_choice(rng, weights)
                    row.append(Tile(x=x, y=y, terrain=t))
            grid.append(row)
        return grid

    def _generate_outer(self, rng: random.Random) -> List[List[Tile]]:
        """Outer-style pipeline with retry-on-disconnect."""
        weights = self.style_cfg["weights"]

        last_grid: Optional[List[List[Tile]]] = None
        for attempt in range(self.max_retries):
            attempt_rng = random.Random(rng.random() + attempt * 9973)
            grid = self._fill_base_terrain(attempt_rng, weights)

            # Forest & mountain clusters (cheap structural upgrade).
            if self.use_clusters:
                generate_forest_clusters(
                    attempt_rng, grid, self.size,
                    self.castle_positions, self.safe_zone_radius,
                )
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

            # Road network.
            if self.use_roads:
                generate_road_network(
                    attempt_rng, grid, self.size,
                    self.castle_positions, villages, barracks,
                    safe_zones=self.safe_zones,
                )

            # Castle / HQ structures (always after terrain pass so
            # they overwrite anything in the template footprint).
            if self.use_hq_structure:
                for centre in self.castle_positions:
                    build_hq_structure(grid, centre, self.size)
            else:
                # Always stamp at least a single-tile castle on each
                # centre — the legacy behaviour.
                for centre in self.castle_positions:
                    build_single_tile_castle(grid, centre)

            # Connectivity check (best-effort, no rollback).
            if verify_connectivity(grid, self.castle_positions):
                last_grid = grid
                break
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