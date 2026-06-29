"""Generate GBA-style 32x32 pixel art terrain tiles.

Outputs 10 PNG files to game/app/web/assets/tiles/:
  plain_v0.png, plain_v1.png
  forest_v0.png, forest_v1.png
  mountain_v0.png, mountain_v1.png
  river_v0.png, river_v1.png
  castle_v0.png, castle_v1.png

GBA palette: 16-bit era, chunky pixels, strong silhouettes, limited gradients.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("game/app/web/assets/tiles")
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 48  # matches CELL_MAX in style.css; tile fills cell at max size


# ============================================================
# GBA-inspired palette (limited but rich)
# ============================================================
class P:
    # Grass tones
    grass_l = (143, 203, 110)   # light grass
    grass_m = (107, 168, 74)
    grass_d = (74, 126, 50)     # grass shadow
    # Forest
    tree_top = (107, 184, 58)   # tree highlight
    tree_mid = (74, 140, 42)
    tree_dk = (45, 90, 26)      # tree shadow
    trunk = (92, 58, 26)
    trunk_dk = (61, 36, 16)
    # Mountain (barren — top-down, no green)
    mtn_edge = (180, 140, 60)    # foothills (yellow-brown)
    mtn_mid = (140, 90, 40)      # mid-elevation (orange-brown)
    mtn_peak = (90, 55, 25)      # peak center (dark brown)
    mtn_high = (220, 180, 100)   # ridge highlight
    # Mountain (snow-capped)
    snow_foot = (210, 170, 80)   # yellow foothills
    snow_mid = (180, 130, 80)    # tan mid
    snow_peak = (240, 235, 220)  # off-white snow ring
    snow_cap = (255, 255, 255)   # pure white peak
    # River
    water_l = (107, 200, 255)
    water_m = (74, 152, 213)
    water_d = (42, 108, 154)
    foam = (255, 255, 255)
    # Castle
    gold = (240, 200, 80)
    gold_d = (176, 136, 48)
    stone = (144, 144, 144)
    stone_d = (96, 96, 96)
    red = (200, 56, 56)
    red_d = (138, 32, 32)
    flag = (60, 60, 180)
    # Desert
    sand_l = (236, 208, 144)   # light sand
    sand_m = (210, 175, 100)   # mid sand (dune shadow)
    sand_d = (170, 130, 60)    # darker sand
    cactus = (60, 130, 60)     # cactus green
    cactus_d = (40, 90, 40)
    rock = (110, 90, 60)       # desert rock
    # Snow plain
    snow_l = (255, 255, 255)
    snow_shadow = (220, 232, 245)  # light blue shadow
    snow_d = (190, 210, 230)       # deeper blue shade
    snow_drift = (235, 245, 252)   # snow drift highlight
    # Mountain rocks (灰岩，参考图风格)
    rock_l = (210, 210, 210)   # light grey (sun-facing)
    rock_m = (170, 170, 170)   # mid grey (body)
    rock_d = (110, 110, 110)   # dark grey (shadow)
    # Common
    outline = (26, 26, 26)


# ============================================================
# Helpers
# ============================================================
def px(img: Image.Image, x: int, y: int, color: tuple[int, int, int]) -> None:
    """Paint a single pixel (in-place), clamped to image bounds."""
    if 0 <= x < SIZE and 0 <= y < SIZE:
        img.putpixel((x, y), color)


def rect(img: Image.Image, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px(img, x, y, color)


def triangle(img: Image.Image, x0: int, y0: int, x1: int, y1: int, x2: int, y2: int,
             fill: tuple[int, int, int], outline_color: tuple[int, int, int] | None = None) -> None:
    """Filled triangle via scanlines."""
    pts = sorted([(x0, y0), (x1, y1), (x2, y2)])
    (ax, ay), (bx, by), (cx, cy) = pts
    # Flat-top or pointy-top
    for y in range(min(ay, by, cy), max(ay, by, cy) + 1):
        if y < ay or y > max(by, cy):
            continue
        # Find x range at this y
        xs = []
        for (x_a, y_a), (x_b, y_b) in [((ax, ay), (bx, by)), ((ax, ay), (cx, cy)),
                                        ((bx, by), (cx, cy))]:
            if y_a == y_b:
                continue
            if min(y_a, y_b) <= y <= max(y_a, y_b):
                t = (y - y_a) / (y_b - y_a)
                xs.append(int(x_a + t * (x_b - x_a)))
        if len(xs) >= 2:
            lo, hi = min(xs), max(xs)
            rect(img, lo, y, hi, y, fill)
    if outline_color is not None:
        # outline (simple: just the 3 vertices connected)
        draw = ImageDraw.Draw(img)
        draw.polygon([(x0, y0), (x1, y1), (x2, y2)], outline=outline_color)


# ============================================================
# Plain (草地)
# ============================================================
def make_plain(variant: int) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), P.grass_l)
    rng = random.Random(0x100 + variant)
    # Grass tufts
    n = 6 if variant == 0 else 9
    for _ in range(n):
        x = rng.randint(2, SIZE - 3)
        y = rng.randint(2, SIZE - 3)
        # 2x1 darker tuft
        rect(img, x, y, x + 1, y, P.grass_d)
        rect(img, x, y + 1, x, y + 1, P.grass_m)
    if variant == 1:
        # Add a tiny white "flower" pixel cluster
        fx, fy = rng.randint(3, SIZE - 5), rng.randint(3, SIZE - 5)
        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            px(img, fx + dx, fy + dy, P.foam)
        px(img, fx, fy, P.gold)
    return img


# ============================================================
# Forest (森林)
# ============================================================
def draw_pine(img: Image.Image, cx: int, cy_base: int, total_height: int = 26,
               base_width: int = 13) -> None:
    """Draw a pine tree (松树) with 3 stacked triangular tiers + brown trunk.

    cx: horizontal center, cy_base: bottom y of tree (ground line).
    total_height: full tree height in pixels (including trunk).
    base_width: max half-width of bottom tier.
    """
    # Trunk (visible at base, 2-3 pixels wide, 3-4 tall)
    trunk_h = 4
    trunk_w = 2
    rect(img, cx - trunk_w // 2, cy_base - trunk_h, cx + trunk_w // 2, cy_base, P.trunk)
    rect(img, cx + trunk_w // 2 - 1, cy_base - trunk_h, cx + trunk_w // 2, cy_base, P.trunk_dk)

    # 3 tiers, drawn BOTTOM-to-TOP: widest first (at trunk), narrowest last (at top)
    tier_specs = [
        # (tier_height, half_width)
        (7,                                 base_width),  # BOTTOM tier (widest)
        (7,                                 6),            # MID tier
        (total_height - trunk_h - 14, 3),                 # TOP tier (pointiest)
    ]
    y_cursor = cy_base - trunk_h  # start from top of trunk, go up
    for tier_h, hw in tier_specs:
        y_bot = y_cursor
        y_top = y_bot - tier_h + 1
        # Fill triangle (apex at TOP, base at BOTTOM — correct pine shape)
        for y in range(y_top, y_bot + 1):
            if y < 0:
                continue
            t = (y - y_top) / max(1, y_bot - y_top)  # 0 at top (apex), 1 at bottom (base)
            w = int(hw * t)
            for x in range(cx - w, cx + w + 1):
                if not (0 <= x < SIZE):
                    continue
                # Two-tone shading: left half lighter, right half darker, center is medium
                if x < cx:
                    color = P.tree_mid
                elif x > cx:
                    color = P.tree_dk
                else:
                    color = P.tree_mid
                px(img, x, y, color)
        # Highlight stripe on leftmost edge of each tier (lighter green)
        for y in range(y_top + 1, y_bot):
            t = (y - y_top) / max(1, y_bot - y_top)
            w = int(hw * t)
            if cx - w >= 0:
                px(img, cx - w, y, P.tree_top)
        # Dark outline on rightmost edge
        for y in range(y_top + 1, y_bot):
            t = (y - y_top) / max(1, y_bot - y_top)
            w = int(hw * t)
            if cx + w < SIZE:
                px(img, cx + w, y, P.outline)
        y_cursor = y_top  # next tier sits on top of this one


ENV_BG = {
    # env -> (base_color, tuft_color) for tree/castle tiles
    "grass":  (P.grass_l, P.grass_d),
    "snow":   (P.snow_l,  P.snow_shadow),
    "desert": (P.sand_l,  P.sand_m),
}

# Tree positions per variant — drawn BACK→MIDDLE→FRONT order
# (cx, cy_base, total_height, base_width)
TREE_LAYOUTS = {
    0: [
        (15,  17, 22, 8),    # BACK: top-center, mid-tall, narrow (perspective)
        (25,  26, 12, 6),    # MIDDLE: right-bottom, short
        (7,   29, 28, 12),   # FRONT: left-bottom, tallest, widest
    ],
    1: [
        (16,  17, 22, 8),    # BACK: top-center, mirror
        (6,   26, 12, 6),    # MIDDLE: left-bottom
        (24,  29, 28, 12),   # FRONT: right-bottom, tallest
    ],
}


def make_forest(env: str, variant: int) -> Image.Image:
    bg, tuft_color = ENV_BG[env]
    img = Image.new("RGB", (SIZE, SIZE), bg)
    rng = random.Random(0x200 + variant)
    # Draw trees back→middle→front (later draws occlude earlier)
    for cx, cy, h, bw in TREE_LAYOUTS[variant]:
        draw_pine(img, cx, cy, total_height=h, base_width=bw)
    # A few ground texture dots
    for _ in range(3):
        x = rng.randint(0, SIZE - 1)
        y = rng.randint(0, SIZE - 1)
        rect(img, x, y, x + 1, y, tuft_color)
    return img


# ============================================================
# Mountain (山地) — 参考图风格：白色雪盖 + 灰岩主体 + 黄沙底
# ============================================================
def _draw_rocky_peak(img: Image.Image, peak_x: int, peak_y: int,
                     half_width: int, base_y: int,
                     rock_color: tuple[int, int, int],
                     snow_color: tuple[int, int, int] = None) -> None:
    """Draw a rocky peak: triangular body filled with rock_color,
    optionally capped with snow_color (top ~30%).
    Adds jagged ridge detail and shadow on right side.
    """
    peak_h = base_y - peak_y
    for y in range(peak_y, base_y + 1):
        if y < 0 or y >= SIZE:
            continue
        t = (y - peak_y) / max(1, peak_h)
        w = int(half_width * t)
        if w <= 0:
            continue
        # Determine if this y is in snow cap region
        snow_t = max(0, min(1, (peak_h * 0.35 - (y - peak_y)) / (peak_h * 0.35))) if snow_color else 0
        for x in range(peak_x - w, peak_x + w + 1):
            if not (0 <= x < SIZE):
                continue
            # Color: snow cap on top, rock body, with subtle ridge shading
            if snow_color and snow_t > 0 and (x - peak_x) ** 2 + ((y - peak_y) * 1.5) ** 2 < (half_width * snow_t * 0.7) ** 2:
                color = snow_color
            else:
                # Subtle ridge shading: center spine slightly darker, edges lighter
                if x == peak_x:
                    color = (rock_color[0] - 20, rock_color[1] - 20, rock_color[2] - 20)
                elif abs(x - peak_x) <= 1:
                    color = rock_color
                else:
                    color = rock_color
            px(img, x, y, color)


def make_mountain(variant: int) -> Image.Image:
    if variant == 0:
        # 参考图风格：黄沙底 + 多座灰岩峰 + 雪盖
        img = Image.new("RGB", (SIZE, SIZE), P.sand_l)  # 黄色沙地

        # 一些沙地纹理（黄色暗斑）
        for y in range(0, SIZE, 2):
            for x in range((y // 2) % 4, SIZE, 6):
                px(img, x, y, P.sand_m)

        # Back peak (smallest, narrowest, far right) — atmospheric perspective
        _draw_rocky_peak(img, peak_x=24, peak_y=10, half_width=6,
                          base_y=SIZE, rock_color=P.rock_m, snow_color=P.snow_cap)

        # Middle peak (medium, far left)
        _draw_rocky_peak(img, peak_x=8, peak_y=6, half_width=8,
                          base_y=SIZE, rock_color=P.rock_l, snow_color=P.snow_cap)

        # Front peak (tallest, center-right, dominant)
        _draw_rocky_peak(img, peak_x=17, peak_y=2, half_width=11,
                          base_y=SIZE, rock_color=P.rock_l, snow_color=P.snow_cap)

        # Subtle dark crevices between rocks (use rock_d color in shadow areas)
        # Crevice 1: between front and middle peaks
        for y in range(8, SIZE):
            px(img, 12, y, P.rock_d)
            px(img, 13, y, P.rock_d)
        # Crevice 2: between back and front
        for y in range(11, SIZE):
            px(img, 21, y, P.rock_d)
    else:
        # 雪山版：白底 + 全白雪山峰（白底白峰，主要靠阴影区分）
        img = Image.new("RGB", (SIZE, SIZE), P.snow_cap)

        # Back peak (light blue-gray)
        _draw_rocky_peak(img, peak_x=24, peak_y=10, half_width=6,
                          base_y=SIZE, rock_color=P.snow_shadow, snow_color=P.snow_cap)

        # Middle peak
        _draw_rocky_peak(img, peak_x=8, peak_y=6, half_width=8,
                          base_y=SIZE, rock_color=P.snow_shadow, snow_color=P.snow_cap)

        # Front peak (largest)
        _draw_rocky_peak(img, peak_x=17, peak_y=2, half_width=11,
                          base_y=SIZE, rock_color=P.snow_shadow, snow_color=P.snow_cap)

        # Crevices (deeper blue)
        for y in range(8, SIZE):
            px(img, 12, y, P.snow_d)
            px(img, 13, y, P.snow_d)
        for y in range(11, SIZE):
            px(img, 21, y, P.snow_d)
    return img


# ============================================================
# River (河流)
# ============================================================
def _draw_rock(img: Image.Image, cx: int, cy: int, w: int = 3, h: int = 2) -> None:
    """Draw a small rock: stone body + dark shadow on right/bottom + 1-2 highlight px on top-left."""
    # body
    rect(img, cx, cy, cx + w - 1, cy + h - 1, P.stone)
    # right edge shadow
    rect(img, cx + w, cy, cx + w, cy + h - 1, P.stone_d)
    # bottom edge shadow
    rect(img, cx, cy + h, cx + w, cy + h, P.stone_d)
    # top-left highlight
    px(img, cx, cy, P.mtn_high)
    if w >= 4:
        px(img, cx + 1, cy, P.mtn_high)


def _scatter_sparkles(img: Image.Image, rng: random.Random, n: int,
                       avoid: list[tuple[int, int, int, int]] | None = None) -> None:
    """Place n single-pixel foam sparkles at random positions, optionally
    avoiding rectangular regions (used so sparkles don't land on rocks)."""
    avoid = avoid or []
    placed: list[tuple[int, int]] = []
    tries = 0
    while len(placed) < n and tries < n * 8:
        tries += 1
        x = rng.randint(1, SIZE - 2)
        y = rng.randint(1, SIZE - 2)
        # skip if inside any avoid rect
        if any(ax <= x <= ax + aw - 1 and ay <= y <= ay + ah - 1
               for ax, ay, aw, ah in avoid):
            continue
        # skip if too close to an already placed sparkle
        if any(abs(x - px_) + abs(y - py_) < 4 for px_, py_ in placed):
            continue
        px(img, x, y, P.foam)
        placed.append((x, y))


def _scatter_shadow_dots(img: Image.Image, rng: random.Random, n: int) -> None:
    """Place n short 1-2px deep-water shadow dots (NOT rows)."""
    for _ in range(n):
        x = rng.randint(1, SIZE - 2)
        y = rng.randint(1, SIZE - 2)
        px(img, x, y, P.water_d)
        # sometimes a paired neighbor pixel to suggest depth (but NOT a row)
        if rng.random() < 0.3 and x + 1 < SIZE - 1:
            px(img, x + 1, y, P.water_d)


def make_river(variant: int) -> Image.Image:
    """River tiles — v1 style: clean water with scattered foam sparkles, a
    couple of small rocks, and a few deep-water shadow dots. No long
    horizontal lines, no diagonal streaks, no "speed-line" rows — those
    patterns tile badly because adjacent cells line up into obvious
    visual seams.
    """
    rng = random.Random(0x400 + variant)
    img = Image.new("RGB", (SIZE, SIZE), P.water_l)

    if variant == 0:
        # Mostly open water with a few sparkles + 1 rock cluster on the left
        _scatter_sparkles(img, rng, n=9)
        _draw_rock(img, cx=4, cy=18, w=4, h=2)
        _draw_rock(img, cx=20, cy=30, w=3, h=2)
        _scatter_shadow_dots(img, rng, n=6)
    elif variant == 1:
        # v1's exact look: 7 sparkles, 2 rocks, shadow ripple dots top & bottom
        for x, y in [(3, 5), (10, 8), (20, 4), (28, 12),
                     (5, 22), (15, 26), (24, 20)]:
            px(img, x, y, P.foam)
        for cx, cy in [(8, 14), (24, 18)]:
            _draw_rock(img, cx, cy, w=3, h=2)
        for x in range(2, SIZE, 4):
            px(img, x, 3, P.water_d)
            px(img, x + 2, 28, P.water_d)
    elif variant == 2:
        # Open water + 1 large rock cluster lower-right + lots of sparkles
        _draw_rock(img, cx=22, cy=18, w=5, h=3)
        _scatter_sparkles(img, rng, n=12,
                          avoid=[(22, 18, 6, 4)])  # keep sparkles off the rock
        _scatter_shadow_dots(img, rng, n=8)
    else:  # variant 3
        # 3 small scattered rocks + many sparkles + shadow dots
        for cx, cy in [(5, 6), (20, 14), (26, 24)]:
            _draw_rock(img, cx, cy, w=3, h=2)
        _scatter_sparkles(img, rng, n=11,
                          avoid=[(5, 6, 4, 3), (20, 14, 4, 3), (26, 24, 4, 3)])
        _scatter_shadow_dots(img, rng, n=10)
    return img


# ============================================================
# Castle (城堡) — sized to fill the full 48×48 tile
# (Previous version used 32×32-style coordinates and left ~20px of right
# margin empty, which read as a "background bar" when tiles were placed
# next to each other.)
# ============================================================
def draw_castle(img: Image.Image, style: int) -> None:
    # Stone base — fills nearly the whole tile width with a 4-px margin
    rect(img, 4, 16, 43, 39, P.stone)
    # Stone outline (top + left shadow strip)
    rect(img, 4, 16, 43, 16, P.stone_d)
    rect(img, 4, 16, 4, 39, P.stone_d)
    if style == 0:
        # Wide castle with 5 crenellations across the top (5 teeth spread
        # over x=5..40, so each tooth is ~4-5px wide with ~4-5px gaps).
        # Teeth sit on top of the wall at y=12..15 (above wall top y=16).
        tooth_w = 4
        gap = 4
        x = 5
        teeth = []
        while x + tooth_w <= 41:
            teeth.append(x)
            x += tooth_w + gap
        for x0 in teeth:
            rect(img, x0, 12, x0 + tooth_w - 1, 15, P.red)
            rect(img, x0, 15, x0 + tooth_w - 1, 15, P.red_d)
        # Door (dark) — centered (roughly x=21..26, height y=28..39)
        rect(img, 21, 28, 26, 39, P.outline)
        # Gold flag in center
        rect(img, 22, 4, 24, 12, P.flag)
        rect(img, 24, 4, 24, 12, P.outline)
        # small banner triangle
        px(img, 24, 4, P.gold)
        px(img, 25, 5, P.gold)
    else:
        # Tall tower style — tower body x=15..32, height y=8..39
        rect(img, 15, 8, 32, 39, P.stone)
        rect(img, 15, 8, 15, 39, P.stone_d)
        rect(img, 15, 8, 32, 8, P.stone_d)
        # Top crenellations (3 teeth across the tower top)
        for i in range(3):
            x0 = 16 + i * 6
            rect(img, x0, 4, x0 + 4, 7, P.red)
        # Window
        rect(img, 21, 16, 26, 21, P.outline)
        px(img, 23, 18, P.gold)
        # Door
        rect(img, 21, 30, 26, 39, P.outline)
        # Gold door highlight
        px(img, 21, 30, P.gold)
        px(img, 26, 30, P.gold)
    # Outlines — close the right + bottom edges of the wall so there's no
    # background seam at x=43 / y=39
    rect(img, 4, 39, 43, 40, P.outline)
    rect(img, 43, 16, 43, 39, P.outline)
    rect(img, 4, 16, 4, 39, P.outline)


def make_castle(env: str, variant: int) -> Image.Image:
    bg, _ = ENV_BG[env]
    img = Image.new("RGB", (SIZE, SIZE), bg)
    # Ground base strip at bottom
    if env == "grass":
        rect(img, 0, 26, SIZE - 1, SIZE - 1, P.grass_m)
    elif env == "desert":
        rect(img, 0, 26, SIZE - 1, SIZE - 1, P.sand_m)
    elif env == "snow":
        rect(img, 0, 26, SIZE - 1, SIZE - 1, P.snow_shadow)
    draw_castle(img, variant)
    # Snow on castle tops
    if env == "snow":
        # Add snow caps on red crenellation tops and wall edges
        # Find red crenellation rows (y=8-11 in make_castle) and overlay snow
        for x in range(5, 28):
            if 8 <= 11:
                for y in [8, 11]:
                    if 0 <= x < SIZE and 0 <= y < SIZE:
                        r, g, b = img.getpixel((x, y))
                        if r > 150 and g < 100:  # red crenellation
                            if y - 1 >= 0:
                                px(img, x, y - 1, P.snow_cap)
        # Snow on top edge of walls
        for x in range(5, 28):
            r, g, b = img.getpixel((x, 12))
            if r > 100 and g > 100 and b > 100:  # stone top
                px(img, x, 11, P.snow_cap)
    return img


# ============================================================
# Desert (沙漠)
# ============================================================
def make_desert(variant: int) -> Image.Image:
    rng = random.Random(0x500 + variant)
    img = Image.new("RGB", (SIZE, SIZE), P.sand_l)  # light sand base
    if variant == 0:
        # 沙丘起伏 + 1 棵小仙人掌
        # Wave-like dunes (curved shadow lines)
        for y in [8, 16, 24]:
            for x in range(0, SIZE):
                if (x // 3 + y // 4) % 2 == 0:
                    px(img, x, y, P.sand_m)
        # Small cactus in front-right
        cx, cy = 22, 22
        # Main cactus body
        rect(img, cx, cy - 4, cx + 1, cy, P.cactus)
        rect(img, cx + 1, cy - 4, cx + 1, cy, P.cactus_d)
        # Left arm
        rect(img, cx - 1, cy - 2, cx, cy - 2, P.cactus)
        rect(img, cx - 1, cy - 2, cx - 1, cy + 1, P.cactus)
        rect(img, cx - 1, cy + 1, cx, cy + 1, P.cactus)
        # Right arm
        rect(img, cx + 1, cy - 3, cx + 2, cy - 3, P.cactus)
        rect(img, cx + 2, cy - 3, cx + 2, cy, P.cactus)
        # Spines
        px(img, cx, cy - 4, P.outline)
        px(img, cx + 1, cy - 4, P.outline)
    else:
        # 风化岩石 + 沙丘 + 多反光
        for y in [6, 14, 22]:
            for x in range(0, SIZE):
                if (x + y) % 5 == 0:
                    px(img, x, y, P.sand_m)
                if (x + y) % 7 == 0:
                    px(img, x, y, P.sand_d)
        # 2 small rocks
        for (rx, ry) in [(7, 8), (24, 18)]:
            rect(img, rx, ry, rx + 3, ry + 2, P.rock)
            rect(img, rx + 3, ry, rx + 3, ry + 2, P.rock)
            rect(img, rx, ry + 2, rx + 3, ry + 2, P.rock)
            # highlight on top
            px(img, rx + 1, ry, P.sand_l)
            px(img, rx + 2, ry, P.sand_l)
        # 1 cactus in left-back
        cx, cy = 5, 14
        rect(img, cx, cy - 3, cx + 1, cy, P.cactus)
        rect(img, cx + 1, cy - 3, cx + 1, cy, P.cactus_d)
        rect(img, cx - 1, cy - 1, cx, cy - 1, P.cactus)
        rect(img, cx - 1, cy - 1, cx - 1, cy + 1, P.cactus)
        px(img, cx, cy - 3, P.outline)
    return img


# ============================================================
# Snow plain (雪原)
# ============================================================
def make_snow(variant: int) -> Image.Image:
    """Snow plain — clean white snowfield with subtle drift shading."""
    img = Image.new("RGB", (SIZE, SIZE), P.snow_l)
    if variant == 0:
        # 稀疏雪面波纹（淡蓝阴影，少而精）
        for y in range(SIZE - 1):  # skip last row to avoid background seam
            for x in range(SIZE):
                if (x + y) % 11 == 0 and (x // 3) % 2 == 0:
                    px(img, x, y, P.snow_shadow)
    else:
        # 雪堆 + 冰面反光
        for cx_d, cy_d, rd in [(10, 14, 9), (24, 22, 8)]:
            for y in range(max(0, cy_d - rd), min(SIZE, cy_d + 2)):
                for x in range(max(0, cx_d - rd), min(SIZE, cx_d + rd + 1)):
                    if (x - cx_d) ** 2 + (y - cy_d) ** 2 <= rd ** 2:
                        if y >= cy_d:
                            px(img, x, y, P.snow_shadow)
        # 冰面反光簇（小白点）
        for (sx, sy) in [(4, 4), (12, 8), (18, 16), (26, 6), (8, 26), (22, 28)]:
            px(img, sx, sy, P.snow_l)
            if sx + 1 < SIZE:
                px(img, sx + 1, sy, P.snow_l)
    return img


# ============================================================
# Driver
# ============================================================
def main() -> None:
    # Tiles that depend on environment (forest, castle get 3 envs each)
    ENV_AWARE = ("forest", "castle")
    ENVS = ("grass", "snow", "desert")
    VARIANTS_2 = ("plain", "mountain", "desert", "snow")
    VARIANTS_4 = ("river",)

    # Env-aware tiles (forest_grass_v0/v1, forest_snow_v0/v1, etc.)
    for name in ENV_AWARE:
        gen_fn = {"forest": make_forest, "castle": make_castle}[name]
        for env in ENVS:
            for v in range(2):
                tile = gen_fn(env, v)
                path = OUT / f"{name}_{env}_v{v}.png"
                tile.save(path)
                print(f"wrote {path}  ({tile.size[0]}x{tile.size[1]})")

    # Plain tiles (2 variants each, no env variation)
    for name in VARIANTS_2:
        gen_fn = {"plain": make_plain, "mountain": make_mountain,
                  "desert": make_desert, "snow": make_snow}[name]
        for v in range(2):
            tile = gen_fn(v)
            path = OUT / f"{name}_v{v}.png"
            tile.save(path)
            print(f"wrote {path}  ({tile.size[0]}x{tile.size[1]})")

    # River (4 variants)
    for v in range(4):
        tile = make_river(v)
        path = OUT / f"river_v{v}.png"
        tile.save(path)
        print(f"wrote {path}  ({tile.size[0]}x{tile.size[1]})")


if __name__ == "__main__":
    main()