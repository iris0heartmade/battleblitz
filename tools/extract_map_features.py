#!/usr/bin/env python3
"""
extract_map_features.py — visual feature extractor for FE / AW / AWBW maps.

Why this exists
---------------
We have ~30 high-quality battle-map thumbnails downloaded from Fire
Emblem Wiki, the Advance Wars Wiki, and the AWBW community. The
existing research report (2026-07-22-火纹与高战战斗地图参考分析.md)
gave us design *principles* but not measurable features. Before we can
build a fitness function for the procedural generator we need to turn
the pixels into numbers:

    - per-terrain pixel share (forest, mountain, water, sand, road, …)
    - castle / HQ positions (centroid + bounding box)
    - water clusters (river vs. sea vs. lake — by size)
    - road connectivity (one network or many fragments)
    - faction colors detected (red / blue / green / yellow)
    - is-island / is-symmetric / chokepoint-candidate count
    - estimated tile resolution (px / tile) so we can back-project
      positions into tile units for direct comparison with our grid

Usage
-----
    # extract all images under the default dir, dump to map_features.json
    python tools/extract_map_features.py

    # custom in/out paths
    python tools/extract_map_features.py \
        --images docs/路线/参考调研/battle-map-references/images \
        --out     docs/路线/参考调研/battle-map-references/map_features.json

Output schema
-------------
A single JSON file. Top level: ``{"version": 1, "images": [ ... ]}``.
Each image entry has ``path``, ``kind``, ``grid_px`` (W,H), ``tile_px``
(best-guess per-tile resolution), and ``features`` (the dict above).

Calibration
-----------
The default color thresholds were hand-picked from inspecting ~7 sample
images.  Each ``kind`` (``fire_emblem`` / ``advance_wars`` /
``advance_wars_awbw``) gets its own palette so an FE green doesn't get
mis-classified as AW plain.  If extraction looks wrong on a new image,
the recommended path is:

    1. ``python tools/label_map_regions.py``  (drag a few regions, save)
    2. ``python tools/derive_palette_from_labels.py``  (rebuild buckets)
    3. re-run this script  — it now auto-loads ``derived_palette.json``
       if present, overriding the hand-picked values.

No ML, no CNN.  Just numpy + PIL + a few BFS calls.  Keep it that way
so we can read the result in 5 minutes and not depend on a training
pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image

# ============================================================
# Optional override: if ``derived_palette.json`` exists next to the
# image root, we replace each (kind, label) bucket in _PALETTES with
# the data-driven one.  This is how the human-labelled regions feed
# back into the auto-classifier.
# ============================================================
_DERIVED_PALETTE_PATHS = [
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "路线", "参考调研", "battle-map-references",
        "derived_palette.json",
    ),
    "derived_palette.json",
]


def _load_derived_palette() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return {kind: {label: {low, high, …}}} or {} if no file."""
    for cand in _DERIVED_PALETTE_PATHS:
        if os.path.exists(cand):
            try:
                with open(cand, encoding="utf-8") as fp:
                    payload = json.load(fp)
                return payload.get("palette", {}) or {}
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def _apply_derived_palette(palettes: Dict[str, List]) -> Dict[str, List]:
    """Override the hardcoded low/high per (kind, label) using the
    derived JSON.  Returns a *new* dict so the caller's copy is left
    alone (useful for tests).
    """
    derived = _load_derived_palette()
    if not derived:
        return palettes
    out: Dict[str, List] = {}
    for kind, entries in palettes.items():
        new_entries: List = []
        for name, cls, low, high in entries:
            # Look up the matching class in the derived data.
            bucket = derived.get(kind, {}).get(cls)
            if bucket and "low" in bucket and "high" in bucket:
                new_entries.append(
                    (name, cls, tuple(bucket["low"]), tuple(bucket["high"]))
                )
            else:
                new_entries.append((name, cls, low, high))
        out[kind] = new_entries
    return out


def _resolve_active_palettes() -> None:
    """Refresh ``_ACTIVE_PALETTES`` from the (possibly newly written)
    derived palette file.  Cheap to call per-image.
    """
    global _ACTIVE_PALETTES
    merged = _apply_derived_palette(_PALETTES)
    for kind, entries in merged.items():
        _ACTIVE_PALETTES[kind] = entries

