#!/usr/bin/env python3
"""Quick map character distribution check."""
import json
from pathlib import Path

maps_dir = Path("game/maps")
for name in ["balanced_2p_15", "classic", "realistic_grass_2p_20",
             "test_arena_10x10_2v2", "realistic_snow_2p_20",
             "realistic_desert_2p_25"]:
    path = maps_dir / f"{name}.json"
    if not path.exists():
        print(f"{name:35} | NOT FOUND")
        continue
    with path.open(encoding="utf-8") as f:
        d = json.load(f)
    layout = "".join(d.get("layout", []))
    counts = {ch: layout.count(ch) for ch in "VCWFTGHP"}
    rows = len(d.get("layout", []))
    cols = len(d.get("layout", ["x"])[0]) if d.get("layout") else 0
    print(f"{name:35} | {rows}x{cols} | V={counts['V']} C={counts['C']} W={counts['W']} F={counts['F']} T={counts['T']} G={counts['G']} H={counts['H']} P={counts['P']}")
