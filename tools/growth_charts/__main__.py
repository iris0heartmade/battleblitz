"""CLI entry point.

Usage examples
--------------
::

    # default — all classes + heroes, autolevel_boss policy, Lv 1..20
    python -m tools.growth_charts

    # custom output dir + max level
    python -m tools.growth_charts --out docs/成长/growth_charts --max-level 20

    # only classes
    python -m tools.growth_charts --entities classes

    # future policy (once added)
    python -m tools.growth_charts --policy curve_linear
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

# Make the project importable when invoked from any cwd.
# Layout: tools/growth_charts/__main__.py  →  one dirname up is "tools",
# two dirname ups is REPO_ROOT (= battleblitz/).  GAME_DIR sits inside.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
GAME_DIR = os.path.join(REPO_ROOT, "game")
for path in (REPO_ROOT, GAME_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.progression.policies import get_policy  # noqa: E402
from tools.growth_charts.dataset import (  # noqa: E402
    all_class_curves,
    all_hero_curves,
)
from tools.growth_charts.render import render_class_growth  # noqa: E402


# ============================================================
# Defaults
# ============================================================

DEFAULT_OUT = os.path.join(REPO_ROOT, "tools", "growth_charts")


# ============================================================
# Argparse
# ============================================================

def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="growth_charts",
        description="Generate per-class / per-hero stat-growth PNG charts.",
    )
    p.add_argument("--out", default=DEFAULT_OUT,
                   help="Output root directory (default: tools/growth_charts)")
    p.add_argument("--policy", default="battle_lane",
                   help="Growth policy name (default: battle_lane)")
    p.add_argument("--max-level", type=int, default=20,
                   help="Max level to plot (default: 20)")
    p.add_argument("--entities", choices=["all", "classes", "heroes"], default="all",
                   help="Which entities to render (default: all)")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-file logging.")
    return p.parse_args(argv)


# ============================================================
# Main
# ============================================================

def main(argv: List[str] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    policy = get_policy(args.policy)

    classes_dir = os.path.join(args.out, "classes")
    heroes_dir = os.path.join(args.out, "heroes")

    index: list = []

    if args.entities in ("all", "classes"):
        class_curves = all_class_curves(max_level=args.max_level, policy=policy)
        if not args.quiet:
            print(f"[classes] rendering {len(class_curves)} unit classes with policy={args.policy} max_level={args.max_level}")
        for curve in class_curves:
            out = os.path.join(classes_dir, f"{curve.baseline.type_id}.png")
            render_class_growth(curve, output_path=out)
            if not args.quiet:
                print(f"  [ok] {os.path.relpath(out, REPO_ROOT)}")
            index.append({
                "kind": "class",
                "type_id": curve.baseline.type_id,
                "label_cn": curve.baseline.label_cn,
                "label_en": curve.baseline.label_en,
                "tier": curve.baseline.tier,
                "output": os.path.relpath(out, REPO_ROOT),
                "policy": args.policy,
                "max_level": args.max_level,
            })

    if args.entities in ("all", "heroes"):
        hero_curves = all_hero_curves(max_level=args.max_level, policy=policy)
        if not args.quiet:
            print(f"[heroes] rendering {len(hero_curves)} heroes with policy={args.policy} max_level={args.max_level}")
        for curve in hero_curves:
            out = os.path.join(heroes_dir, f"{curve.baseline.type_id}.png")
            render_class_growth(curve, output_path=out)
            if not args.quiet:
                print(f"  [ok] {os.path.relpath(out, REPO_ROOT)}")
            index.append({
                "kind": "hero",
                "hero_id": curve.baseline.type_id,
                "label_cn": curve.baseline.label_cn,
                "label_en": curve.baseline.label_en,
                "base_class_id": curve.baseline.base_class_id,
                "output": os.path.relpath(out, REPO_ROOT),
                "policy": args.policy,
                "max_level": args.max_level,
            })

    # Index — JSON metadata for every chart, useful for future web
    # gallery and for diff-checking output determinism.
    index_path = os.path.join(args.out, "index.json")
    os.makedirs(args.out, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    if not args.quiet:
        print(f"\nindex → {os.path.relpath(index_path, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
