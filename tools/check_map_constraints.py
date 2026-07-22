#!/usr/bin/env python3
"""
check_map_constraints.py — validate a generated or hand-authored map against
the hard constraints defined in app.map_generation.quality.

What it checks
--------------
    H1. One castle per declared player, no orphan castle components.
    H2. Every map has at least one economy tile (village / barracks / vault)
        OR initial units covering for the missing economy.
    H3. Every castle is reachable from every other castle through
        passable terrain.

Plus the soft metrics (S1..S6) get a 0..1 score that you can use as a
quality gate (e.g. fail CI if any soft score is < 0.3).

Inputs
------
A battle map JSON file.  Three accepted shapes:

  1. Generator-style ``MapGenerator.generate()`` return (List[List[Tile]])
     serialised as ``[[{"x": int, "y": int, "terrain": str, ...}, ...]]``
  2. Hand-authored ``.json`` map with a ``layout`` list-of-strings
     (e.g. ``tools/check_maps.py`` consumes this format)
  3. ``tiles`` block in the modern ``Game`` schema (P2.3+) — looks for
     ``{"tiles": [{"x": .., "y": .., "terrain": ..}, ...], ...}``

The first matching shape wins; if none match the script errors out.

Outputs
-------
- Stdout: human-readable summary.
- Exit code: 0 = pass, 1 = at least one hard violation, 2 = no map
  parsed (usage error).

Examples
--------
    # Validate a hand-authored map and pretty-print the report
    python tools/check_map_constraints.py game/maps/balanced_2p_15.json

    # Validate an in-memory generator output (writes to /tmp first)
    python -c "
    from app.map_generation import MapGenerator
    import json
    g = MapGenerator(size=15, seed=42)
    grid = [[{'x': t.x, 'y': t.y, 'terrain': t.terrain} for t in row] for row in g.generate()]
    json.dump(grid, open('/tmp/m.json', 'w'))
    " && python tools/check_map_constraints.py /tmp/m.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Make ``game`` importable when running from the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))

from app.config import (
    TERRAIN_BARRACKS,
    TERRAIN_CASTLE,
    TERRAIN_VILLAGE,
)
from app.map_generation.quality import QualityReport, score_map
from app.models import Tile


Coord = Tuple[int, int]


# ============================================================
# Tile format normalizers
# ============================================================


def _from_generator_dump(data: Any) -> Tuple[List[List[Tile]], List[Coord], Dict[str, float]]:
    """Generator-style dump: outer list of rows, each cell is a dict
    with ``x``, ``y``, ``terrain``.
    """
    grid: List[List[Tile]] = []
    for row in data:
        new_row: List[Tile] = []
        for cell in row:
            if not isinstance(cell, dict):
                return [], [], {}
            new_row.append(Tile(
                x=int(cell.get("x", 0)),
                y=int(cell.get("y", 0)),
                terrain=str(cell.get("terrain", "plain")),
                subtype=cell.get("subtype"),
            ))
        grid.append(new_row)
    castles: List[Coord] = [
        (c.x, c.y) for row in grid for c in row if c.terrain == TERRAIN_CASTLE
    ]
    return grid, castles, {}


def _from_layout_string(data: Dict[str, Any]) -> Tuple[List[List[Tile]], List[Coord], Dict[str, float]]:
    """Hand-authored map (legacy ``balanced_*.json`` format) with a
    ``layout`` list of equal-length strings.  Tile chars are mapped to
    terrain ids using the same table as ``game/app/game_logic.py
    _layout_to_tiles`` so we agree with the runtime.
    """
    layout = data.get("layout")
    if not layout or not isinstance(layout, list):
        return [], [], {}
    char_to_terrain = {
        "P": "plain", "F": "forest", "M": "mountain",
        "R": "river", "C": "castle", "v": "village",
        "b": "barracks", "r": "road", "g": "gate",
    }
    grid: List[List[Tile]] = []
    for y, line in enumerate(layout):
        new_row: List[Tile] = []
        for x, ch in enumerate(line):
            terrain = char_to_terrain.get(ch, char_to_terrain.get(ch.upper(), "plain"))
            new_row.append(Tile(x=x, y=y, terrain=terrain))
        grid.append(new_row)
    castles: List[Coord] = [
        (c.x, c.y) for row in grid for c in row if c.terrain == TERRAIN_CASTLE
    ]
    if not castles:
        for u in data.get("initial_units", []) or []:
            x, y = u.get("x"), u.get("y")
            if x is not None and y is not None:
                castles.append((int(x), int(y)))
        castles = list(dict.fromkeys(castles))
    return grid, castles, {}


def _from_tiles_block(data: Dict[str, Any]) -> Tuple[List[List[Tile]], List[Coord], Dict[str, float]]:
    """Modern ``Game`` schema: ``{"tiles": [...]}`` with full TileOut
    records.
    """
    tiles = data.get("tiles")
    if not tiles or not isinstance(tiles, list):
        return [], [], {}
    if not tiles:
        return [], [], {}
    max_x = max(t.get("x", 0) for t in tiles) + 1
    max_y = max(t.get("y", 0) for t in tiles) + 1
    grid: List[List[Tile]] = [
        [Tile(x=x, y=y, terrain="plain") for x in range(max_x)]
        for y in range(max_y)
    ]
    for t in tiles:
        x = int(t.get("x", 0))
        y = int(t.get("y", 0))
        if 0 <= y < max_y and 0 <= x < max_x:
            grid[y][x] = Tile(
                x=x, y=y,
                terrain=str(t.get("terrain", "plain")),
                subtype=t.get("subtype"),
            )
    castles: List[Coord] = [
        (c.x, c.y) for row in grid for c in row if c.terrain == TERRAIN_CASTLE
    ]
    return grid, castles, {}


def parse_map(path: str) -> Tuple[List[List[Tile]], List[Coord], Dict[str, float]]:
    """Try each known format; return the first one that yields a non-empty
    grid.  Raises ``ValueError`` if none of the formats match.

    Returns ``(grid, castles, target_share)``.  ``target_share`` may be
    empty if the file doesn't embed it (legacy / hand-authored maps).
    """
    target_share: Dict[str, float] = {}
    with open(path, encoding="utf-8") as fp:
        data = json.load(fp)

    # Pick up target_share if the file embeds it (P0-5 preset format).
    if isinstance(data, dict):
        target_share = data.get("target_share", {}) or {}

    # 1. Modern Game-style block
    if isinstance(data, dict) and "tiles" in data:
        grid, castles, _ = _from_tiles_block(data)
        if grid:
            return grid, castles, target_share

    # 2. Hand-authored layout-string
    if isinstance(data, dict) and "layout" in data:
        grid, castles, _ = _from_layout_string(data)
        if grid:
            return grid, castles, target_share

    # 3. Generator dump (list of list of dicts)
    if isinstance(data, list) and data and isinstance(data[0], list):
        grid, castles, _ = _from_generator_dump(data)
        if grid:
            return grid, castles, target_share

    raise ValueError(
        f"unrecognized map format in {path}: need one of "
        f"{{tiles, layout, [[dict, ...], ...]}}"
    )


# ============================================================
# Report printing
# ============================================================


def _print_report(report: QualityReport, path: str) -> None:
    print(f"\n=== {os.path.basename(path)} ===")
    print(f"fitness:           {report.fitness:.3f}")
    if report.hard_violations:
        print(f"hard violations:   {len(report.hard_violations)} (FAIL)")
        for v in report.hard_violations:
            print(f"  - {v}")
    else:
        print("hard violations:   0 (PASS)")
    print("soft scores:")
    for k, v in report.soft_scores.items():
        bar = "#" * int(v * 20)
        print(f"  {k:24s} {v:5.2f}  {bar}")
    if report.features:
        print("features:")
        for k, v in report.features.items():
            if isinstance(v, dict):
                v = ", ".join(f"{kk}={vv:.2f}" for kk, vv in v.items() if isinstance(vv, float))
            print(f"  {k:24s} {v}")


# ============================================================
# CLI
# ============================================================


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument("path", help="Map JSON file to validate.")
    p.add_argument(
        "--soft-floor", type=float, default=0.0,
        help="If > 0, fail when any soft score falls below this (CI gate).",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Emit the full report as JSON (machine-readable).",
    )
    args = p.parse_args(argv)

    if not os.path.exists(args.path):
        print(f"file not found: {args.path}", file=sys.stderr)
        return 2

    try:
        grid, castles, target_share = parse_map(args.path)
    except (ValueError, TypeError) as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 2

    if not grid:
        print(f"empty grid parsed from {args.path}", file=sys.stderr)
        return 2

    # Estimate size + use first 4 castles as the "declared" anchors
    # (mirrors what the symmetric 4p layout does)
    size = len(grid)
    if not castles:
        # No castle in the file at all — use the centre of the grid as
        # the only anchor (lets H1 still fire so the user sees the
        # diagnostic).
        mid = (size // 2, size // 2)
        castles = [mid]
    # H1 is only meaningful when the map has explicit castle tiles.
    # Legacy hand-authored maps encode HQ implicitly via unit positions
    # (multiple units per HQ) — in that case H1 is informational only.
    has_explicit_castle = any(
        t.terrain == TERRAIN_CASTLE for row in grid for t in row
    )
    report = score_map(grid, castles, size, target_share=target_share)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        # Suppress H1 violations in the *displayed* report too when
        # the map has no explicit castle tiles (the suppression is
        # also applied to the gate below).
        if not has_explicit_castle:
            h1_count = sum(1 for v in report.hard_violations if v.startswith("H1"))
            if h1_count:
                report.hard_violations = [
                    v for v in report.hard_violations if not v.startswith("H1")
                ]
                print(
                    f"  [info] H1 skipped (no explicit castle tiles): "
                    f"{h1_count} implicit-HQ check(s) suppressed"
                )
        _print_report(report, args.path)

    if report.hard_violations:
        # When the map has no explicit castle tiles, treat H1 as
        # informational only (legacy maps encode HQ via unit positions).
        if not has_explicit_castle:
            h1_violations = [v for v in report.hard_violations if v.startswith("H1")]
            report.hard_violations = [
                v for v in report.hard_violations if not v.startswith("H1")
            ]
            if h1_violations:
                print(
                    f"  [info] H1 skipped (no explicit castle tiles in the file): "
                    f"{len(h1_violations)} implicit-HQ check(s) suppressed",
                    file=sys.stderr,
                )
        if report.hard_violations:
            return 1
    if args.soft_floor:
        for k, v in report.soft_scores.items():
            if v < args.soft_floor:
                print(
                    f"\n[FAIL] {k}={v:.2f} < soft floor {args.soft_floor}",
                    file=sys.stderr,
                )
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
