#!/usr/bin/env python3
"""Sync tile PNGs from the existing JS frontend into the Godot project.

Godot 4 expects assets to live under the project root so it can generate
`.import` sidecars on first open. The source-of-truth pixel art already
lives at `game/app/web/assets/tiles/` (kept in sync for the legacy web
client). This script copies the 70 PNGs into `godot-client/assets/tiles/`.

Run once after cloning; the destination is committed to git so the
Godot editor can open the project offline.

Usage:
    python godot-client/tools/sync_assets.py [--check]
        --check  Verify the destination is in sync; exit 1 if not.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "game" / "app" / "web" / "assets" / "tiles"
DST = REPO_ROOT / "godot-client" / "assets" / "tiles"


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--check", action="store_true",
		help="Verify dst matches src; exit 1 on mismatch.")
	args = parser.parse_args()

	if not SRC.is_dir():
		print(f"ERROR: source directory not found: {SRC}", file=sys.stderr)
		return 1

	src_pngs = sorted(SRC.glob("*.png"))
	if not src_pngs:
		print(f"ERROR: no PNGs found in {SRC}", file=sys.stderr)
		return 1

	if not args.check:
		DST.mkdir(parents=True, exist_ok=True)

	mismatches: list[str] = []
	copied = 0
	for png in src_pngs:
		dst_path = DST / png.name
		if not args.check:
			shutil.copy2(png, dst_path)
			copied += 1
			continue
		# --check mode: compare bytes.
		if not dst_path.is_file():
			mismatches.append(f"missing: {png.name}")
			continue
		with png.open("rb") as fa, dst_path.open("rb") as fb:
			if fa.read() != fb.read():
				mismatches.append(f"differs: {png.name}")

	if args.check:
		if mismatches:
			print(f"Tile asset drift detected ({len(mismatches)} files):")
			for m in mismatches:
				print(f"  - {m}")
			print("Run `python godot-client/tools/sync_assets.py` to fix.")
			return 1
		print(f"OK — {len(src_pngs)} tiles in sync.")
		return 0

	print(f"Copied {copied} tiles → {DST}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
