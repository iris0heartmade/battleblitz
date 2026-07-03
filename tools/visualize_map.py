#!/usr/bin/env python3
"""
visualize_map.py — render a generated map to the terminal.

Prints an ASCII-art view of the map with terrain glyphs.  Useful for
spot-checking the new ``app.map_generation.MapGenerator`` output without
spinning up the full web app.

Usage:
    # Default 15×15 grass_outer map, seed=42
    python tools/visualize_map.py

    # Specific style / size / player count
    python tools/visualize_map.py --style snow_outer --size 20 --players 4

    # Save multiple side-by-side seeds
    python tools/visualize_map.py --count 3 --seeds 1 2 3 --size 15

Colours (optional, via ``--color``): plain=green, forest=dark green,
mountain=gray, river=cyan, road=yellow, castle=red, village/blue,
barracks/magenta.  Falls back to plain ASCII when ``--no-color`` is set
or stdout is not a TTY.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, List

# Make the ``game`` package importable when running from the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))

from app.map_generation import MapGenerator  # noqa: E402
from app.models import Tile  # noqa: E402

GLYPHS = {
    "plain": ".",
    "forest": "F",
    "mountain": "M",
    "river": "~",
    "road": ",",
    "castle": "C",
    "castle_floor": "f",
    "castle_wall": "W",
    "castle_door": "D",
    "castle_throne": "T",
    "castle_stairs": "S",
    "castle_vault": "V",
    "village": "V",
    "barracks": "B",
    "snow_peak": "^",
    "gate": "#",
}

# ANSI colour palette — keyed by primary terrain (sub-features inherit
# their parent's hue).
COLORS = {
    "plain": "\033[32m",       # green
    "forest": "\033[32;1m",    # bold green
    "mountain": "\033[90m",    # gray
    "river": "\033[36m",       # cyan
    "road": "\033[33m",        # yellow
    "castle": "\033[31;1m",    # bold red
    "castle_floor": "\033[31m",
    "castle_wall": "\033[30;1m",
    "castle_door": "\033[33;1m",
    "castle_throne": "\033[35;1m",
    "castle_stairs": "\033[36m",
    "castle_vault": "\033[33m",
    "village": "\033[34m",
    "barracks": "\033[35m",
    "snow_peak": "\033[37;1m",
    "gate": "\033[30;1m",
}
RESET = "\033[0m"


def _glyph(tile: Tile) -> str:
    sub = getattr(tile, "subtype", None)
    if sub and sub in GLYPHS:
        return GLYPHS[sub]
    return GLYPHS.get(tile.terrain, "?")


def _color(tile: Tile) -> str:
    sub = getattr(tile, "subtype", None)
    if sub and sub in COLORS:
        return COLORS[sub]
    return COLORS.get(tile.terrain, "")


def render(grid: List[List[Tile]], use_color: bool = True) -> str:
    lines: List[str] = []
    if use_color:
        lines.append("    " + "".join(str(x % 10) for x in range(len(grid[0]))))
    else:
        lines.append("    " + "".join(str(x % 10) for x in range(len(grid[0]))))
    for y, row in enumerate(grid):
        prefix = f"{y:3d} "
        body = "".join(
            f"{_color(t)}{_glyph(t)}{RESET}" if use_color else _glyph(t)
            for t in row
        )
        lines.append(prefix + body)
    return "\n".join(lines)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--style", default="grass_outer")
    p.add_argument("--size", type=int, default=15)
    p.add_argument("--players", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--count", type=int, default=1,
                   help="how many side-by-side maps to render")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="explicit seeds (overrides --count)")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--rich", action="store_true",
                   help="use the rich (clustered, river, road) generator")
    return p.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    use_color = (not args.no_color) and sys.stdout.isatty()

    seeds = args.seeds or [args.seed + i for i in range(args.count)]
    for i, seed in enumerate(seeds):
        gen = MapGenerator(
            size=args.size,
            player_count=args.players,
            style=args.style,
            seed=seed,
            use_clusters=args.rich,
            use_rivers=args.rich,
            use_roads=args.rich,
            use_buildings=args.rich,
        )
        grid = gen.generate()
        print(f"=== seed={seed} style={args.style} size={args.size} "
              f"players={args.players} ===")
        print(render(grid, use_color=use_color))
        if i != len(seeds) - 1:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))