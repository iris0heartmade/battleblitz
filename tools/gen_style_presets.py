"""Generate P2.4 multi-style map presets.

For each of the 5 styles (grass_outer / snow_outer / desert_outer /
compact_outer / castle_internal) we run the procedural generator across
the cross product (style × {2,3,4} players × recommended size) and
write each result out as a JSON file in game/maps/. The presets are
named `<style>_<size>_<players>p`.

The point of writing each result to a JSON file rather than relying on
live procedural generation is reproducibility — two players sharing
the same preset_id + seed must see the same map, and hand-edits in the
custom-map editor also need a stable JSON target.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

# Import the procedural generator + style table from the game package.
# We don't `cd` into game/ because we want this script to run from
# any CWD. The package is imported by file path via repo-relative config.
HERE = Path(__file__).resolve().parent
GAME_DIR = HERE.parent / "game"
sys.path.insert(0, str(GAME_DIR))

from app.config import (
    MAP_STYLES, STYLE_GRASS_OUTER, STYLE_SNOW_OUTER,
    STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER, STYLE_ISLAND_OUTER,
    STYLE_CHAPTER_GRASS, STYLE_CHAPTER_SNOW, STYLE_CHAPTER_SEIZE,
    STYLE_ASYMMETRIC_1V2, STYLE_ASYMMETRIC_1V3,
    CASTLE_THRONE, CASTLE_DOOR,
    CASTLE_STAIRS, CASTLE_VAULT, CASTLE_WALL, CASTLE_FLOOR,
)
from app.map_generation import MapGenerator  # noqa: E402

OUT_DIR = GAME_DIR / "maps"

# Cross-product definition:
#   style → list of (size, num_players) tuples.
# P0-5 — added island_outer + 3 chapter_* styles.
STYLE_SIZES: Dict[str, List[int]] = {
    STYLE_GRASS_OUTER:   [15, 20],
    STYLE_SNOW_OUTER:    [20, 25],
    STYLE_DESERT_OUTER:  [20],
    STYLE_COMPACT_OUTER: [15],
    STYLE_ISLAND_OUTER:  [20, 25],
    # P0-1 — mainline chapter styles (FE-style)
    STYLE_CHAPTER_GRASS: [15, 20],
    STYLE_CHAPTER_SNOW:  [20],
    STYLE_CHAPTER_SEIZE: [15],
    # 学长 2026-07-22 — 1vN 不对称设计(玩家数固定,1v2=3p,1v3=4p)
    STYLE_ASYMMETRIC_1V2: [20],
    STYLE_ASYMMETRIC_1V3: [20, 25],
}

# Player counts we generate for each cell. The procedural generator
# supports 2/3/4 players; we emit all three so the lobby's 3p
# category has real options (P2.4 polish).
# 学长 2026-07-22:1vN style 锁定玩家数(1v2→3p,1v3→4p)
DEFAULT_PLAYER_COUNTS = [2, 3, 4]
STYLE_PLAYER_COUNTS: Dict[str, List[int]] = {
    STYLE_ASYMMETRIC_1V2: [3],
    STYLE_ASYMMETRIC_1V3: [4],
}


def _tile_to_char(terrain: str, subtype: str | None) -> str:
    """Compress a Tile row into the single-char layout grammar.

    Castle sub-features are compressed to lower-case identifiers so a
    JSON preset round-trips through `_layout_to_tiles` losslessly.
    """
    if subtype == CASTLE_FLOOR:
        return "f"
    if subtype == CASTLE_WALL:
        return "w"
    if subtype == CASTLE_THRONE:
        return "t"
    if subtype == CASTLE_DOOR:
        return "d"
    if subtype == CASTLE_STAIRS:
        return "s"
    if subtype == CASTLE_VAULT:
        return "v"  # collides with village but only castle-internal style uses it
    short = {
        "plain": "P", "forest": "F", "mountain": "M", "river": "R",
        "castle": "C", "village": "v", "barracks": "b", "road": "r",
        "gate": "g",
    }
    return short.get(terrain, ".")


def _grid_to_chars(grid) -> List[str]:
    """Convert a 2D list of Tile rows into a list of char-strings."""
    rows: List[str] = []
    for row in grid:
        s = "".join(_tile_to_char(t.terrain, getattr(t, "subtype", None)) for t in row)
        rows.append(s)
    return rows


def _style_meta(style: str) -> Dict:
    cfg = MAP_STYLES[style]
    return {
        "display_cn": cfg["display_cn"],
        "biome": cfg["biome"],
        "mode": cfg["mode"],
    }


def build_one(style: str, size: int, players: int, seed: int) -> Dict:
    # P0-5 — use the new MapGenerator directly (not the legacy
    # generate_map wrapper) so chapter_* styles get the
    # connectivity-rescue + per-style weights + target_share wiring.
    gen = MapGenerator(
        size=size, player_count=players, style=style, seed=seed,
        use_clusters=True, use_rivers=True, use_roads=True,
        use_buildings=True,
    )
    grid = gen.generate()
    meta = _style_meta(style)
    base_id = f"{style}_{size}_{players}p"
    cfg = MAP_STYLES[style]
    return {
        "id": base_id,
        "name": f"{meta['display_cn']} · {size}×{size} · {players}人",
        "description": (
            f"P2.4 自动生成：{meta['display_cn']} 风格，{players} 人对战，"
            f"{size}×{size} 棋盘 (种子 #{seed})"
        ),
        "biome": meta["biome"],
        "size": size,
        "style": style,
        "mode": meta["mode"],
        "recommended_players": players,
        "seed": seed,
        "layout": _grid_to_chars(grid),
        # P0-5 — embed the style's full param set so the file is
        # self-describing and the fitness function can recompute S7
        # (target-share match) without needing the live MAP_STYLES.
        "objective": cfg.get("objective", "rout"),
        "category": cfg.get("category", "free_for_all"),
        "target_share": cfg.get("target_share", {}),
        "road_density": cfg.get("road_density", 0.5),
        "water_template": cfg.get("water_template", "river"),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for style, sizes in STYLE_SIZES.items():
        # 学长 2026-07-22:1vN style 锁定玩家数
        player_counts = STYLE_PLAYER_COUNTS.get(style, DEFAULT_PLAYER_COUNTS)
        for size in sizes:
            for players in player_counts:
                seed = 1000 + size * 17 + players * 7  # deterministic per (style,size,players)
                preset = build_one(style, size, players, seed)
                path = OUT_DIR / f"{preset['id']}.json"
                path.write_text(
                    json.dumps(preset, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"wrote {path}  ({size}x{size} / {players}p / {style})")
                written += 1
    print(f"\n=== {written} P2.4 presets written to {OUT_DIR}")


if __name__ == "__main__":
    main()
