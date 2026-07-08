"""
Render a BattleBlitz map JSON as a PNG preview.

Why this exists
---------------
``tools/gen_balanced_player_maps.py`` (and any future map-authoring
tool) needs a quick visual sanity check.  The map is a 2-D grid of
single chars, so a human can read the source, but rendering it makes
it easier to spot balance problems at a glance (asymmetric castles,
unreachable terrain, decoration crowding out spawn tiles, …).

The output is intentionally dependency-light: only the standard
library + Pillow (already in the project).  No matplotlib / cairo /
network calls, so this script runs anywhere.

Layout
------
A single map is rendered to one PNG ``<map_id>.png`` under
``<out>/previews/`` (default ``./map_previews/`` next to the repo
root).  The PNG contains:

  * a top banner with the map id, name, recommended_players and size
  * the tile grid (terrain-coloured squares with subtle borders)
  * a side strip on the right with a colour-coded legend
  * a small overlay at the bottom listing how many HQ tiles, unit
    starting positions per colour, and whether the layout has the
    correct castle count

A second ``index.html`` is emitted into the same directory that
embeds all the PNGs in a grid — useful for quickly scanning the
whole map pack.

Usage
-----
    # render one map
    python -m app.tools.render_map_preview game/maps/balanced_2p_15.json

    # render every map under game/maps/ and refresh the index
    python -m app.tools.render_map_preview --all

    # custom output directory
    python -m app.tools.render_map_preview --all --out docs/img/maps

    # larger tiles for presentation
    python -m app.tools.render_map_preview game/maps/balanced_4p_20.json \\
        --tile-px 32 --with-grid
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

# Allow `python game/app/tools/render_map_preview.py …` from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_MAPS_DIR = _REPO_ROOT / "game" / "maps"
_DEFAULT_OUT = _REPO_ROOT / "map_previews"

# ---------------------------------------------------------------------------
# Visual config — keep all magic numbers here so designers can tweak
# them without hunting through the rendering code.
# ---------------------------------------------------------------------------

# (terrain, RGB) — chosen to match the existing in-game palette so
# the preview reads like the actual battlefield.
TERRAIN_COLOURS: dict[str, tuple[int, int, int]] = {
    "plain":        (200, 220, 160),  # light grass
    "forest":       (60, 130, 60),    # dark green
    "mountain":     (130, 110, 90),   # warm brown
    "snow_peak":    (220, 230, 240),  # silver/white
    "river":        (90, 150, 220),   # bright blue
    "castle":       (190, 160, 110),  # sandstone (will be overridden by
                                      # the HQ accent below)
    "village":      (240, 200, 100),  # straw yellow
    "barracks":     (180, 100, 60),   # brick red
    "road":         (210, 190, 150),  # dusty tan
    "gate":         (60, 60, 60),     # nearly black
    "castle_floor": (170, 140, 100),  # warm floor
    "castle_wall":  (80, 80, 80),     # dark wall
    "castle_throne":(180, 30, 30),    # crimson throne
    "castle_stairs":(200, 180, 140),  # lighter floor
    "castle_vault": (240, 200, 60),   # bright gold
    "castle_door":  (90, 50, 20),     # dark wood
}

# (color name, RGB) — one entry per seat.
COLOUR_COLOURS: dict[str, tuple[int, int, int]] = {
    "red":    (220, 60, 60),
    "blue":   (60, 100, 220),
    "green":  (60, 180, 90),
    "yellow": (230, 210, 60),
}

DEFAULT_TILE_PX = 28
GRID_LINE_RGB = (0, 0, 0, 60)
BANNER_BG = (245, 245, 240)
BANNER_FG = (40, 40, 40)
HQ_OUTLINE = (0, 0, 0)
HQ_OUTLINE_W = 2
LEGEND_BG = (250, 250, 250)
LEGEND_BORDER = (180, 180, 180)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MapSpec:
    """The minimal info we need to render a map preview."""

    map_id: str
    name: str
    description: str
    biome: str
    width: int
    height: int
    recommended_players: int
    layout: list[str]            # each row is len==width
    initial_units: list[dict]    # each {x, y, type, color, level}
    notes: Optional[str] = None

    @classmethod
    def from_json_path(cls, path: Path) -> "MapSpec":
        data = json.loads(path.read_text(encoding="utf-8"))
        size = data.get("size", 15)
        if isinstance(size, dict):
            w, h = int(size["width"]), int(size["height"])
        else:
            w = h = int(size)
        return cls(
            map_id=data.get("id", path.stem),
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            biome=data.get("biome", "grass"),
            width=w,
            height=h,
            recommended_players=int(data.get("recommended_players", 0)),
            layout=data["layout"],
            initial_units=data.get("initial_units", []),
            notes=data.get("notes"),
        )


# ---------------------------------------------------------------------------
# Terrain resolution
# ---------------------------------------------------------------------------

# The same single-char → (terrain[, subtype]) mapping the engine uses
# in ``game_logic._layout_to_tiles``.  Duplicated here so the script
# works without spinning up the FastAPI app / DB / settings layer.
_CHAR_TERRAIN: dict[str, str] = {
    "P": "plain",
    "F": "forest",
    "M": "mountain",
    "S": "snow_peak",
    "R": "river",
    "C": "castle",
    "H": "castle",  # P2.6+ alias
    "v": "village",
    "b": "barracks",
    "r": "road",
    "g": "gate",
    "$": "castle_vault",
}


def _terrain_at(spec: MapSpec, x: int, y: int) -> str:
    """Return the resolved terrain name (or 'plain' for unknown chars)."""
    if not (0 <= y < len(spec.layout)):
        return "plain"
    row = spec.layout[y]
    if not (0 <= x < len(row)):
        return "plain"
    ch = row[x]
    return _CHAR_TERRAIN.get(ch, "plain")


def _hq_positions(spec: MapSpec) -> list[tuple[int, int]]:
    """Row-major order; engine uses the same order to assign seats."""
    hq: list[tuple[int, int]] = []
    for y, row in enumerate(spec.layout):
        for x, ch in enumerate(row):
            if ch in ("C", "H"):
                hq.append((x, y))
    hq.sort(key=lambda p: (p[1], p[0]))
    return hq


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _seat_color_for_hq_index(idx: int) -> tuple[int, int, int]:
    """Match engine's seat→colour convention: red, blue, green, yellow."""
    return [
        COLOUR_COLOURS["red"],
        COLOUR_COLOURS["blue"],
        COLOUR_COLOURS["green"],
        COLOUR_COLOURS["yellow"],
    ][idx % 4]


