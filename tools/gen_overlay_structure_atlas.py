from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


TILE = 48
OUT = Path("game/app/web/assets/tiles/overlays")
OUT.mkdir(parents=True, exist_ok=True)


class C:
    outline = (24, 24, 28, 255)
    shadow = (0, 0, 0, 90)
    rock_grass = ((173, 174, 166, 255), (120, 122, 116, 255), (88, 90, 86, 255))
    rock_snow = ((240, 244, 252, 255), (190, 210, 235, 255), (126, 148, 176, 255))
    rock_desert = ((190, 150, 102, 255), (150, 112, 72, 255), (110, 76, 44, 255))
    road_grass = ((176, 134, 88, 255), (146, 106, 64, 255), (112, 76, 48, 255))
    road_snow = ((170, 144, 124, 255), (140, 118, 98, 255), (110, 90, 74, 255))
    road_desert = ((198, 154, 92, 255), (170, 128, 70, 255), (132, 92, 46, 255))
    stone = ((168, 172, 182, 255), (126, 132, 145, 255), (86, 92, 108, 255))
    wood = ((143, 93, 52, 255), (112, 68, 38, 255), (76, 44, 24, 255))
    roof_red = ((205, 76, 72, 255), (164, 52, 48, 255), (110, 30, 28, 255))
    roof_blue = ((86, 122, 196, 255), (60, 92, 156, 255), (38, 58, 110, 255))
    roof_snow = ((235, 242, 248, 255), (190, 205, 224, 255), (146, 160, 184, 255))
    tent = ((192, 150, 92, 255), (148, 110, 64, 255), (100, 70, 40, 255))
    gold = (236, 196, 82, 255)


def new_tile() -> Image.Image:
    return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))