# ============================================================
# Color palettes (per source).  Each entry is (R, G, B) range and
# which terrain_class it contributes to.  Order matters: first match
# wins.  All thresholds are inclusive on both ends to handle JPEG /
# WebP anti-aliasing fringes.
# ============================================================

# _PALETTES[kind] -> (name, terrain_class, low, high) tuples, low/high
# inclusive per channel.  ``advance_wars_2`` and ``advance_wars_ds`` reuse
# the ``advance_wars`` palette (GBA / DS colors overlap) until the
# derived_palette.json overrides them with hand-labelled data.
_PALETTES: Dict[str, List[Tuple[str, str, Tuple[int, int, int], Tuple[int, int, int]]]] = {
    "fire_emblem": [
        # Sea / deep water (Bethroen / Melkaen)
        ("deep_water",  "water",     (0,  60, 100), (40, 130, 180)),
        # River / shallow water
        ("water",       "water",     (40, 130, 180), (90, 200, 230)),
        # Sand / beach
        ("sand",        "sand",      (200, 200, 80), (255, 255, 200)),
        # Mountain / rocky
        ("mountain",    "mountain",  (80,  60,  40), (140, 110,  80)),
        # Snow / silver peak (Darkling Woods)
        ("snow_peak",   "mountain",  (180, 180, 200), (245, 245, 245)),
        # Forest (dark green to teal)
        ("forest",      "forest",    (10,  60,  30), (70, 130,  90)),
        # Plain (teal-green) — broad because FE palette is pastel
        ("plain",       "plain",     (70, 160, 120), (200, 240, 220)),
        # Road (warm tan)
        ("road",        "road",      (160, 130,  80), (220, 180, 130)),
        # Castle (gray stone with red accents) — accept wide gray
        ("castle",      "castle",    (110, 100,  90), (210, 200, 180)),
        # Castle red roof
        ("castle_red",  "castle",    (160,  20,  20), (240,  80,  80)),
        # Purple throne / darkling (very specific to FE8)
        ("throne",      "castle",    (80,  20, 130), (160,  80, 200)),
    ],
    "advance_wars": [
        # Sea (purple-blue)
        ("sea",         "water",     (60,  50, 200), (140, 110, 255)),
        # River / shallow
        ("water",       "water",     (80, 130, 220), (180, 200, 250)),
        # Plain (lime green)
        ("plain",       "plain",     (140, 200,  20), (220, 240,  90)),
        # Forest
        ("forest",      "forest",    (20,  90,  20), (90, 150,  70)),
        # Mountain (gray-tan)
        ("mountain",    "mountain",  (130, 130, 110), (200, 200, 180)),
        # Snow peak
        ("snow_peak",   "mountain",  (200, 220, 230), (250, 250, 250)),
        # Road / city (gray)
        ("road",        "road",      (130, 150, 170), (200, 210, 220)),
        # HQ buildings (red/blue/yellow/green) treated as castle
        ("hq_red",      "castle",    (200,  30,  30), (250, 100, 100)),
        ("hq_blue",     "castle",    (30,   30, 200), (110, 110, 250)),
        ("hq_yellow",   "castle",    (200, 180,  30), (250, 240, 130)),
        ("hq_green",    "castle",    (30,  150,  30), (110, 230, 110)),
    ],
    "advance_wars_awbw": [
        # Sea (royal blue)
        ("sea",         "water",     (40,  60, 200), (140, 200, 255)),
        # River (lighter blue)
        ("river",       "water",     (80, 130, 200), (160, 200, 250)),
        # Plain (lime green)
        ("plain",       "plain",     (80,  200,  30), (180, 250, 110)),
        # Forest
        ("forest",      "forest",    (30,  90,  20), (90, 150,  70)),
        # Mountain (gray-tan)
        ("mountain",    "mountain",  (140, 140, 120), (200, 200, 180)),
        # Snow / white
        ("snow",        "mountain",  (210, 210, 200), (255, 255, 255)),
        # Road (very light gray, almost white)
        ("road",        "road",      (210, 210, 200), (255, 255, 255)),
        # HQ buildings
        ("hq_red",      "castle",    (200,  30,  30), (255, 100,  90)),
        ("hq_blue",     "castle",    (30,   30, 200), (110,  90, 250)),
        ("hq_yellow",   "castle",    (200, 180,  20), (255, 240, 110)),
        ("hq_green",    "castle",    (30,  150,  30), (110, 230, 110)),
    ],
}

