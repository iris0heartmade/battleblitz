#!/usr/bin/env python3
"""
label_map_regions.py — 【极简模式】地图标注向导

设计思路
--------
用户不需要理解"拖框"、"选择区域"。每一步只做一件事:

    1. 屏幕中央显示一张 64x64 的小切图(从原图随机切出)
    2. 下面 9 个大按钮:平原/森林/山/雪山/水/沙地/道路/城堡/跳过
    3. 你点一个按钮就行
    4. 自动切下一张
    5. 一张原图切 12-15 次后,自动保存并切到下一张原图

输出格式
--------
和原版完全一样 (map_region_labels.jsonl),所以 derive_palette_from_labels.py
不用改。每个 region 还是 bbox_px + label + avg_rgb。

使用
----
    python tools/label_map_regions.py
    python tools/label_map_regions.py --max-crops 10   # 一张图只标 10 块
    python tools/label_map_regions.py --skip-image     # 跳过当前图

技巧
----
- 一张图的颜色种类有限,大部分是同一片色。所以标 12-15 块基本能覆盖。
- 系统会优先从颜色簇密集的地方切,所以你看到的切图比较有代表性。
- 不确定就点 "跳过" — 系统会换一块。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tkinter as tk
from collections import Counter
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageTk

# ============================================================
# 标签词表(显示用中文,内部 key 用英文)
# ============================================================
LABEL_KEYS: List[str] = [
    "plain", "forest", "mountain", "snow_peak",
    "water", "sand", "road", "castle", "ignore",
]
LABEL_DISPLAY: Dict[str, str] = {
    "plain":     "平原",
    "forest":    "森林",
    "mountain":  "山",
    "snow_peak": "雪山",
    "water":     "水",
    "sand":      "沙地",
    "road":      "道路",
    "castle":    "城堡/建筑",
    "ignore":    "跳过(看不懂)",
}
# 每个标签对应的边框色,画在切图上方便辨认
LABEL_HINT_COLOR: Dict[str, str] = {
    "plain":     "#7ad06d",
    "forest":    "#1f5c25",
    "mountain":  "#8a6a3a",
    "snow_peak": "#dadada",
    "water":     "#3b78d8",
    "sand":      "#e6cf6a",
    "road":      "#b9b0a0",
    "castle":    "#c14a4a",
    "ignore":    "#888888",
}


def _guess_kind(rel: str) -> str:
    """按目录 + 文件名前缀判定 kind(细到 AW2/AWDS 区别)。"""
    if "fire-emblem" in rel:
        return "fire_emblem"
    if "awbw" in rel:
        return "advance_wars_awbw"
    if "advance-wars" in rel:
        base = rel.rsplit("/", 1)[-1].lower()
        if (base.startswith("aw2_") or base.startswith("spann_island_aw2")
                or "sea_fortress" in base or "spann_island" in base):
            return "advance_wars_2"
        if base.startswith("awds_") or "moji_island" in base or "spann_island_awds" in base:
            return "advance_wars_ds"
        return "advance_wars"
    return "fire_emblem"


def _iter_images(root: str) -> List[str]:
    out: List[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def _detect_tile_px(w: int, h: int, kind: str = "") -> int:
    """根据 kind 决定单瓦片边长(像素)。

    - advance_wars_awbw (AWBW 在线预览) → 4px(子瓦片,1 个 macro tile = 3×3 子瓦片)
    - advance_wars_2 / advance_wars_ds (GBA / DS 原版) → 8px
    - fire_emblem (FE8 GBA) → 16px
    - 兜底:按图片大小(< 100 短边 → 8,否则 16)
    """
    if kind == "advance_wars_awbw":
        return 4
    if kind.startswith("advance_wars"):
        return 8
    if kind.startswith("fire_emblem"):
        return 16
    if min(w, h) < 100:
        return 8
    return 16


def _pick_uniform_single_tile_crops(
    arr: np.ndarray, n: int, tile_px: int = 16, attempts: int = 800,
    max_variance: float = 800.0,
) -> List[Tuple[int, int, Tuple[int, int, int]]]:
    """从原图里挑 n 个【单瓦片大小 + 颜色均匀】的切图位置。

    为什么单瓦片:你看到的就是一个 tile,不会跨多种地形,平均色才有意义。
    为什么强制低方差:防止切到瓦片边界 / 装饰边缘那种"两种色混在一起"的格子。

    参数:
        tile_px: 单瓦片边长(像素)。FE / AW = 16,AWBW 小图 = 8。
        max_variance: 切图内部颜色方差上限,超过就跳过。
                      800 是个经验值,够宽松,够筛掉边界。

    返回:list of (x, y, avg_rgb)。x, y 是切图左上角。
    """
    h, w, _ = arr.shape
    if h < tile_px or w < tile_px:
        return []

    rng = random.Random()
    candidates: List[Tuple[int, int, Tuple[int, int, int], float]] = []
    for _ in range(attempts):
        # tile-aligned: 16 像素对齐,确保切出来就是一个完整瓦片
        x = (rng.randint(0, w - tile_px) // tile_px) * tile_px
        y = (rng.randint(0, h - tile_px) // tile_px) * tile_px
        patch = arr[y:y + tile_px, x:x + tile_px].reshape(-1, 3).astype(float)
        var = float(patch.var(axis=0).sum())  # RGB 三通道方差之和
        if var > max_variance:
            continue
        avg = patch.mean(axis=0).astype(int)
        candidates.append((x, y, tuple(avg.tolist()), var))

    if not candidates:
        return []

    # 颜色尽量分散:贪心选 n 个最不像的
    candidates.sort(key=lambda t: t[3])  # 优先选最均匀的(方差小=纯色)
    selected: List[Tuple[int, int, Tuple[int, int, int]]] = []
    for cand in candidates:
        if len(selected) >= n:
            break
        x, y, rgb, var = cand
        # 跟已选的距离
        too_close = False
        for s in selected:
            d2 = sum((rgb[k] - s[2][k]) ** 2 for k in range(3))
            if d2 < 1500:  # RGB 距离太近,跳过
                too_close = True
                break
        if not too_close:
            selected.append((x, y, rgb))
    # 不够 n 个再补:允许近似色
    if len(selected) < n:
        for cand in candidates:
            if len(selected) >= n:
                break
            x, y, rgb, _ = cand
            if any(s[0] == x and s[1] == y for s in selected):
                continue
            selected.append((x, y, rgb))
    return selected


def _pick_targeted_crops(
    arr: np.ndarray, n: int, tile_px: int, target_class: str,
) -> List[Tuple[int, int, Tuple[int, int, int]]]:
    """针对某类地形主动找 n 个候选切图位置(全部单瓦片大小)。

    颜色提示:
      - castle: 任意 HQ 颜色(红/蓝/黄/绿)或浅色屋顶区
      - forest: 深绿
      - sand:   沙黄
      - snow_peak: 高亮白
      - road:   灰/棕
    """
    h, w, _ = arr.shape
    crop = tile_px
    if h < crop or w < crop:
        return []
    rng = random.Random()
    out: List[Tuple[int, int, Tuple[int, int, int]]] = []
    tries = 0
    while len(out) < n and tries < n * 60:
        tries += 1
        x = (rng.randint(0, w - crop) // tile_px) * tile_px
        y = (rng.randint(0, h - crop) // tile_px) * tile_px
        patch = arr[y:y + crop, x:x + crop].reshape(-1, 3).astype(float)
        avg = patch.mean(axis=0)
        r, g, b = avg
        if target_class == "castle":
            # 有归属 HQ(任一 HQ 颜色)
            is_hq_color = (r > 140 and g < 110 and b < 110) or \
                          (b > 140 and r < 110 and g < 110) or \
                          (r > 180 and g > 150 and b < 110) or \
                          (g > 140 and r < 110 and b < 110)
            # 无归属城堡:浅灰/中灰/白(高战中立建筑常用)
            is_neutral_gray = (
                (180 <= r <= 240 and 180 <= g <= 240 and 180 <= b <= 240 and
                 max(r, g, b) - min(r, g, b) < 25) or  # 浅灰 (180-240)
                (r > 220 and g > 220 and b > 220)        # 白 (220+)
            )
            # FE 城堡内部:亮色屋顶/灰色地砖
            is_fe_castle = (
                (r > 200 and g > 180 and b > 100) or  # 黄/沙色屋顶
                (r > 200 and g > 200 and b > 200) or  # 白
                (90 <= r <= 180 and 90 <= g <= 180 and 90 <= b <= 180 and
                 max(r, g, b) - min(r, g, b) < 30)  # 中灰
            )
            if not (is_hq_color or is_neutral_gray or is_fe_castle):
                continue
        elif target_class == "forest":
            if not (g > r + 25 and g > b + 25 and g < 180 and r < 130 and b < 130):
                continue
        elif target_class == "sand":
            if not (r > 180 and g > 160 and b < 200 and r + g > 350):
                continue
        elif target_class == "snow_peak":
            if not (r > 200 and g > 200 and b > 200):
                continue
        elif target_class == "road":
            if not (abs(r - g) < 30 and 100 < (r + g + b) / 3 < 220):
                continue
        else:
            continue
        rgb = (int(r), int(g), int(b))
        out.append((x, y, rgb))
    return out


# ============================================================
# App
# ============================================================


class SimpleLabeler:
    def __init__(
        self, images: List[str], out_path: str, max_crops: int,
        mode: str = "auto", focus: Optional[str] = None,
    ) -> None:
        self.images = images
        self.out_path = out_path
        self.max_crops = max_crops
        self.mode = mode       # "diverse" | "targeted" | "auto"
        self.focus = focus     # "castle" / "forest" / etc, only for targeted
        self.idx = 0
        # Per-image state
        self._arr: Optional[np.ndarray] = None
        self._crops: List[Tuple[int, int, Tuple[int, int, int]]] = []
        self._crop_idx = 0
        self._tile_px = 16
        self.regions: List[Dict[str, Any]] = []

        self.root = tk.Tk()
        self.root.title("地图标注向导")
        self.root.geometry("960x820")
        self.root.minsize(900, 780)
        self.root.configure(bg="#f5f5f5")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._load_current()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # === 顶部状态栏 ===
        top = tk.Frame(self.root, bg="#fff", height=70)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        self.var_progress = tk.StringVar(value="")
        tk.Label(
            top, textvariable=self.var_progress,
            font=("Microsoft YaHei", 12, "bold"), bg="#fff", fg="#333",
        ).pack(anchor=tk.W, padx=16, pady=(8, 0))
        self.var_file = tk.StringVar(value="")
        tk.Label(
            top, textvariable=self.var_file, wraplength=850,
            font=("Microsoft YaHei", 9), bg="#fff", fg="#777",
        ).pack(anchor=tk.W, padx=16)

        # === 中间:小切图 + 原图缩略图 ===
        center = tk.Frame(self.root, bg="#f5f5f5")
        center.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 切图(大,中央)
        crop_frame = tk.Frame(center, bg="#fff", bd=2, relief=tk.SUNKEN)
        crop_frame.pack(side=tk.LEFT, padx=(0, 20))
        self.var_crop_hint = tk.StringVar(value="")
        tk.Label(
            crop_frame, textvariable=self.var_crop_hint,
            font=("Microsoft YaHei", 14, "bold"), bg="#fff", fg="#222",
        ).pack(pady=(8, 4))
        self.lbl_crop = tk.Label(crop_frame, bg="#fff")
        self.lbl_crop.pack(padx=8, pady=8)
        self.var_crop_info = tk.StringVar(value="")
        tk.Label(
            crop_frame, textvariable=self.var_crop_info,
            font=("Consolas", 9), bg="#fff", fg="#888",
        ).pack(pady=(0, 8))

        # 右侧:原图缩略 + 计数
        side = tk.Frame(center, bg="#f5f5f5")
        side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            side, text="原图参考(灰色 = 已标,红框 = 当前):",
            font=("Microsoft YaHei", 9), bg="#f5f5f5", fg="#555",
        ).pack(anchor=tk.W)
        self.lbl_thumb = tk.Label(side, bg="#fff", bd=1, relief=tk.SUNKEN)
        self.lbl_thumb.pack(anchor=tk.NW, pady=(4, 8))
        self.var_count = tk.StringVar(value="")
        tk.Label(
            side, textvariable=self.var_count,
            font=("Microsoft YaHei", 10), bg="#f5f5f5", fg="#222",
        ).pack(anchor=tk.W, pady=(8, 0))

        # === 底部:9 个大按钮(每个用一种代表色,不用记) ===
        bot = tk.Frame(self.root, bg="#ddd", bd=1, relief=tk.RAISED)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            bot, text="👇 这块是什么?点一个按钮:",
            font=("Microsoft YaHei", 12, "bold"), bg="#ddd", fg="#222",
        ).pack(anchor=tk.W, padx=16, pady=(10, 6))
        grid = tk.Frame(bot, bg="#ddd")
        grid.pack(padx=16, pady=(0, 12))
        # 9 个按钮,3 行 3 列,每个都加高加大
        cols = 3
        for i, key in enumerate(LABEL_KEYS):
            r, c = divmod(i, cols)
            color = LABEL_HINT_COLOR.get(key, "#fff")
            btn = tk.Button(
                grid,
                text=LABEL_DISPLAY[key],
                font=("Microsoft YaHei", 14, "bold"),
                bg=color, fg="#fff" if key not in ("plain", "sand", "snow_peak", "road") else "#222",
                activebackground=color,
                width=14, height=3,
                command=lambda k=key: self._on_label(k),
            )
            btn.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
        # 让按钮列等宽
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1)
        # 底部一排动作按钮(更显眼)
        nav = tk.Frame(self.root, bg="#fff", bd=1, relief=tk.RAISED)
        nav.pack(fill=tk.X, side=tk.BOTTOM)
        # 左侧:撤销 / 跳过本块
        tk.Button(
            nav, text="↶ 撤销上一步 (Backspace)",
            font=("Microsoft YaHei", 10),
            command=self._on_undo,
            bg="#fd8", fg="#222",
        ).pack(side=tk.LEFT, padx=8, pady=8)
        tk.Button(
            nav, text="⏭ 跳过本块",
            font=("Microsoft YaHei", 10),
            command=lambda: self._on_label("ignore"),
            bg="#eee", fg="#444",
        ).pack(side=tk.LEFT, padx=4)
        # 整张图跳过(显眼橙色)
        tk.Button(
            nav, text="⤵ 跳过整张图",
            font=("Microsoft YaHei", 11, "bold"),
            command=self._on_skip_image,
            bg="#f96", fg="#fff",
        ).pack(side=tk.LEFT, padx=12)
        # 右侧:保存 / 退出
        tk.Button(
            nav, text="💾 保存 + 下一张",
            font=("Microsoft YaHei", 10, "bold"),
            command=self._on_save_next,
            bg="#5a8", fg="#fff",
        ).pack(side=tk.RIGHT, padx=8, pady=8)
        tk.Button(
            nav, text="❌ 退出",
            font=("Microsoft YaHei", 10),
            command=self._on_quit,
            bg="#a55", fg="#fff",
        ).pack(side=tk.RIGHT, padx=4)
        # Backspace 撤销热键
        self.root.bind("<BackSpace>", lambda _e: self._on_undo())

    # ------------------------------------------------------------------
    # 加载当前图 + 切图
    # ------------------------------------------------------------------
    def _load_current(self) -> None:
        if self.idx >= len(self.images):
            messagebox.showinfo("完成", f"全部 {len(self.images)} 张图都处理完了。\n数据写到:\n{self.out_path}")
            self.root.destroy()
            return
        path = self.images[self.idx]
        self.var_progress.set(
            f"第 {self.idx + 1} / {len(self.images)} 张图"
        )
        self.var_file.set(f"📂 {os.path.relpath(path)}")

        im = Image.open(path).convert("RGB")
        self._pil_full = im
        self._arr = np.array(im)
        # 按 kind 判定瓦片大小 + 切单瓦片、均匀色块
        kind = _guess_kind(path)
        self._tile_px = _detect_tile_px(*im.size, kind=kind)
        self._crops = self._make_crops_for_image()
        self._crop_idx = 0
        self.regions = []
        self._render_thumb()
        self._show_crop()

    def _make_crops_for_image(self) -> List[Tuple[int, int, Tuple[int, int, int], int]]:
        """每项 = (x, y, rgb, crop_size),全部单瓦片。

        - diverse:  8 块颜色分散的均匀单瓦片
        - targeted: 8 块都是目标类(找不到就空)
        - auto:     先 4 块 diverse + 4 块 targeted (找该图最缺的类)
        """
        cs = self._tile_px
        if self.mode == "diverse":
            return [
                (x, y, rgb, cs)
                for (x, y, rgb) in _pick_uniform_single_tile_crops(
                    self._arr, n=self.max_crops, tile_px=self._tile_px,
                )
            ]
        if self.mode == "targeted":
            target = self.focus or "castle"
            out = _pick_targeted_crops(
                self._arr, n=self.max_crops,
                tile_px=self._tile_px, target_class=target,
            )
            if not out:
                out = _pick_uniform_single_tile_crops(
                    self._arr, n=self.max_crops, tile_px=self._tile_px,
                )
            return [(x, y, rgb, cs) for (x, y, rgb) in out]
        # auto: 4 diverse + 找本图最缺类补 4
        diverse = [
            (x, y, rgb, cs)
            for (x, y, rgb) in _pick_uniform_single_tile_crops(
                self._arr, n=4, tile_px=self._tile_px,
            )
        ]
        missing = self._guess_missing_class()
        targeted: List[Tuple[int, int, Tuple[int, int, int], int]] = []
        if missing:
            targeted = [
                (x, y, rgb, cs)
                for (x, y, rgb) in _pick_targeted_crops(
                    self._arr, n=4, tile_px=self._tile_px,
                    target_class=missing,
                )
            ]
        return diverse + targeted

    def _guess_missing_class(self) -> Optional[str]:
        """粗略看本图哪种目标类可能存在,返回最可能缺的那个。"""
        if self._arr is None:
            return None
        arr = self._arr
        h, w, _ = arr.shape
        has_hq = has_forest = has_sand = has_snow = False
        for yy in range(0, h - 8, 8):
            for xx in range(0, w - 8, 8):
                patch = arr[yy:yy + 8, xx:xx + 8].reshape(-1, 3).astype(float).mean(axis=0)
                r, g, b = patch
                if (r > 140 and g < 110 and b < 110) or (b > 140 and r < 110 and g < 110) \
                   or (r > 180 and g > 150 and b < 110) or (g > 140 and r < 110 and b < 110):
                    has_hq = True
                if g > r + 25 and g > b + 25 and g < 180 and r < 130:
                    has_forest = True
                if r > 180 and g > 160 and b < 200 and r + g > 350:
                    has_sand = True
                if r > 200 and g > 200 and b > 200:
                    has_snow = True
        if has_hq:
            return "castle"
        if has_forest:
            return "forest"
        if has_sand:
            return "sand"
        if has_snow:
            return "snow_peak"
        return None

    def _render_thumb(self) -> None:
        if not hasattr(self, "_pil_full"):
            return
        im = self._pil_full.copy()
        # 在已标过的切图位置画灰色
        for x, y, _rgb, cs in self._crops[: self._crop_idx]:
            for dx in range(0, cs, 2):
                for dy in range(0, cs, 2):
                    if 0 <= x + dx < im.size[0] and 0 <= y + dy < im.size[1]:
                        im.putpixel((x + dx, y + dy), (180, 180, 180))
        # 当前切图位置画红色边框
        if self._crop_idx < len(self._crops):
            x, y, _, cs = self._crops[self._crop_idx]
            for i in range(cs):
                if 0 <= x + i < im.size[0]:
                    im.putpixel((x + i, y), (255, 0, 0))
                    im.putpixel((x + i, y + cs - 1), (255, 0, 0))
                if 0 <= y + i < im.size[1]:
                    im.putpixel((x, y + i), (255, 0, 0))
                    im.putpixel((x + cs - 1, y + i), (255, 0, 0))
        thumb = im.copy()
        thumb.thumbnail((280, 210), Image.NEAREST)
        self._photo_thumb = ImageTk.PhotoImage(thumb)
        self.lbl_thumb.config(image=self._photo_thumb)

    def _show_crop(self) -> None:
        if self._crop_idx >= len(self._crops):
            self._on_save_next()
            return
        x, y, rgb, cs = self._crops[self._crop_idx]
        # 切出 crop(可能是单瓦片,可能是 3×3 多瓦片)
        patch = self._pil_full.crop((x, y, x + cs, y + cs))
        big = patch.resize((256, 256), Image.NEAREST)
        self._photo_crop = ImageTk.PhotoImage(big)
        self.lbl_crop.config(image=self._photo_crop)
        self.var_crop_hint.set(
            f"第 {self._crop_idx + 1} / {len(self._crops)} 块"
        )
        # crop 大小说明
        if cs == self._tile_px:
            tile_zh = {8: "8px (AWBW)", 12: "12px", 16: "16px (FE/AW)"}.get(cs, f"{cs}px")
            crop_desc = f"单瓦片 {tile_zh}"
        else:
            crop_desc = f"多瓦片 {cs}×{cs} (HQ 结构)"
        self.var_crop_info.set(
            f"{crop_desc}    位置: ({x}, {y})    "
            f"颜色: RGB{rgb}"
        )
        # 类别统计(看看缺什么)
        from collections import Counter
        cnt = Counter(r["label"] for r in self.regions)
        missing = [k for k in ("plain", "forest", "mountain", "water", "road", "castle")
                   if k not in cnt]
        miss_text = f"   还没标: {'/'.join(missing[:3]) or '够全'}"
        self.var_count.set(
            f"本图已标: {dict(cnt)}{miss_text}   "
            f"剩余: {len(self._crops) - self._crop_idx} 块"
        )

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def _on_label(self, key: str) -> None:
        if self._crop_idx >= len(self._crops):
            return
        x, y, rgb, cs = self._crops[self._crop_idx]
        # "ignore" 算作"看不清",不写入 region,只前进
        if key != "ignore":
            self.regions.append({
                "bbox_px": [x, y, x + cs, y + cs],
                "label": key,
                "avg_rgb": [int(rgb[0]), int(rgb[1]), int(rgb[2])],
                "n_pixels": cs * cs,
            })
        self._crop_idx += 1
        self._render_thumb()
        if self._crop_idx >= len(self._crops):
            self._on_save_next()
        else:
            self._show_crop()

    def _on_undo(self) -> None:
        """撤销上一步标注(只是把 _crop_idx 退 1,真要改 label 就让用户标到 ignore 跳过)"""
        if self._crop_idx == 0:
            return
        self._crop_idx -= 1
        # 如果之前那条 region 是真标过的(不是 ignore),删掉
        if len(self.regions) > self._crop_idx:
            self.regions = self.regions[: self._crop_idx]
        self._render_thumb()
        self._show_crop()

    def _on_save_next(self) -> None:
        self._write_jsonl()
        self.idx += 1
        self._load_current()

    def _on_skip_image(self) -> None:
        # 不写 JSONL,直接下一张
        self.idx += 1
        self._load_current()

    def _on_quit(self) -> None:
        self._write_jsonl()
        self.root.destroy()

    def _on_window_close(self) -> None:
        self._write_jsonl()
        self.root.destroy()

    def _write_jsonl(self) -> None:
        if not self.regions:
            return
        path = self.images[self.idx]
        record = {
            "path": os.path.relpath(path).replace("\\", "/"),
            "kind": _guess_kind(path),
            "regions": self.regions,
        }
        os.makedirs(os.path.dirname(self.out_path) or ".", exist_ok=True)
        with open(self.out_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self) -> None:
        self.root.mainloop()


# ============================================================
# CLI
# ============================================================


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument(
        "--root",
        default="docs/路线/参考调研/battle-map-references/images",
    )
    p.add_argument(
        "--out",
        default="docs/路线/参考调研/battle-map-references/map_region_labels.jsonl",
    )
    p.add_argument(
        "--max-crops", type=int, default=8,
        help="一张原图切几块(默认 8,够覆盖大部分色板)",
    )
    p.add_argument(
        "--mode", default="auto", choices=["diverse", "targeted", "auto"],
        help="diverse=颜色分散单瓦片; targeted=只找目标类; auto=前 4 块分散+后 4 块找缺的",
    )
    p.add_argument(
        "--focus", default=None,
        choices=["plain", "forest", "mountain", "snow_peak", "water",
                 "sand", "road", "castle"],
        help="targeted 模式找哪类(默认 castle)",
    )
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)

    images = _iter_images(args.root)
    if args.start:
        images = images[args.start:]
    if args.limit:
        images = images[:args.limit]
    if not images:
        print("没找到图", file=sys.stderr)
        return 1

    # 跳过已标过的
    if os.path.exists(args.out):
        # 收集每张图已经标过的 labels
        labels_by_path: Dict[str, set] = {}
        with open(args.out, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                p = rec.get("path", "")
                labels_by_path.setdefault(p, set()).update(
                    r.get("label", "") for r in rec.get("regions", [])
                )
        before = len(images)
        target = args.focus
        if args.mode == "targeted" and target:
            # targeted 模式:只跳已标过 *目标类* 的图
            images = [
                p for p in images
                if target not in labels_by_path.get(
                    os.path.relpath(p).replace("\\", "/"), set()
                )
            ]
        else:
            # diverse / auto:跳已标过任何标签的图
            images = [
                p for p in images
                if os.path.relpath(p).replace("\\", "/") not in labels_by_path
            ]
        skipped = before - len(images)
        if skipped:
            print(f"已跳过 {skipped} 张(已标过相应类别)", file=sys.stderr)

    if not images:
        if args.focus:
            print(f"所有图都已标过 '{args.focus}',没新图可标", file=sys.stderr)
        else:
            print("没有要标的图了", file=sys.stderr)
        return 0

    SimpleLabeler(
        images, args.out, args.max_crops,
        mode=args.mode, focus=args.focus,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