def _load_font(size: int) -> ImageFont.ImageFont:
    """Try a few common Windows fonts, fall back to PIL's default."""
    for name in ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf",
                 "arial.ttf", "consolab.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    draw.text(xy, text, font=font, fill=fill)


def _render_grid(
    spec: MapSpec,
    tile_px: int,
    show_grid: bool,
    show_units: bool,
) -> Image.Image:
    """Render just the tile grid (no banner / legend)."""
    w_px = spec.width * tile_px
    h_px = spec.height * tile_px
    img = Image.new("RGBA", (w_px, h_px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    # 1) base terrain fill
    for y in range(spec.height):
        for x in range(spec.width):
            terrain = _terrain_at(spec, x, y)
            colour = TERRAIN_COLOURS.get(terrain, (200, 200, 200))
            x0, y0 = x * tile_px, y * tile_px
            x1, y1 = x0 + tile_px, y0 + tile_px
            draw.rectangle([x0, y0, x1, y1], fill=colour)

    # 2) optional thin grid lines (alpha-blended for legibility)
    if show_grid and tile_px >= 16:
        for x in range(spec.width + 1):
            draw.line(
                [(x * tile_px, 0), (x * tile_px, h_px)],
                fill=GRID_LINE_RGB, width=1,
            )
        for y in range(spec.height + 1):
            draw.line(
                [(0, y * tile_px), (w_px, y * tile_px)],
                fill=GRID_LINE_RGB, width=1,
            )

    # 3) HQ outlines + small seat number
    hq_font = _load_font(max(10, tile_px // 2))
    for seat, (hx, hy) in enumerate(_hq_positions(spec)):
        outline = _seat_color_for_hq_index(seat)
        x0, y0 = hx * tile_px, hy * tile_px
        x1, y1 = x0 + tile_px - 1, y0 + tile_px - 1
        for _ in range(HQ_OUTLINE_W):
            draw.rectangle(
                [x0, y0, x1, y1], outline=(*outline, 255),
            )
            x0 += 1; y0 += 1; x1 -= 1; y1 -= 1
        # tiny seat number in the centre
        _draw_text(
            draw,
            (hx * tile_px + tile_px // 4, hy * tile_px + tile_px // 8),
            str(seat), font=hq_font, fill=(0, 0, 0),
        )

    # 4) initial units — small filled circle in their colour
    if show_units and tile_px >= 12:
        for u in spec.initial_units:
            x, y = int(u["x"]), int(u["y"])
            colour = COLOUR_COLOURS.get(u.get("color", ""), (0, 0, 0))
            cx = x * tile_px + tile_px // 2
            cy = y * tile_px + tile_px // 2
            r = max(2, tile_px // 4)
            draw.ellipse(
                [(cx - r, cy - r), (cx + r, cy + r)],
                fill=(*colour, 220),
                outline=(0, 0, 0, 255),
            )

    return img


def _render_banner(spec: MapSpec, width_px: int) -> Image.Image:
    h = 80
    img = Image.new("RGBA", (width_px, h), BANNER_BG + (255,))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(22)
    sub_font = _load_font(14)
    _draw_text(
        draw, (12, 8),
        f"{spec.name}  ·  id={spec.map_id}",
        font=title_font, fill=BANNER_FG,
    )
    _draw_text(
        draw, (12, 38),
        f"size={spec.width}×{spec.height}  "
        f"recommended_players={spec.recommended_players}  "
        f"biome={spec.biome}  "
        f"hqs={len(_hq_positions(spec))}  "
        f"units={len(spec.initial_units)}",
        font=sub_font, fill=(80, 80, 80),
    )
    if spec.description:
        _draw_text(
            draw, (12, 58),
            spec.description[:100],
            font=sub_font, fill=(110, 110, 110),
        )
    draw.line([(0, h - 1), (width_px, h - 1)], fill=(180, 180, 180))
    return img


def _render_legend(width_px: int) -> Image.Image:
    """Terrain + colour key, drawn down the right side."""
    pad = 10
    line_h = 20
    terrain_rows = list(TERRAIN_COLOURS.items())
    # add a row for "HQ seat" and "starting unit"
    extra_rows = [
        ("HQ seat #0 (red)",    COLOUR_COLOURS["red"]),
        ("HQ seat #1 (blue)",   COLOUR_COLOURS["blue"]),
        ("HQ seat #2 (green)",  COLOUR_COLOURS["green"]),
        ("HQ seat #3 (yellow)", COLOUR_COLOURS["yellow"]),
    ]
    rows = terrain_rows + extra_rows
    h = pad * 2 + line_h * len(rows) + 30
    img = Image.new("RGBA", (width_px, h), LEGEND_BG + (255,))
    draw = ImageDraw.Draw(img)
    font = _load_font(12)
    bold = _load_font(14)
    _draw_text(draw, (pad, 4), "Legend", font=bold, fill=BANNER_FG)
    for i, (label, colour) in enumerate(rows):
        y = 26 + i * line_h
        draw.rectangle(
            [(pad, y), (pad + 14, y + 14)],
            fill=colour + (255,), outline=(80, 80, 80),
        )
        _draw_text(
            draw, (pad + 22, y + 1),
            label, font=font, fill=(60, 60, 60),
        )
    draw.rectangle(
        [(0, 0), (width_px - 1, h - 1)],
        outline=LEGEND_BORDER,
    )
    return img


def _stack_vertical(images: Iterable[Image.Image]) -> Image.Image:
    images = list(images)
    width = max(im.width for im in images)
    height = sum(im.height for im in images)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    y = 0
    for im in images:
        canvas.paste(im, (0, y), im if im.mode == "RGBA" else None)
        y += im.height
    return canvas


def _render_preview(
    spec: MapSpec,
    *,
    tile_px: int = DEFAULT_TILE_PX,
    show_grid: bool = True,
    show_units: bool = True,
) -> Image.Image:
    """Compose a full preview: banner on top, grid + side legend below."""
    grid = _render_grid(spec, tile_px, show_grid, show_units)
    legend = _render_legend(220)
    # place the legend down the right of the grid
    canvas_w = grid.width + legend.width
    canvas_h = max(grid.height, legend.height)
    combined = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    combined.paste(grid, (0, 0), grid)
    combined.paste(legend, (grid.width, 0), legend)
    banner = _render_banner(spec, canvas_w)
    return _stack_vertical([banner, combined])


# ---------------------------------------------------------------------------
# File I/O + CLI
# ---------------------------------------------------------------------------


def render_to_path(
    spec: MapSpec,
    out_path: Path,
    *,
    tile_px: int = DEFAULT_TILE_PX,
    show_grid: bool = True,
    show_units: bool = True,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = _render_preview(
        spec, tile_px=tile_px,
        show_grid=show_grid, show_units=show_units,
    )
    # The image is RGBA with a white background; converting to RGB
    # gives smaller PNGs and a clean white.
    img.convert("RGB").save(out_path, format="PNG", optimize=True)
    return out_path


def render_index(
    previews: list[tuple[MapSpec, Path]],
    out_path: Path,
) -> Path:
    """Emit a simple HTML index that links every preview."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for spec, png in previews:
        rel = png.relative_to(out_path.parent)
        rows.append(
            f"<figure>"
            f"<a href='{rel.as_posix()}'><img src='{rel.as_posix()}' "
            f"alt='{spec.map_id}' width='320'/></a>"
            f"<figcaption>"
            f"<strong>{spec.name}</strong> "
            f"<span class='meta'>id={spec.map_id} · "
            f"{spec.width}×{spec.height} · "
            f"rec={spec.recommended_players}p · "
            f"hqs={len(_hq_positions(spec))} · "
            f"units={len(spec.initial_units)}</span>"
            f"</figcaption></figure>"
        )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>BattleBlitz map previews</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;background:#f4f4f0;"
        "color:#222;margin:0;padding:24px;}"
        "h1{margin:0 0 16px;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,360px);"
        "gap:18px;}"
        "figure{margin:0;background:#fff;padding:10px;border-radius:6px;"
        "box-shadow:0 1px 4px rgba(0,0,0,.08);}"
        "figure img{display:block;width:100%;height:auto;border:1px solid #ddd;}"
        "figcaption{margin-top:8px;font-size:13px;}"
        ".meta{color:#666;font-size:12px;}"
        "</style></head><body>"
        f"<h1>BattleBlitz map previews ({len(previews)} maps)</h1>"
        f"<div class='grid'>{''.join(rows)}</div>"
        "</body></html>"
    )
    out_path.write_text(html, encoding="utf-8")
    return out_path


def iter_map_files(maps_dir: Path) -> list[Path]:
    return sorted(p for p in maps_dir.glob("*.json") if p.is_file())


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument(
        "paths", nargs="*", type=Path,
        help="Map JSON file(s) to render. Omit with --all.",
    )
    p.add_argument(
        "--all", action="store_true",
        help=f"Render every map under {_MAPS_DIR}",
    )
    p.add_argument(
        "--maps-dir", type=Path, default=_MAPS_DIR,
        help=f"Directory to scan when --all is set (default: {_MAPS_DIR})",
    )
    p.add_argument(
        "--out", type=Path, default=_DEFAULT_OUT,
        help=f"Output directory for PNGs + index.html "
             f"(default: {_DEFAULT_OUT})",
    )
    p.add_argument(
        "--tile-px", type=int, default=DEFAULT_TILE_PX,
        help=f"Pixel size of one map cell (default: {DEFAULT_TILE_PX})",
    )
    p.add_argument(
        "--with-grid", dest="show_grid", action="store_true", default=True,
        help="Draw thin grid lines between cells (default: on)",
    )
    p.add_argument(
        "--no-grid", dest="show_grid", action="store_false",
        help="Skip grid lines",
    )
    p.add_argument(
        "--no-units", dest="show_units", action="store_false", default=True,
        help="Don't draw initial-unit dots on top of the grid",
    )
    p.add_argument(
        "--no-index", dest="write_index", action="store_false", default=True,
        help="Skip the index.html emission",
    )
    args = p.parse_args(argv)

    if args.all:
        targets = iter_map_files(args.maps_dir)
    else:
        targets = list(args.paths)

    if not targets:
        p.error("no map files to render (pass paths or --all)")

    previews: list[tuple[MapSpec, Path]] = []
    for path in targets:
        spec = MapSpec.from_json_path(path)
        out_png = args.out / f"{spec.map_id}.png"
        render_to_path(
            spec, out_png,
            tile_px=args.tile_px,
            show_grid=args.show_grid,
            show_units=args.show_units,
        )
        print(f"  {out_png.relative_to(_REPO_ROOT)}")
        previews.append((spec, out_png))

    if args.write_index and len(previews) > 1:
        index_path = args.out / "index.html"
        render_index(previews, index_path)
        print(f"  {index_path.relative_to(_REPO_ROOT)} (index)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