def paste_cell(sheet: Image.Image, tile: Image.Image, index: int, cols: int) -> None:
    x = (index % cols) * TILE
    y = (index // cols) * TILE
    sheet.alpha_composite(tile, (x, y))


def jitter_points(points: list[tuple[int, int]], dx: int = 0, dy: int = 0) -> list[tuple[int, int]]:
    return [(x + dx, y + dy) for x, y in points]


def draw_mountain(shape: str, biome: str) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    light, mid, dark = {
        "grass": C.rock_grass,
        "snow": C.rock_snow,
        "desert": C.rock_desert,
    }[biome]
    if shape == "peak":
        polys = [
            [(5, 42), (18, 20), (28, 38)],
            [(18, 42), (28, 10), (43, 42)],
        ]
    elif shape == "ridge_h":
        polys = [
            [(0, 40), (12, 22), (24, 28), (36, 16), (47, 38), (47, 47), (0, 47)],
        ]
    elif shape == "ridge_v":
        polys = [
            [(8, 47), (18, 34), (15, 22), (24, 8), (38, 18), (31, 30), (42, 47)],
        ]
    elif shape == "corner_ne":
        polys = [
            [(10, 47), (18, 30), (28, 20), (47, 8), (47, 47)],
        ]
    elif shape == "corner_sw":
        polys = [
            [(0, 30), (10, 18), (24, 8), (34, 20), (18, 34), (8, 47), (0, 47)],
        ]
    else:
        polys = [[(4, 47), (16, 24), (24, 28), (28, 20), (40, 32), (44, 47)]]
    for poly in polys:
        draw.polygon(poly, fill=mid)
        draw.line(poly + [poly[0]], fill=C.outline, width=1)
        hi = [(poly[0][0] + 2, poly[0][1] - 2), (poly[1][0], poly[1][1] + 1), (poly[2][0] - 2, poly[2][1] + 2)]
        draw.polygon(hi, fill=light)
    for x in range(6, TILE - 6, 5):
        y = 34 + (x % 3)
        draw.point((x, y), fill=dark)
    if biome == "snow":
        draw.polygon([(17, 18), (28, 9), (34, 19), (25, 24)], fill=C.roof_snow[0])
    return img


def draw_path(kind: str, biome: str, stone: bool = False) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    light, mid, dark = (C.stone if stone else {
        "grass": C.road_grass,
        "snow": C.road_snow,
        "desert": C.road_desert,
    }[biome])
    width = 12 if stone else 10

    def road_line(points: list[tuple[int, int]]) -> None:
        draw.line(points, fill=dark, width=width + 4, joint="curve")
        draw.line(points, fill=mid, width=width, joint="curve")
        draw.line(points, fill=light, width=max(3, width // 3), joint="curve")
        for px, py in points[1:-1]:
            draw.ellipse((px - 1, py - 1, px + 1, py + 1), fill=dark)

    if kind == "h":
        road_line([(0, 24), (47, 24)])
    elif kind == "v":
        road_line([(24, 0), (24, 47)])
    elif kind == "bend_ne":
        road_line([(24, 47), (24, 24), (47, 24)])
    elif kind == "bend_sw":
        road_line([(0, 24), (24, 24), (24, 47)])
    elif kind == "t_n":
        road_line([(0, 24), (47, 24)])
        road_line([(24, 0), (24, 24)])
    elif kind == "cross":
        road_line([(0, 24), (47, 24)])
        road_line([(24, 0), (24, 47)])
    elif kind == "fork":
        road_line([(24, 47), (24, 28), (10, 14)])
        road_line([(24, 28), (38, 12)])
    else:
        road_line([(8, 24), (24, 24), (40, 30)])
    return img


def draw_bridge(kind: str, biome: str, material: str) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    light, mid, dark = C.wood if material == "wood" else C.stone
    if biome == "snow":
        cap = C.roof_snow[0]
    elif biome == "desert":
        cap = (214, 182, 126, 255)
    else:
        cap = (170, 148, 92, 255)

    if kind == "h":
        body = (4, 16, 43, 31)
        rail1 = [(4, 16), (43, 16)]
        rail2 = [(4, 31), (43, 31)]
        posts = [(8, 17), (18, 17), (28, 17), (38, 17)]
        plank_vertical = True
    elif kind == "v":
        body = (16, 4, 31, 43)
        rail1 = [(16, 4), (16, 43)]
        rail2 = [(31, 4), (31, 43)]
        posts = [(17, 8), (17, 18), (17, 28), (17, 38)]
        plank_vertical = False
    else:
        body = (6, 18, 41, 29)
        rail1 = [(6, 18), (41, 18)]
        rail2 = [(6, 29), (41, 29)]
        posts = [(10, 19), (20, 19), (30, 19)]
        plank_vertical = True

    draw.rounded_rectangle(body, radius=2, fill=mid, outline=C.outline)
    draw.line(rail1, fill=dark, width=2)
    draw.line(rail2, fill=dark, width=2)
    if plank_vertical:
        for x in range(body[0] + 3, body[2], 6):
            draw.line([(x, body[1] + 2), (x, body[3] - 2)], fill=light, width=2)
    else:
        for y in range(body[1] + 3, body[3], 6):
            draw.line([(body[0] + 2, y), (body[2] - 2, y)], fill=light, width=2)
    for x, y in posts:
        draw.rectangle((x, y, x + 2, y + 11), fill=dark)
        draw.point((x + 1, y + 1), fill=cap)
    if biome == "snow":
        draw.line([rail1[0], rail1[1]], fill=cap, width=1)
    return img


def draw_castle(biome: str, variant: str) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    roof = {"grass": C.roof_red, "snow": C.roof_snow, "desert": C.roof_blue}[biome]
    light, mid, dark = C.stone
    base = (6, 16, 41, 41)
    draw.rounded_rectangle(base, radius=2, fill=mid, outline=C.outline)
    for x in range(8, 40, 6):
        draw.rectangle((x, 12, x + 3, 16), fill=dark)
    if variant == "gate":
        draw.rectangle((19, 27, 28, 41), fill=dark, outline=C.outline)
        draw.arc((16, 19, 31, 34), 180, 360, fill=dark, width=2)
    else:
        draw.rectangle((14, 10, 33, 24), fill=light, outline=C.outline)
        draw.polygon([(12, 14), (24, 4), (35, 14)], fill=roof[1], outline=C.outline)
        draw.polygon([(16, 19), (24, 10), (31, 19)], fill=roof[0])
        draw.rectangle((20, 26, 27, 41), fill=dark)
    if biome == "desert":
        draw.line([(9, 34), (14, 34)], fill=C.gold, width=2)
    elif biome == "snow":
        draw.line([(9, 17), (39, 17)], fill=C.roof_snow[0], width=2)
    return img


def draw_village(biome: str, variant: str) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    roofs = {
        "grass": C.roof_red,
        "snow": C.roof_snow,
        "desert": C.tent,
    }[biome]
    huts = [
        ((6, 22, 18, 34), (4, 22), (12, 12), (20, 22)),
        ((22, 18, 38, 32), (20, 18), (30, 8), (40, 18)),
    ]
    if variant == "dense":
        huts.append(((15, 28, 29, 40), (13, 28), (22, 19), (31, 28)))
    for box, p1, p2, p3 in huts:
        draw.rectangle(box, fill=C.stone[0], outline=C.outline)
        draw.polygon([p1, p2, p3], fill=roofs[1], outline=C.outline)
        draw.polygon([(p1[0] + 2, p1[1]), p2, (p3[0] - 3, p3[1])], fill=roofs[0])
        cx = (box[0] + box[2]) // 2
        draw.rectangle((cx - 1, box[1] + 7, cx + 1, box[3]), fill=C.wood[2])
    return img


def draw_outpost(biome: str, variant: str) -> Image.Image:
    img = new_tile()
    draw = ImageDraw.Draw(img)
    tent = C.tent
    pole_color = C.wood[2]
    if variant == "tent":
        draw.polygon([(6, 31), (16, 14), (26, 31)], fill=tent[1], outline=C.outline)
        draw.polygon([(22, 34), (33, 15), (43, 34)], fill=tent[0], outline=C.outline)
        draw.line([(16, 14), (16, 33)], fill=pole_color, width=1)
        draw.line([(33, 15), (33, 35)], fill=pole_color, width=1)
    else:
        draw.rectangle((8, 18, 38, 38), fill=C.wood[1], outline=C.outline)
        draw.polygon([(6, 20), (23, 8), (40, 20)], fill=C.roof_blue[1], outline=C.outline)
        for x in range(12, 38, 8):
            draw.line([(x, 20), (x, 38)], fill=C.wood[2], width=2)
    draw.line([(36, 8), (36, 24)], fill=pole_color, width=2)
    draw.polygon([(36, 8), (44, 11), (36, 15)], fill=C.roof_red[0], outline=C.outline)
    if biome == "snow":
        draw.line([(10, 31), (25, 31)], fill=C.roof_snow[0], width=2)
    elif biome == "desert":
        draw.point((12, 36), fill=C.gold)
        draw.point((15, 34), fill=C.gold)
    return img


def make_sheet(cells: list[Image.Image], cols: int) -> Image.Image:
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * TILE, rows * TILE), (0, 0, 0, 0))
    for i, tile in enumerate(cells):
        paste_cell(sheet, tile, i, cols)
    return sheet


def build_mountain_road_bridge() -> Image.Image:
    cells: list[Image.Image] = []
    for biome in ("grass", "snow", "desert"):
        for shape in ("peak", "ridge_h", "ridge_v", "corner_ne", "corner_sw"):
            cells.append(draw_mountain(shape, biome))
    for biome in ("grass", "snow", "desert"):
        for kind in ("h", "v", "bend_ne", "bend_sw", "t_n", "cross", "fork"):
            cells.append(draw_path(kind, biome, stone=False))
    for biome in ("grass", "snow", "desert"):
        cells.append(draw_path("h", biome, stone=True))
        cells.append(draw_path("cross", biome, stone=True))
    for biome in ("grass", "snow", "desert"):
        for material in ("wood", "stone"):
            for kind in ("h", "v"):
                cells.append(draw_bridge(kind, biome, material))
    return make_sheet(cells, cols=8)


def build_castle_village_outpost() -> Image.Image:
    cells: list[Image.Image] = []
    for biome in ("grass", "snow", "desert"):
        for variant in ("keep", "gate"):
            cells.append(draw_castle(biome, variant))
    for biome in ("grass", "snow", "desert"):
        for variant in ("sparse", "dense"):
            cells.append(draw_village(biome, variant))
    for biome in ("grass", "snow", "desert"):
        for variant in ("tent", "fort"):
            cells.append(draw_outpost(biome, variant))
    return make_sheet(cells, cols=6)


def main() -> None:
    mrb = build_mountain_road_bridge()
    cvo = build_castle_village_outpost()
    mrb.save(OUT / "overlay_mountain_road_bridge_atlas.png")
    cvo.save(OUT / "overlay_castle_village_outpost_atlas.png")
    print(OUT / "overlay_mountain_road_bridge_atlas.png")
    print(OUT / "overlay_castle_village_outpost_atlas.png")


if __name__ == "__main__":
    main()