# 在 _PALETTES 之后,把 advance_wars_2 / advance_wars_ds 指向同一份数据
# (sub-kind 只是训练维度,像素色板暂时共用 advance_wars 的;derived_palette
# 里有更准的就用 derived 的覆盖)
for _sub in ("advance_wars_2", "advance_wars_ds"):
    _PALETTES[_sub] = list(_PALETTES["advance_wars"])


def _classify_pixels(arr: np.ndarray, kind: str) -> Tuple[np.ndarray, List[str]]:
    """Return (class_grid, palette_order) — class_grid per-pixel class id.

    class id 0 = unclassified / background.  id N+1 maps to
    palette_order[N].  Both arrays are H×W.

    Uses ``active_palettes`` if the caller has loaded a derived
    palette; otherwise falls back to the module-level ``_PALETTES``.
    """
    palette = _ACTIVE_PALETTES.get(kind, _PALETTES[kind])
    order = [name for name, *_ in palette]
    h, w, _ = arr.shape
    class_id = np.zeros((h, w), dtype=np.uint8)
    for i, (_name, _cls, low, high) in enumerate(palette):
        low_a = np.array(low, dtype=np.uint8)
        high_a = np.array(high, dtype=np.uint8)
        mask = np.all((arr >= low_a) & (arr <= high_a), axis=-1)
        # Only set unclassified pixels (first match wins).
        new_mask = mask & (class_id == 0)
        class_id[new_mask] = i + 1
    return class_id, order


# Resolved palette lookup — overridden by derived_palette.json when
# present.  Lives at module scope so ``_classify_pixels`` can find
# the current values without threading them through every function.
_ACTIVE_PALETTES: Dict[str, List] = {kind: list(entries) for kind, entries in _PALETTES.items()}


