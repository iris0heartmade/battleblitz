#!/usr/bin/env python3
"""
derive_palette_from_labels.py — turn human-labelled regions into color buckets.

Why this exists
---------------
``extract_map_features.py`` ships with hand-picked RGB ranges, which is
fine for a first cut but it can't survive a new palette (e.g. AWDS
uses different greens than AW1).  Instead of hand-tuning thresholds
every time, we let the human label regions in
``label_map_regions.py`` and derive the buckets from *their* data.

Algorithm
---------
For every (kind, label) pair, gather all the pixels inside the labelled
rectangles.  We then compute per-channel robust ranges:

  * 5th / 95th percentile  →  ``low``  /  ``high``  bounds
  * median                  →  printed as a hint, not used directly

We also expand the range by a small fudge factor (5%) so borderline
anti-aliased pixels still match.

Output
------
Writes a JSON file ``derived_palette.json`` with the new thresholds
and prints a per-class summary table.  Then re-runs
``extract_map_features`` against a small audit set (every region in the
JSONL) so you can see the round-trip accuracy.

Usage
-----
    # 1. label a few images (1-2 per kind, ~10-15 regions each)
    python tools/label_map_regions.py

    # 2. derive the palette and audit accuracy
    python tools/derive_palette_from_labels.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image

# ============================================================
# Imports from the extractor — avoid duplicating palette schema.
# ============================================================
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "game"))

# ============================================================
# Label vocabulary (mirrors label_map_regions.LABELS).
# ============================================================
TERRAIN_CLASSES: List[str] = [
    "plain", "forest", "mountain", "snow_peak",
    "water", "sand", "road", "castle",
]

# Per-class pixel fudge factor (relative to the 5/95 percentile range).
# Slightly larger for water / sand because those are anti-aliasing
# hotspots; slightly smaller for castle because HQ roofs have tight hues.
FUDGE = {
    "plain": 0.05,
    "forest": 0.05,
    "mountain": 0.05,
    "snow_peak": 0.05,
    "water": 0.10,
    "sand": 0.10,
    "road": 0.05,
    "castle": 0.03,
}


def _load_labels(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _gather_pixels(record: Dict[str, Any], root_hint: str) -> List[Tuple[str, np.ndarray]]:
    """Return (label, Nx3 pixel array) tuples for one record."""
    path = record["path"]
    # Records store relative paths but Image.open needs an absolute one
    # (or one relative to the cwd).  Try the recorded path first; if
    # that fails, try resolving under the project's images root.
    candidates = [path]
    if root_hint and not os.path.isabs(path):
        candidates.append(os.path.join(root_hint, path))
    for cand in candidates:
        if os.path.exists(cand):
            break
    else:
        raise FileNotFoundError(f"image not found: {path} (tried {candidates})")
    im = Image.open(cand).convert("RGB")
    arr = np.array(im)
    out: List[Tuple[str, np.ndarray]] = []
    for r in record.get("regions", []):
        if r.get("label") == "ignore":
            continue
        x0, y0, x1, y1 = r["bbox_px"]
        if x1 <= x0 or y1 <= y0:
            continue
        patch = arr[y0:y1, x0:x1].reshape(-1, 3)
        out.append((r["label"], patch))
    return out


def _derive_bucket(pixels: np.ndarray, label: str) -> Dict[str, Any]:
    """Compute robust low/high RGB bounds from a stack of pixels.

    Strategy:
      * Compute the 5th / 95th percentile per channel.
      * Apply a per-class fudge factor so anti-aliased fringe pixels
        still match.
      * Clamp to valid RGB [0, 255].
    """
    fudge = FUDGE.get(label, 0.05)
    low_p = np.percentile(pixels, 5, axis=0)
    high_p = np.percentile(pixels, 95, axis=0)
    span = high_p - low_p
    low = np.maximum(0, np.floor(low_p - fudge * span)).astype(int).tolist()
    high = np.minimum(255, np.ceil(high_p + fudge * span)).astype(int).tolist()
    median = np.median(pixels, axis=0).astype(int).tolist()
    return {
        "label": label,
        "n_pixels": int(pixels.shape[0]),
        "n_regions": int(np.unique(pixels, axis=0).shape[0]),
        "low": low,
        "high": high,
        "median": median,
        "fudge": fudge,
    }


def derive(records: List[Dict[str, Any]], root_hint: str) -> Dict[str, Any]:
    """Return the derived palette keyed by ``kind`` → ``label`` → bucket."""
    by_kind: Dict[str, Dict[str, List[np.ndarray]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rec in records:
        kind = rec.get("kind", "fire_emblem")
        try:
            for label, pixels in _gather_pixels(rec, root_hint):
                if label in TERRAIN_CLASSES and pixels.size:
                    by_kind[kind][label].append(pixels)
        except FileNotFoundError as e:
            print(f"  warn: {e}", file=sys.stderr)
    out: Dict[str, Any] = {}
    for kind, by_label in by_kind.items():
        out[kind] = {}
        for label, chunks in by_label.items():
            stacked = np.concatenate(chunks, axis=0)
            out[kind][label] = _derive_bucket(stacked, label)
    return out


# ============================================================
# Audit pass: re-apply the derived palette to every labelled region
# and report per-class accuracy.  This is the round-trip that tells
# us if more labels are needed.
# ============================================================


def _classify_with_buckets(arr: np.ndarray, buckets: Dict[str, Dict[str, Any]]) -> np.ndarray:
    """Return an H×W int8 array where each value is the class id or
    0 (unclassified).  Class ids match the order of TERRAIN_CLASSES + 1.
    """
    h, w, _ = arr.shape
    out = np.zeros((h, w), dtype=np.uint8)
    for i, label in enumerate(TERRAIN_CLASSES):
        bucket = buckets.get(label)
        if bucket is None:
            continue
        low = np.array(bucket["low"], dtype=np.uint8)
        high = np.array(bucket["high"], dtype=np.uint8)
        mask = np.all((arr >= low) & (arr <= high), axis=-1)
        out[mask & (out == 0)] = i + 1  # first match wins
    return out


def audit(records: List[Dict[str, Any]], palette: Dict[str, Any], root_hint: str) -> Dict[str, Any]:
    """For every labelled region, classify its bbox and report
    per-class accuracy.  Returns a summary dict that also gets printed.

    Per-kind accuracy is also computed (so the user can see which
    game/palette is healthy vs. which needs more labels).
    """
    per_class_correct: Dict[str, int] = defaultdict(int)
    per_class_total: Dict[str, int] = defaultdict(int)
    # Per-(kind, label) accuracy so the user can compare across games
    per_kind_class_correct: Dict[Tuple[str, str], int] = defaultdict(int)
    per_kind_class_total: Dict[Tuple[str, str], int] = defaultdict(int)
    for rec in records:
        kind = rec.get("kind", "fire_emblem")
        buckets = palette.get(kind, {})
        if not buckets:
            continue
        path = rec["path"]
        candidates = [path]
        if root_hint and not os.path.isabs(path):
            candidates.append(os.path.join(root_hint, path))
        cand = next((c for c in candidates if os.path.exists(c)), None)
        if cand is None:
            continue
        im = Image.open(cand).convert("RGB")
        arr = np.array(im)
        class_grid = _classify_with_buckets(arr, buckets)
        target_id_by_label = {lbl: i + 1 for i, lbl in enumerate(TERRAIN_CLASSES)}
        for r in rec.get("regions", []):
            if r.get("label") == "ignore":
                continue
            x0, y0, x1, y1 = r["bbox_px"]
            if x1 <= x0 or y1 <= y0:
                continue
            target = r["label"]
            if target not in target_id_by_label:
                continue
            patch = class_grid[y0:y1, x0:x1]
            correct = int((patch == target_id_by_label[target]).sum())
            total = int(patch.size)
            per_class_correct[target] += correct
            per_class_total[target] += total
            per_kind_class_correct[(kind, target)] += correct
            per_kind_class_total[(kind, target)] += total
    summary: Dict[str, Any] = {
        "by_class": {},
        "by_kind_class": {},
    }
    for label in TERRAIN_CLASSES:
        total = per_class_total.get(label, 0)
        correct = per_class_correct.get(label, 0)
        summary["by_class"][label] = {
            "pixels": total,
            "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
        }
    # Per-(kind, label) flat dict
    for (kind, label), total in per_kind_class_total.items():
        correct = per_kind_class_correct[(kind, label)]
        key = f"{kind}/{label}"
        summary["by_kind_class"][key] = {
            "pixels": total,
            "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
        }
    return summary


# ============================================================
# Pretty print
# ============================================================


def _print_palette(palette: Dict[str, Any]) -> None:
    print("\nDerived palette buckets")
    print("=" * 76)
    print(f"{'kind':18s} {'label':10s} {'low':16s} {'high':16s} "
          f"{'median':16s} {'pixels':>7s} {'regions':>7s}")
    print("-" * 76)
    for kind, by_label in palette.items():
        if not by_label:
            print(f"  {kind:18s}  (no labels)")
            continue
        for label, b in by_label.items():
            print(
                f"{kind:18s} {label:10s} "
                f"{str(tuple(b['low'])):16s} {str(tuple(b['high'])):16s} "
                f"{str(tuple(b['median'])):16s} {b['n_pixels']:7d} {b['n_regions']:7d}"
            )
    print("=" * 76)


def _print_audit(audit_dict: Dict[str, Any]) -> None:
    print("\nRound-trip accuracy on the labelled set")
    print("=" * 60)
    print(f"{'label':12s} {'pixels':>10s} {'correct':>10s} {'accuracy':>10s}")
    print("-" * 60)
    total_pixels = 0
    total_correct = 0
    for label, row in audit_dict["by_class"].items():
        acc = row["accuracy"]
        print(
            f"{label:12s} {row['pixels']:10d} {row['correct']:10d} "
            f"{acc * 100:9.1f}%"
        )
        total_pixels += row["pixels"]
        total_correct += row["correct"]
    print("-" * 60)
    overall = (total_correct / total_pixels) if total_pixels else 0.0
    print(f"{'OVERALL':12s} {total_pixels:10d} {total_correct:10d} "
          f"{overall * 100:9.1f}%")

    # Per-kind breakdown
    print("\nPer (kind, label) breakdown:")
    print("=" * 78)
    print(f"{'kind':20s} {'label':12s} {'pixels':>10s} {'correct':>10s} {'accuracy':>10s}")
    print("-" * 78)
    by_kind_class = audit_dict["by_kind_class"]
    # Group by kind
    kinds_seen: List[str] = []
    for key in by_kind_class:
        kind = key.split("/", 1)[0]
        if kind not in kinds_seen:
            kinds_seen.append(kind)
    for kind in kinds_seen:
        kind_total = 0
        kind_correct = 0
        for label in TERRAIN_CLASSES:
            key = f"{kind}/{label}"
            row = by_kind_class.get(key)
            if not row or row["pixels"] == 0:
                continue
            acc = row["accuracy"]
            print(
                f"{kind:20s} {label:12s} {row['pixels']:10d} {row['correct']:10d} "
                f"{acc * 100:9.1f}%"
            )
            kind_total += row["pixels"]
            kind_correct += row["correct"]
        if kind_total:
            k_overall = kind_correct / kind_total
            print(f"{kind:20s} {'(subtotal)':12s} {kind_total:10d} {kind_correct:10d} "
                  f"{k_overall * 100:9.1f}%")
            print("-" * 78)


# ============================================================
# CLI
# ============================================================


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument(
        "--labels",
        default="docs/路线/参考调研/battle-map-references/map_region_labels.jsonl",
        help="Path to the JSONL produced by label_map_regions.py.",
    )
    p.add_argument(
        "--root",
        default="docs/路线/参考调研/battle-map-references/images",
        help="Image root used to resolve relative paths in the JSONL.",
    )
    p.add_argument(
        "--out",
        default="docs/路线/参考调研/battle-map-references/derived_palette.json",
        help="Where to write the derived palette.",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if not os.path.exists(args.labels):
        print(f"labels file not found: {args.labels}", file=sys.stderr)
        return 1

    records = _load_labels(args.labels)
    if not records:
        print("no labelled records found", file=sys.stderr)
        return 1
    print(f"loaded {len(records)} labelled images")

    palette = derive(records, args.root)
    _print_palette(palette)

    audit_summary = audit(records, palette, args.root)
    _print_audit(audit_summary)

    payload = {
        "version": 1,
        "source_labels": os.path.relpath(args.labels),
        "n_records": len(records),
        "palette": palette,
        "audit": audit_summary,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    if not args.quiet:
        print(f"\nwrote {args.out}")

    # Friendly next-step hint
    by_class = audit_summary.get("by_class", {}) if audit_summary else {}
    overall = (by_class and (
        sum(r["correct"] for r in by_class.values())
        / max(1, sum(r["pixels"] for r in by_class.values()))
    ))
    if overall is not None:
        if overall < 0.80:
            print(
                "\n[!]  accuracy < 80% — add more regions (especially for low-scoring classes) "
                "and re-run this script."
            )
        elif overall < 0.90:
            print(
                "\n[i]  accuracy 80-90% — usable; spot-check a few auto-classified maps before "
                "trusting the aggregate stats."
            )
        else:
            print(
                "\n[OK] accuracy >= 90% — palette is good. Re-run extract_map_features.py to "
                "refresh map_features.json."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
