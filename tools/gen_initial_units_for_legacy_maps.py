#!/usr/bin/env python3
"""
Generate initial_units for legacy map presets.

For each map JSON under game/maps/ that lacks initial_units, generate
a default set based on the map's castle positions and a classic roster.

Usage:
    python tools/gen_initial_units_for_legacy_maps.py [--dry-run] [--write]
"""
import argparse
import json
from pathlib import Path

MAPS_DIR = Path(__file__).resolve().parent.parent / "game" / "maps"

# Default classic roster per player
DEFAULT_ROSTER = {"swordsman": 2, "archer": 1, "knight": 1, "healer": 1}

# Castle positions for 15x15 maps (legacy)
CASTLE_POSITIONS = {
    2: [(2, 2), (12, 12)],
    3: [(2, 2), (12, 2), (7, 12)],
    4: [(2, 2), (12, 2), (2, 12), (12, 12)],
}

# Color order by seat
COLORS = ["red", "blue", "green", "yellow"]

# Spawn offsets (matching the old _spawn_xy_for_castle logic)
SPAWN_OFFSETS = [(0, 1), (1, 0), (1, 1), (2, 0), (0, 2)]


def _generate_units(castle_xy, color, roster):
    """Generate initial_units for one player at castle_xy."""
    units = []
    unit_index = 0
    for unit_type, count in roster.items():
        for _ in range(count):
            dx, dy = SPAWN_OFFSETS[unit_index % len(SPAWN_OFFSETS)]
            x = castle_xy[0] + dx
            y = castle_xy[1] + dy
            units.append({
                "x": x, "y": y,
                "type": unit_type,
                "color": color,
                "level": 1,
            })
            unit_index += 1
    return units


def main():
    parser = argparse.ArgumentParser(description="Generate initial_units for legacy maps")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write")
    parser.add_argument("--write", action="store_true", help="Write changes to files")
    args = parser.parse_args()

    for json_path in sorted(MAPS_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if "initial_units" in data:
            continue  # already migrated

        num_players = data.get("recommended_players", 2)
        castles = CASTLE_POSITIONS.get(num_players, CASTLE_POSITIONS[2])
        initial_units = []
        for seat, castle in enumerate(castles):
            color = COLORS[seat] if seat < len(COLORS) else COLORS[-1]
            initial_units.extend(_generate_units(castle, color, DEFAULT_ROSTER))

        data["initial_units"] = initial_units
        data["notes"] = data.get("notes", "") + " [initial_units auto-generated]"
        data["notes"] = data["notes"].strip()

        if args.dry_run:
            print(f"[DRY RUN] {json_path.name}: {len(initial_units)} units added")
        elif args.write:
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[WRITTEN] {json_path.name}: {len(initial_units)} units")
        else:
            print(f"[SKIP] {json_path.name}: {len(initial_units)} units would be added (use --write)")


if __name__ == "__main__":
    main()