def _connected_components(mask: np.ndarray) -> List[Dict[str, Any]]:
    """Return a list of {pixels:int, bbox:Tuple[x0,y0,x1,y1], centroid:(x,y)}."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps: List[Dict[str, Any]] = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            q = deque([(x, y)])
            seen[y, x] = True
            xs: List[int] = []
            ys: List[int] = []
            while q:
                cx, cy = q.popleft()
                xs.append(cx)
                ys.append(cy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((nx, ny))
            comps.append({
                "pixels": len(xs),
                "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "centroid": (sum(xs) / len(xs), sum(ys) / len(ys)),
            })
    return comps


def _class_to_mask(class_id: np.ndarray, target_name: str, order: List[str]) -> np.ndarray:
    if target_name not in order:
        return np.zeros_like(class_id, dtype=bool)
    target_id = order.index(target_name) + 1
    return class_id == target_id


def _class_share(class_id: np.ndarray, order: List[str]) -> Dict[str, float]:
    """Return {terrain_class_name: fraction}.  Unclassified is dropped."""
    total = class_id.size
    out: Dict[str, float] = {}
    for i, name in enumerate(order):
        # First entry of palette tuple's *terrain class* is in palette
        # tuple at index 1.  Pull the class out of the palette.
        cls = _PALETTES[_kind_from_order(order)][i][1]
        share = float((class_id == (i + 1)).sum()) / total
        # Merge multiple names into the same class (e.g. castle + castle_red
        # both roll up into "castle").
        out[cls] = out.get(cls, 0.0) + share
    return out


def _count_chokepoint_candidates(water_comps: List[Dict[str, Any]]) -> int:
    """A water "neck" is a 1-2 cell-wide water channel between two
    larger water bodies.  Heuristic: count water clusters whose bbox
    aspect ratio is > 3:1.  Written as a plain loop because the
    inline-lambda form in a generator expression confuses Python.
    """
    n = 0
    for c in water_comps:
        b = c["bbox"]
        bw = b[2] - b[0]
        bh = b[3] - b[1]
        long_side = max(bw, bh)
        short_side = max(1, min(bw, bh))
        if long_side / short_side > 3 and long_side >= 8:
            n += 1
    return n


def _kind_from_order(order: List[str]) -> str:
    # Invert the lookup.  Cheap because we have only 3 kinds.
    for k, pal in _PALETTES.items():
        if [n for n, *_ in pal] == order:
            return k
    return "fire_emblem"  # default fallback


def _guess_tile_px(grid_px: Tuple[int, int], features: Dict[str, Any], kind: str = "") -> int:
    """Best-guess px per tile.  Per kind:
      - advance_wars_awbw → 4 (AWBW online preview uses 3×3 sub-tiles)
      - advance_wars_2 / advance_wars_ds → 8 (GBA/DS original)
      - fire_emblem → 16 (FE8 GBA)
    Falls back to bbox-castle-median heuristic when no kind given.
    """
    if kind == "advance_wars_awbw":
        return 4
    if kind.startswith("advance_wars"):
        return 8
    if kind.startswith("fire_emblem"):
        return 16
    w, h = grid_px
    cs = features.get("castle_clusters", [])
    if cs:
        sides: List[int] = []
        for c in cs:
            b = c.get("bbox_px") or c.get("bbox")
            if not b:
                continue
            sides.extend([b[2] - b[0], b[3] - b[1]])
        sides = [s for s in sides if 4 <= s <= 80]
        if sides:
            med = float(np.median(sides))
            for cand in (4, 8, 12, 16, 24, 32):
                if abs(med - cand) / cand < 0.4:
                    return cand
    return 16


# ============================================================
# Per-image driver.
# ============================================================

def extract(image_path: str) -> Dict[str, Any]:
    rel = os.path.relpath(image_path).replace("\\", "/")
    kind = _guess_kind(rel)
    im = Image.open(image_path).convert("RGB")
    arr = np.array(im)
    h, w, _ = arr.shape

    # Apply derived palette (if any) per-image so the rest of the
    # pipeline keeps using the module-level lookups.
    _resolve_active_palettes()
    class_id, order = _classify_pixels(arr, kind)
    share = _class_share(class_id, order)

    # Components per terrain class.
    def _big_components(name: str, min_pixels: int = 16) -> List[Dict[str, Any]]:
        m = _class_to_mask(class_id, name, order)
        return [c for c in _connected_components(m) if c["pixels"] >= min_pixels]

    # Use the active palette so derived overrides take effect here too.
    palette = _ACTIVE_PALETTES.get(kind, _PALETTES[kind])

    # Castle = roll up all "castle"-class palette entries.
    castle_mask = np.zeros_like(class_id, dtype=bool)
    for i, (_name, cls, *_rest) in enumerate(palette):
        if cls == "castle":
            castle_mask |= (class_id == (i + 1))
    castle_comps = [c for c in _connected_components(castle_mask) if c["pixels"] >= 32]

    water_comps: List[Dict[str, Any]] = []
    for i, (_name, cls, *_rest) in enumerate(palette):
        if cls == "water":
            water_comps.extend(
                c for c in _connected_components(class_id == (i + 1)) if c["pixels"] >= 16
            )

    road_mask = np.zeros_like(class_id, dtype=bool)
    for i, (_name, cls, *_rest) in enumerate(palette):
        if cls == "road":
            road_mask |= (class_id == (i + 1))
    road_comps = [c for c in _connected_components(road_mask) if c["pixels"] >= 8]

    forest_comps: List[Dict[str, Any]] = []
    for i, (_name, cls, *_rest) in enumerate(palette):
        if cls == "forest":
            forest_comps.extend(
                c for c in _connected_components(class_id == (i + 1)) if c["pixels"] >= 16
            )

    mountain_comps: List[Dict[str, Any]] = []
    for i, (_name, cls, *_rest) in enumerate(palette):
        if cls == "mountain":
            mountain_comps.extend(
                c for c in _connected_components(class_id == (i + 1)) if c["pixels"] >= 16
            )

    features: Dict[str, Any] = {
        "kind": kind,
        "grid_px": [w, h],
        "terrain_share": share,
        "castle_clusters": [
            {
                "pixels": c["pixels"],
                "bbox_px": list(c["bbox"]),
                "centroid_px": [round(c["centroid"][0], 1), round(c["centroid"][1], 1)],
            }
            for c in castle_comps
        ],
        "castle_count": len(castle_comps),
        "water_clusters": [
            {
                "pixels": c["pixels"],
                "bbox_px": list(c["bbox"]),
                "centroid_px": [round(c["centroid"][0], 1), round(c["centroid"][1], 1)],
            }
            for c in water_comps
        ],
        "water_cluster_count": len(water_comps),
        "largest_water_share": max(
            ((c["pixels"] / (w * h)) for c in water_comps), default=0.0
        ),
        "road_clusters": len(road_comps),
        "largest_road_share": max(
            ((c["pixels"] / (w * h)) for c in road_comps), default=0.0
        ),
        "forest_clusters": len(forest_comps),
        "mountain_clusters": len(mountain_comps),
    }

    tile_px = _guess_tile_px((w, h), features, kind=kind)
    features["tile_px_guess"] = tile_px
    features["grid_tiles_guess"] = [
        round(w / tile_px, 1),
        round(h / tile_px, 1),
    ]

    # Heuristic flags (don't over-trust these — they exist to surface
    # *candidates* for the human reviewer, not as authoritative).
    features["is_island"] = (
        features["largest_water_share"] > 0.30
        and len(water_comps) <= 2
    )
    features["is_marsh_or_fen"] = (
        share.get("water", 0) > 0.20
        and share.get("sand", 0) < 0.05
        and share.get("plain", 0) > 0.40
    )
    features["looks_symmetric"] = (
        len(castle_comps) in (2, 4)
    )
    features["chokepoint_candidate_count"] = _count_chokepoint_candidates(water_comps)
    return {"path": rel, "features": features}


def _guess_kind(rel: str) -> str:
    """按目录 + 文件名前缀判定 kind(细到 AW2/AWDS 区别)。"""
    if "fire-emblem" in rel:
        return "fire_emblem"
    if "awbw" in rel:
        return "advance_wars_awbw"
    if "advance-wars" in rel:
        # AW 2 (GBA) vs AW Dual Strike (DS) 颜色不一样,分开训练
        base = rel.rsplit("/", 1)[-1].lower()
        if (base.startswith("aw2_") or base.startswith("spann_island_aw2")
                or "sea_fortress" in base or "spann_island" in base):
            return "advance_wars_2"
        if base.startswith("awds_") or "moji_island" in base or "spann_island_awds" in base:
            return "advance_wars_ds"
        return "advance_wars"
    return "fire_emblem"


# ============================================================
# CLI.
# ============================================================

def _iter_images(root: str) -> List[str]:
    out: List[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument(
        "--images",
        default="docs/路线/参考调研/battle-map-references/images",
        help="Root directory to scan for images.",
    )
    p.add_argument(
        "--out",
        default="docs/路线/参考调研/battle-map-references/map_features.json",
        help="Output JSON path.",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    images = _iter_images(args.images)
    if not images:
        print(f"no images found under {args.images}", file=sys.stderr)
        return 1

    results: List[Dict[str, Any]] = []
    for img in images:
        try:
            results.append(extract(img))
        except Exception as e:  # noqa: BLE001
            print(f"FAILED {img}: {e!r}", file=sys.stderr)
            continue
        if not args.quiet:
            f = results[-1]["features"]
            print(
                f"{os.path.basename(img):42s}  "
                f"size={f['grid_px']}  "
                f"tile={f['tile_px_guess']}px  "
                f"castle={f['castle_count']}  "
                f"water={f['water_cluster_count']}  "
                f"plain={f['terrain_share'].get('plain', 0):.2f}"
            )

    payload = {"version": 1, "image_count": len(results), "images": results}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}  ({len(results)} images)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
