"""P2.7+ — generate realistic-procedural maps using the improved generator.

Each map is generated with:
  - ``realistic_hq=True`` (HQ placed by terrain affinity, not corners)
  - biome-consistent terrain (snow has no brown mountain, desert no forest)
  - improved clustering (no isolated single tiles)
  - varied starting rosters (3-7 units per HQ, includes warlock)

Outputs static JSON files so the lobby can list them as named presets.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO / "game"))

from app.map_generation import MapGenerator
from app.config import (
    MAP_SIZE, STYLE_GRASS_OUTER, STYLE_SNOW_OUTER, STYLE_DESERT_OUTER,
)

from app.game_logic import (
    _castle_positions_for_size,
    _build_varied_initial_units,
    _CLASSIC_COLORS,
)

_MAPS_DIR = _REPO / "game" / "maps"

GENERATIONS: list[dict] = [
    # name, style, seed, size, players, biome
    {"id": "realistic_grass_2p_20", "name": "草原绿洲 2p",
     "desc": "开阔草原，森林簇簇，两条河流交汇",
     "style": STYLE_GRASS_OUTER, "seed": 20260708, "size": 20, "players": 2,
     "biome": "grass"},
    {"id": "realistic_snow_2p_20", "name": "雪域要塞 2p",
     "desc": "皑皑白雪中的银色山脊，冰河蜿蜒而过",
     "style": STYLE_SNOW_OUTER, "seed": 20260709, "size": 20, "players": 2,
     "biome": "snow"},
    {"id": "realistic_desert_2p_25", "name": "荒漠绿洲 2p",
     "desc": "干旱沙漠中零星绿洲，河流是唯一的生命线",
     "style": STYLE_DESERT_OUTER, "seed": 20260710, "size": 25, "players": 2,
     "biome": "desert"},
]


def main() -> int:
    _MAPS_DIR.mkdir(parents=True, exist_ok=True)
    for spec in GENERATIONS:
        print(f"Generating {spec['id']} ({spec['style']}, seed={spec['seed']})...")

        # Generate the terrain grid with realistic HQ placement.
        gen = MapGenerator(
            size=spec["size"],
            player_count=spec["players"],
            style=spec["style"],
            seed=spec["seed"],
            realistic_hq=True,
        )
        grid = gen.generate()
        layout: list[str] = []
        for y, row in enumerate(grid):
            # Convert Tile objects back to single-char layout.
            line_chars: list[str] = []
            for tile in row:
                ch = _tile_to_char(tile)
                line_chars.append(ch)
            layout.append("".join(line_chars))

        # Build HQ positions list (for initial_units placement).
        castles = gen.castle_positions
        assert len(castles) == spec["players"], (
            f"expected {spec['players']} HQs, got {len(castles)}"
        )

        # Generate varied initial units with a sub-seed.
        rng = random.Random(spec["seed"] + 999)
        initial_units = _build_varied_initial_units(castles, rng, map_size=spec["size"])

        # Build seat colours list from the castles in row-major order
        # (matching the convention the engine uses).
        hq_sorted = sorted(castles, key=lambda p: (p[1], p[0]))
        seat_colours = [_CLASSIC_COLORS[i % len(_CLASSIC_COLORS)]
                        for i in range(len(hq_sorted))]

        # Count initial_units per colour (informational).
        counts: dict[str, int] = {}
        for u in initial_units:
            c = u["color"]
            counts[c] = counts.get(c, 0) + 1

        data = {
            "id": spec["id"],
            "name": spec["name"],
            "description": spec["desc"],
            "biome": spec["biome"],
            "size": {"width": spec["size"], "height": spec["size"]},
            "layout": layout,
            "initial_units": initial_units,
            "recommended_players": spec["players"],
            "notes": (
                f"P2.7+ realistic 地图 — HQ 基于地形亲和力分布；"
                f"开局单位随机（{counts.get('red', 0)} red, "
                f"{counts.get('blue', 0)} blue）"
            ),
        }

        out_path = _MAPS_DIR / f"{spec['id']}.json"
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Print layout preview
        print(f"  Layout ({spec['size']}×{spec['size']}):")
        for y, row in enumerate(layout):
            print(f"    {y:2d}: {row}")
        print(f"  HQs at: {castles}")
        print(f"  Units per colour: {counts}")
        print(f"  Total units: {len(initial_units)}")
        print()

    return 0


def _tile_to_char(tile) -> str:
    """Reverse the char_to_terrain mapping used in _layout_to_tiles."""
    from app.config import (
        TERRAIN_PLAIN, TERRAIN_FOREST, TERRAIN_MOUNTAIN,
        TERRAIN_SNOW_PEAK, TERRAIN_RIVER, TERRAIN_CASTLE,
        TERRAIN_VILLAGE, TERRAIN_BARRACKS, TERRAIN_ROAD, TERRAIN_GATE,
        CASTLE_VAULT,
    )
    t = tile.terrain
    if t == TERRAIN_PLAIN:       return "P"
    if t == TERRAIN_FOREST:      return "F"
    if t == TERRAIN_MOUNTAIN:    return "M"
    if t == TERRAIN_SNOW_PEAK:   return "S"
    if t == TERRAIN_RIVER:       return "R"
    if t == TERRAIN_CASTLE:      return "C"
    if t == TERRAIN_VILLAGE:     return "v"
    if t == TERRAIN_BARRACKS:    return "b"
    if t == TERRAIN_ROAD:        return "r"
    if t == TERRAIN_GATE:        return "g"
    if t == CASTLE_VAULT:        return "$"
    return "."


if __name__ == "__main__":
    raise SystemExit(main())
