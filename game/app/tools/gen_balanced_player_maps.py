"""
Build 3 hand-authored, balanced maps — one each for 2p / 3p / 4p.

Design rules (P2.6+ "map-driven HQ ownership"):

  * ``size`` declared as ``{width, height}`` (matches the new dict format
    used by the map editor + the procedural generator output).
  * ``recommended_players`` MUST equal the number of HQ tiles.
  * HQ tiles use the ``H`` character (the loader maps both ``C`` and
    ``H`` to ``TERRAIN_CASTLE`` — see ``game_logic._layout_to_tiles``).
  * HQ positions follow the convention adopted by the engine's
    row-major scan in ``routes.game._start_battle_internal``: the first
    HQ encountered in row-major order is assigned to seat 0 (red), the
    second to seat 1 (blue), etc.  We therefore place seat 0's HQ at
    the top-left, seat 1 at the top-right, seat 2 at the bottom-left,
    seat 3 at the bottom-right.
  * ``initial_units`` declares the 5 default units per HQ with their
    *colour already set* (so the engine's color-based dispatch lands
    each unit on the right player even if a seat is unused).
  * No more, no fewer castles than the player count — the whole point
    of this rewrite is to stop the engine from "owning" neutral
    castles or refusing to assign a castle to a player.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow this script to be run as `python game/app/tools/gen_balanced_player_maps.py`
# from the repo root, in which case `app.tools.render_map_preview` is not
# importable via the package path.  We pre-pend the `game/` directory to
# sys.path so the relative import below resolves to the same module that
# `python -m app.tools.render_map_preview` would load.
_REPO_ROOT_GUESS = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT_GUESS / "game"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# This file lives at <repo>/game/app/tools/gen_balanced_player_maps.py,
# so the maps directory is three levels up + "game/maps".
_MAPS_DIR = _REPO_ROOT / "game" / "maps"


# ---------------------------------------------------------------------
# Layout builders — programmatic so row widths are guaranteed correct.
# ---------------------------------------------------------------------


def _empty_grid(w: int, h: int) -> list[list[str]]:
    return [["P"] * w for _ in range(h)]


def _add_borders(grid, w: int, h: int) -> None:
    """Mountain border + forest second ring — keeps the action in the middle."""
    for x in range(w):
        grid[0][x] = "M"
        grid[h - 1][x] = "M"
    for y in (1, h - 2):
        for x in range(w):
            grid[y][x] = "F"


def _add_hq(grid, w: int, h: int, x: int, y: int) -> None:
    """Place an HQ and clear the 1-cell ring around it (no obstacles next to spawn)."""
    grid[y][x] = "H"
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (dx, dy) != (0, 0):
                if grid[ny][nx] not in ("M", "H"):
                    grid[ny][nx] = "P"


def _in_bounds(grid, x: int, y: int) -> bool:
    return 0 <= y < len(grid) and 0 <= x < len(grid[0])


def _add_village(grid, x: int, y: int) -> None:
    if _in_bounds(grid, x, y) and grid[y][x] not in ("M", "F", "H"):
        grid[y][x] = "v"


def _add_barracks(grid, x: int, y: int) -> None:
    if _in_bounds(grid, x, y) and grid[y][x] not in ("M", "F", "H"):
        grid[y][x] = "b"


def _add_mountain(grid, x: int, y: int) -> None:
    if _in_bounds(grid, x, y) and grid[y][x] not in ("H", "F"):
        grid[y][x] = "M"


def _add_forest(grid, x: int, y: int) -> None:
    if _in_bounds(grid, x, y) and grid[y][x] not in ("H", "M"):
        grid[y][x] = "F"


def _2p_map() -> tuple[list[str], list[tuple[int, int]]]:
    """15×15 — two HQs on the centre row, mirror-symmetric."""
    w, h = 15, 15
    g = _empty_grid(w, h)
    _add_borders(g, w, h)
    # Castles at (2, 7) and (12, 7) — seat 0 red, seat 1 blue
    _add_hq(g, w, h, 2, 7)
    _add_hq(g, w, h, 12, 7)
    # Villages & barracks near each HQ
    _add_village(g, 2, 4)
    _add_village(g, 12, 4)
    _add_village(g, 2, 10)
    _add_village(g, 12, 10)
    _add_barracks(g, 4, 7)
    _add_barracks(g, 10, 7)
    # Forest clusters around each HQ
    for x in (3, 4, 10, 11):
        _add_forest(g, x, 4)
        _add_forest(g, x, 10)
    # A mountain ridge just off-centre (decorative, doesn't block spawn)
    for y in (4, 5, 9, 10):
        _add_mountain(g, 7, y)
    # Forest belt between the two sides
    for x in range(5, 10):
        _add_forest(g, x, 2)
        _add_forest(g, x, 12)
    return ["".join(row) for row in g], [(2, 7), (12, 7)]


def _3p_map() -> tuple[list[str], list[tuple[int, int]]]:
    """15×15 — three HQs in a triangle: top-left, top-right, bottom-centre."""
    w, h = 15, 15
    g = _empty_grid(w, h)
    _add_borders(g, w, h)
    # Castles at (2, 2) red, (12, 2) blue, (7, 12) green
    _add_hq(g, w, h, 2, 2)
    _add_hq(g, w, h, 12, 2)
    _add_hq(g, w, h, 7, 12)
    # Each HQ gets a village and a barracks
    for cx, cy in ((2, 2), (12, 2)):
        _add_village(g, cx + 2, cy + 2)
        _add_barracks(g, cx - 2, cy + 2)
    _add_village(g, 7, 10)
    _add_barracks(g, 7, 14)  # near the southern border; keeps the
                              # southern HQ defended
    # Mountain ridge in the middle to give the layout some shape
    for y in range(4, 10):
        _add_mountain(g, 7, y)
    # Forest bands on each side
    for y in (3, 4):
        for x in range(4, 7):
            _add_forest(g, x, y)
        for x in range(8, 11):
            _add_forest(g, x, y)
    return ["".join(row) for row in g], [(2, 2), (12, 2), (7, 12)]


def _4p_map() -> tuple[list[str], list[tuple[int, int]]]:
    """20×20 — four HQs in the four corners. Symmetric."""
    w, h = 20, 20
    g = _empty_grid(w, h)
    _add_borders(g, w, h)
    # Castles: (2,2) red, (17,2) blue, (2,17) green, (17,17) yellow
    _add_hq(g, w, h, 2, 2)
    _add_hq(g, w, h, 17, 2)
    _add_hq(g, w, h, 2, 17)
    _add_hq(g, w, h, 17, 17)
    # Each HQ gets village + barracks
    for cx, cy in ((2, 2), (17, 2), (2, 17), (17, 17)):
        _add_village(g, cx + 2, cy + 2)
        _add_village(g, cx - 2, cy - 2)
        _add_barracks(g, cx + 3, cy + 2)
    # Central forest belt (split by rivers)
    for y in (8, 9, 10, 11):
        for x in range(5, 15):
            _add_forest(g, x, y)
    # Two diagonal mountain "lanes" leading from each corner toward the centre
    for i in range(4):
        # top-left to centre
        _add_mountain(g, 3 + i, 4 + i)
        # top-right to centre
        _add_mountain(g, 16 - i, 4 + i)
        # bottom-left to centre
        _add_mountain(g, 3 + i, 15 - i)
        # bottom-right to centre
        _add_mountain(g, 16 - i, 15 - i)
    return ["".join(row) for row in g], [(2, 2), (17, 2), (2, 17), (17, 17)]


# ---------------------------------------------------------------------
# initial_units — the canonical 5-unit roster around each HQ.
# ---------------------------------------------------------------------


def _initial_units_for(
    hq_positions: list[tuple[int, int]],
    hq_colours: list[str],
) -> list[dict]:
    """Generate the canonical 5-unit roster around each HQ.

    Same offsets used by ``_CLASSIC_OFFSETS`` in ``game_logic.py``:
        (0, 1) (1, 0) (1, 1) (2, 0) (0, 2)
    and the same composition: 2 swordsman / 1 archer / 1 knight / 1
    healer, with one of the swordsmen promoted to Lv2.
    """
    offsets = [(0, 1), (1, 0), (1, 1), (2, 0), (0, 2)]
    roster = [
        ("swordsman", 2),
        ("archer", 1),
        ("knight", 1),
        ("healer", 1),
    ]
    units: list[dict] = []
    for (cx, cy), colour in zip(hq_positions, hq_colours):
        idx = 0
        for unit_type, count in roster:
            for _ in range(count):
                dx, dy = offsets[idx % len(offsets)]
                units.append({
                    "x": cx + dx, "y": cy + dy,
                    "type": unit_type,
                    "color": colour,
                    "level": 1,
                })
                idx += 1
    return units


# (id, name, description, biome, w, h, builder, colours)
_MAPS: list[dict] = [
    {
        "id": "balanced_2p_15",
        "name": "2 人标准图",
        "description": "15×15，2 个 HQ 居中对阵。每玩家 5 兵 (1 Lv2 + 4 Lv1)。",
        "biome": "grass",
        "width": 15, "height": 15,
        "builder": _2p_map,
        "seat_colours": ["red", "blue"],
    },
    {
        "id": "balanced_3p_15",
        "name": "3 人三角图",
        "description": "15×15，3 个 HQ 三角布置（上 2 + 下 1）。",
        "biome": "grass",
        "width": 15, "height": 15,
        "builder": _3p_map,
        "seat_colours": ["red", "blue", "green"],
    },
    {
        "id": "balanced_4p_20",
        "name": "4 人四方图",
        "description": "20×20，4 个 HQ 四角布置。中央山区 / 森林 / 河流交错。",
        "biome": "grass",
        "width": 20, "height": 20,
        "builder": _4p_map,
        "seat_colours": ["red", "blue", "green", "yellow"],
    },
]


def main() -> int:
    _MAPS_DIR.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for spec in _MAPS:
        layout, castles = spec["builder"]()
        w, h = spec["width"], spec["height"]

        # Sanity: every row must be exactly `width` chars.
        bad_rows = [
            (i, len(r)) for i, r in enumerate(layout) if len(r) != w
        ]
        if bad_rows:
            print(f"ERROR {spec['id']}: rows have wrong width: {bad_rows}",
                  file=sys.stderr)
            return 1
        # Sanity: castle count == seat count.
        hq_count = sum(row.count("H") for row in layout)
        if hq_count != len(spec["seat_colours"]):
            print(f"ERROR {spec['id']}: {hq_count} H tiles but "
                  f"{len(spec['seat_colours'])} seats", file=sys.stderr)
            return 1
        # Sanity: the 'castles' list we hand back matches the row-major
        # order in the layout — important because the engine assigns
        # seats by row-major order.
        hq_in_layout = sorted(
            [(x, y) for y, row in enumerate(layout)
             for x, ch in enumerate(row) if ch == "H"],
            key=lambda p: (p[1], p[0]),
        )
        if hq_in_layout != castles:
            print(
                f"ERROR {spec['id']}: 'castles' {castles} disagrees with "
                f"row-major H positions {hq_in_layout}", file=sys.stderr,
            )
            return 1

        data = {
            "id": spec["id"],
            "name": spec["name"],
            "description": spec["description"],
            "biome": spec["biome"],
            "size": {"width": w, "height": h},
            "layout": layout,
            "initial_units": _initial_units_for(
                castles, spec["seat_colours"],
            ),
            "recommended_players": len(spec["seat_colours"]),
            "notes": (
                "P2.6+ — HQ tiles use 'H'; layout has EXACTLY "
                f"{len(spec['seat_colours'])} HQ tiles, one per seat."
            ),
        }
        out_path = _MAPS_DIR / f"{spec['id']}.json"
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"wrote {out_path.relative_to(_REPO_ROOT)}  "
            f"(H={hq_count}, units={len(data['initial_units'])})"
        )
        rendered.append(out_path)

    # P2.6+ — render a PNG preview of every map we just wrote so the
    # author can sanity-check the layout at a glance.  Skip if the
    # preview tool isn't importable (e.g. Pillow missing).
    if rendered:
        try:
            from app.tools.render_map_preview import render_to_path, MapSpec
            preview_dir = _REPO_ROOT / "map_previews"
            for json_path in rendered:
                spec = MapSpec.from_json_path(json_path)
                png_path = preview_dir / f"{spec.map_id}.png"
                render_to_path(spec, png_path)
                print(
                    f"  preview: {png_path.relative_to(_REPO_ROOT)}"
                )
        except ImportError as e:
            print(
                f"  (skipped preview: {e})", file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
