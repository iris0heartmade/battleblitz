"""
从 BASE_CLASSIC.png 裁剪 6 个职业图标 → assets/classic/。

流程:
  1. 粗裁（不含外框线）
  2. 二值 mask: 非白 → 前景
  3. 只保留最大连通域（角色本体）
  4. 闭运算填内部小孔
  5. 轮廓外扩 + 高斯羽化
  6. 用羽化 mask 合成 RGBA 输出
"""

from PIL import Image, ImageFilter
from pathlib import Path
from collections import deque

SRC = Path(__file__).resolve().parent.parent / "game/app/web/assets/_unused/BASE_CLASSIC.png"
OUT_DIR = Path(__file__).resolve().parent.parent / "game/app/web/assets/classic"

BOXES = [
    (30,  347,  "swordsman"),
    (376, 693,  "heavy_armor"),
    (723, 1035, "knight"),
    (1064,1375, "healer"),
    (1404,1723, "archer"),
    (1753,2069, "warlock"),
]
ROW_TOP, ROW_BOTTOM = 166, 537

BG_THRESH = 235
EDGE_TRIM = 5    # 先腐蚀边缘 N px，洗掉紧贴裁剪边的抗锯齿环
BRIDGE_R = 10      # 桥接半径: 先膨胀再取最大连通域，裂片自动合并
DILATE_R = 4
FEATHER_R = 8


def _make_mask(img: Image.Image) -> Image.Image:
    m = Image.new("L", img.size, 0)
    pi, po = img.load(), m.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = pi[x, y][:3]
            if r < BG_THRESH or g < BG_THRESH or b < BG_THRESH:
                po[x, y] = 255
    return m


def _keep_largest(bw: Image.Image) -> Image.Image:
    w, h = bw.size
    px = bw.load()
    vis = [[False] * w for _ in range(h)]
    comps = []
    for y in range(h):
        for x in range(w):
            if vis[y][x] or px[x, y] == 0:
                continue
            c = []
            q = deque([(x, y)])
            vis[y][x] = True
            while q:
                cx, cy = q.popleft()
                c.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not vis[ny][nx] and px[nx, ny] > 0:
                        vis[ny][nx] = True
                        q.append((nx, ny))
            comps.append(c)
    if not comps:
        return bw
    big = max(comps, key=len)
    out = Image.new("L", bw.size, 0)
    po = out.load()
    for x, y in big:
        po[x, y] = 255
    return out


def _close(bw: Image.Image, k: int) -> Image.Image:
    if k < 3:
        return bw
    return bw.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))


def _expand_feather(bw: Image.Image, dr: int, fr: int) -> Image.Image:
    if dr > 0:
        bw = bw.filter(ImageFilter.MaxFilter(dr * 2 + 1))
    if fr > 0:
        bw = bw.filter(ImageFilter.GaussianBlur(fr))
    return bw


def _remove_tiny_islands(rgba: Image.Image, min_px: int = 20) -> Image.Image:
    """移除 RGBA 中所有像素数 < min_px 的独立不透明连通域（鬼影碎片）。"""
    w, h = rgba.size
    px = rgba.load()
    visited = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if visited[y][x] or px[x, y][3] < 10:
                continue
            comp = []
            q = deque([(x, y)])
            visited[y][x] = True
            while q:
                cx, cy = q.popleft()
                comp.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and px[nx, ny][3] >= 10:
                        visited[ny][nx] = True
                        q.append((nx, ny))
            if len(comp) < min_px:
                for cx, cy in comp:
                    r, g, b, _ = px[cx, cy]
                    px[cx, cy] = (r, g, b, 0)
    return rgba


def _suppress_white_halo(rgba: Image.Image, raw: Image.Image) -> Image.Image:
    """羽化边缘若落在原图白色背景上 → 降低 alpha 直至消失。"""
    px_rgba, px_raw = rgba.load(), raw.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px_rgba[x, y]
            if a == 0:
                continue
            rr, gg, bb = px_raw[x, y][:3]
            # 原图是近白 且 alpha 不饱和 → 白色光晕，抹掉
            if rr > BG_THRESH and gg > BG_THRESH and bb > BG_THRESH and a < 192:
                px_rgba[x, y] = (r, g, b, 0)
    return rgba


def process(src: Image.Image, left: int, right: int, tid: str):
    raw = src.crop((left, ROW_TOP, right + 1, ROW_BOTTOM + 1))
    m = _make_mask(raw)
    if EDGE_TRIM > 0:
        m = m.filter(ImageFilter.MinFilter(EDGE_TRIM * 2 + 1))
    m = m.filter(ImageFilter.MaxFilter(BRIDGE_R * 2 + 1))
    m = _keep_largest(m)
    m = _expand_feather(m, DILATE_R, FEATHER_R)
    rgba = raw.convert("RGBA")
    rgba.putalpha(m)
    rgba = _suppress_white_halo(rgba, raw)
    rgba = _remove_tiny_islands(rgba, min_px=20)
    bb = rgba.getbbox()
    if bb:
        rgba = rgba.crop(bb)
    rgba.save(OUT_DIR / f"{tid}.png", optimize=True)
    print(f"  ✓ {tid}.png  {rgba.size}")


def main():
    src = Image.open(SRC)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for l, r, tid in BOXES:
        process(src, l, r, tid)
    print(f"\nDone → {OUT_DIR}/")


if __name__ == "__main__":
    main()
