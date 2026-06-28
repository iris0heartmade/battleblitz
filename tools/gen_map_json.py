"""One-shot tool: write map preset JSON files from the existing hardcoded
_layout builders in game/app/game_logic.py.

Run from repo root:  python tools/gen_map_json.py

Reads the source of game_logic.py, extracts the _build_*() functions,
executes them in a sandbox, and writes one JSON file per preset to
game/maps/. After verifying, the hardcoded builders in game_logic.py
can be deleted.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAME_LOGIC = REPO / "game" / "app" / "game_logic.py"
OUT_DIR = REPO / "game" / "maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_layouts() -> dict[str, list[list[str]]]:
    """Pull _build_*() functions out of game_logic.py and run them."""
    src = GAME_LOGIC.read_text(encoding="utf-8")

    # Grab from the "# Map presets" comment through the MAP_PRESETS dict end
    start = src.index("# Map presets")
    # MAP_PRESETS = { ... } block — find the closing brace at column 0
    mp_idx = src.index("MAP_PRESETS", start)
    end = src.index("\n}\n", mp_idx) + len("\n}\n")
    block = src[start:end]

    # Sandbox the builders (they only need MAP_SIZE + _preset helpers)
    ns: dict = {}
    from app.config import MAP_SIZE  # type: ignore  # noqa
    ns["MAP_SIZE"] = MAP_SIZE
    ns["_preset"] = lambda id_, name, desc, layout: {  # stub (not used at extraction time)
        "id": id_, "name": name, "description": desc, "layout": layout,
    }

    # Pull out each _build_* function and exec it
    pattern = re.compile(r"^def (_build_\w+)\(.*?\n(?=^def |\Z)", re.M | re.S)
    for m in pattern.finditer(block):
        fn_name = m.group(1)
        exec(m.group(0), ns)
        layout = ns[fn_name]()  # type: ignore[index]
        # Convert List[List[str]] -> List[str] (rows as compact strings)
        rows = ["".join(row) for row in layout]
        yield fn_name.removeprefix("_build_"), rows


PRESET_META = {
    "open_plains":    ("开阔平原", "少障碍、易推进、弓兵强势"),
    "mountain_pass":  ("山地关口", "山脉横贯，狭窄通道决定胜负"),
    "river_crossing": ("河流分割", "对角线河流分割战场，需绕行或强渡"),
    "forest_ambush":  ("森林伏击", "中央密林，防御+2，远程受限"),
    "four_lakes":     ("四方水泽", "中央山地堡垒，四角河流阻隔"),
}


def main() -> None:
    layouts = list(extract_layouts())
    if not layouts:
        print("ERROR: no layouts extracted — check the block extraction regex")
        sys.exit(1)
    for preset_id, rows in layouts:
        name, desc = PRESET_META[preset_id]
        payload = {
            "id": preset_id,
            "name": name,
            "description": desc,
            "size": len(rows),
            "chars": {"P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle"},
            "layout": rows,
        }
        out = OUT_DIR / f"{preset_id}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(REPO)}  ({len(rows)}x{len(rows[0])})")


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "game"))
    main()