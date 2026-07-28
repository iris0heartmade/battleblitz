#!/usr/bin/env python3
"""
compare_gen_vs_reference.py — 对照"我们的生成器输出"和"参考图模型"。

为每一种 map style:
  1. 用该 style 跑 N 张生成图(同 seed 取平均)
  2. 用 quality.score_map 打分
  3. 跟同 kind 的参考图(features.json)的特征做"形状对比"

输出 docs/路线/参考调研/2026-07-22-地图评价对照表.md
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List

# Make ``game`` importable when running from the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))

from app.map_generation import MapGenerator  # noqa: E402
from app.map_generation.quality import score_map  # noqa: E402


def _load_reference_features() -> Dict[str, List[Dict[str, Any]]]:
    """Group map_features.json by kind for cross-comparison."""
    p = os.path.join(
        ROOT, "docs", "路线", "参考调研",
        "battle-map-references", "map_features.json",
    )
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fp:
        data = json.load(fp)
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for img in data.get("images", []):
        kind = img.get("path", "").split("/")[-2] if "/" in img.get("path", "") else "?"
        # Strip the "advance-wars-awbw" / "advance-wars" / "fire-emblem"
        # prefix to match MAP_STYLES keys.
        if "awbw" in kind:
            kind = "advance_wars_awbw"
        elif "fire-emblem" in kind:
            kind = "fire_emblem"
        elif "advance-wars" in kind:
            kind = "advance_wars"  # aggregate AW2+AWDS under "AW" for now
        by_kind.setdefault(kind, []).append(img.get("features", {}))
    return by_kind


def _score_style(
    style: str, size: int, n: int = 5, seed_base: int = 1,
) -> Dict[str, Any]:
    """Generate ``n`` maps of the given style and aggregate their scores."""
    total = Counter()
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        gen = MapGenerator(
            size=size, style=style, seed=seed_base + i,
            use_clusters=True, use_rivers=True,
            use_roads=True, use_buildings=True,
        )
        grid = gen.generate()
        rep = score_map(grid, gen.castle_positions, gen.size)
        rows.append({
            "fitness": rep.fitness,
            "soft": dict(rep.soft_scores),
            "hard": len(rep.hard_violations),
            "share": rep.features.get("terrain_share", {}),
        })
        total["fitness"] += rep.fitness
        for k, v in rep.soft_scores.items():
            total[k] += v
        total["hard"] += len(rep.hard_violations)
    avg = {k: total[k] / n for k in total}
    return {
        "style": style, "size": size, "n": n,
        "avg_fitness": avg["fitness"],
        "avg_hard": avg["hard"],
        "avg_soft": {k: avg[k] for k in avg if k.startswith("S")},
        "sample_share": rows[0]["share"] if rows else {},
    }


def _avg_share(features: List[Dict[str, Any]]) -> Dict[str, float]:
    """Average terrain_share across a list of reference features."""
    if not features:
        return {}
    keys = set()
    for f in features:
        keys.update(f.get("terrain_share", {}).keys())
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = sum(f.get("terrain_share", {}).get(k, 0) for f in features) / len(features)
    return out


def main() -> int:
    ref_by_kind = _load_reference_features()

    styles = [
        ("grass_outer", 15, "fire_emblem"),       # FE-style outdoor
        ("grass_outer", 20, "fire_emblem"),
        ("snow_outer", 15, "fire_emblem"),
        ("desert_outer", 20, "fire_emblem"),
        ("compact_outer", 15, "fire_emblem"),
        ("grass_outer", 15, "advance_wars_awbw"),  # AWBW 4p
        ("grass_outer", 20, "advance_wars"),      # AW outer
        ("castle_internal", 15, "fire_emblem"),
    ]
    print(f"\n{'='*78}\nGenerator vs reference comparison\n{'='*78}\n")

    rows = []
    for style, size, ref_kind in styles:
        gen = _score_style(style, size, n=5)
        ref_share = _avg_share(ref_by_kind.get(ref_kind, []))
        rows.append({
            "style": style, "size": size, "ref_kind": ref_kind,
            "gen_fitness": gen["avg_fitness"],
            "gen_hard": gen["avg_hard"],
            "gen_share": gen["sample_share"],
            "ref_share": ref_share,
            "gen_soft": gen["avg_soft"],
        })

    # Pretty-print a markdown table
    print(f"{'style':16s} {'size':>4s} {'kind':20s} "
          f"{'fitness':>7s} {'hard':>4s}   "
          f"{'plain':>5s} {'forest':>6s} {'water':>5s} {'mtn':>4s} {'road':>4s}")
    print("-" * 90)
    for r in rows:
        gs = r["gen_share"]
        rs = r["ref_share"]
        print(
            f"{r['style']:16s} {r['size']:4d} {r['ref_kind']:20s} "
            f"{r['gen_fitness']:7.3f} {int(round(r['gen_hard'])):4d}   "
            f"{gs.get('plain', 0) * 100:4.1f}% {gs.get('forest', 0) * 100:5.1f}% "
            f"{gs.get('river', 0) * 100:4.1f}% {gs.get('mountain', 0) * 100:3.1f}% "
            f"{gs.get('road', 0) * 100:3.1f}%"
        )
    print()
    print("Reference map average terrain shares (per kind):")
    for kind, feats in ref_by_kind.items():
        avg = _avg_share(feats)
        if not avg:
            continue
        print(f"\n  {kind} ({len(feats)} maps):")
        for k, v in sorted(avg.items(), key=lambda kv: -kv[1]):
            print(f"    {k:12s}: {v * 100:5.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
