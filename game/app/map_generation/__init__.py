"""
Random map generation — P1.4 refactor (MAP_GENERATION_PLAN.md).

Sub-modules:

  generator       — main entry point; orchestrates the layered pipeline.
  castle_layout   — HQ 5×5/7×7 structure and the castle_internal BSP style.
  terrain_clusters — Poisson-disk-style forest / mountain clusters.
  river_network   — random-walk rivers with branch + repair passes.
  road_network    — A* road network connecting castles ↔ villages ↔ barracks.
  symmetry        — rotation-symmetric castle positions and safe zones.

Backwards compatibility: ``app.game_logic.generate_map()`` still exists
as a thin wrapper that delegates here.
"""
from __future__ import annotations

from .generator import MapGenerator
from .castle_layout import (
    build_castle_internal_map,
    build_hq_structure,
    build_single_tile_castle,
)
from .symmetry import (
    calculate_castle_positions,
    calculate_safe_zones,
    is_in_safe_zone,
)
from .terrain_clusters import (
    cluster_target_count,
    generate_forest_clusters,
    generate_mountain_clusters,
    verify_connectivity,
)
from .river_network import generate_river_network
from .road_network import (
    a_star_path,
    generate_road_network,
    place_buildings,
)

__all__ = [
    "MapGenerator",
    # castle layouts
    "build_castle_internal_map",
    "build_hq_structure",
    "build_single_tile_castle",
    # symmetry
    "calculate_castle_positions",
    "calculate_safe_zones",
    "is_in_safe_zone",
    # clusters
    "cluster_target_count",
    "generate_forest_clusters",
    "generate_mountain_clusters",
    "verify_connectivity",
    # rivers / roads
    "a_star_path",
    "generate_river_network",
    "generate_road_network",
    "place_buildings",
]