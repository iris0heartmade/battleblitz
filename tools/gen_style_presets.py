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
    MAP_STYLES, STYLE_CASTLE_INTERNAL, STYLE_GRASS_OUTER, STYLE_SNOW_OUTER,
    STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER, CASTLE_THRONE, CASTLE_DOOR,
    CASTLE_STAIRS, CASTLE_VAULT, CASTLE_WALL, CASTLE_FLOOR,
)
from app.game_logic import generate_map  # noqa: E402

OUT_DIR = GAME_DIR / "maps"

# Cross-product definition:
#   style → list of (size, num_players) tuples.
STYLE_SIZES: Dict[str, List[int]] = {
    STYLE_GRASS_OUTER:   [15, 20],
    STYLE_SNOW_OUTER:    [20, 25],
    STYLE_DESERT_OUTER:  [20],
    STYLE_COMPACT_OUTER: [15],
    STYLE_CASTLE_INTERNAL: [20, 25],
}

# Player counts we generate for each cell. The procedural generator
# only handles 2/3/4 players; we generate 2 and 4 to cover the most
# common modes (3 is identical 2p plus an extra slot — skipped for
# brevity, easy to add later).
PLAYER_COUNTS = [2, 4]


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
    grid = generate_map(seed=seed, num_castles=players, style=style, size=size)
    meta = _style_meta(style)
    base_id = f"{style}_{size}_{players}p"
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
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for style, sizes in STYLE_SIZES.items():
        for size in sizes:
            for players in PLAYER_COUNTS:
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
