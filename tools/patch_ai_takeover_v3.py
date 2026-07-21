#!/usr/bin/env python3
"""Patch battle_02 + battle_03 to put enemies in attack range."""
from pathlib import Path

path = Path("godot-client/tools/chapter_06_ai_takeover.gd")
src = path.read_text(encoding="utf-8")

# === Battle 02: 玩家在 (1,8)(2,8), 敌人放射程内 (3,8)(3,7) ===
old_b02 = '''func _make_battle_02_snapshots() -> Array:
	# battle_02: defend 模式. 2 个 1-HP 敌人
	return [
		_make_snapshot(9002, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(20, "knight", "援军-1", 5, 4, 1, 1, 3, 3, 1, 1, [], "blue"),
			_make_unit(21, "knight", "援军-2", 5, 5, 1, 1, 3, 3, 1, 1, [], "blue"),
		])
	]'''

new_b02 = '''func _make_battle_02_snapshots() -> Array:
	# battle_02: defend 模式. 2 个 1-HP 敌人在射程内, AI 1 回合能清完
	return [
		_make_snapshot(9002, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(20, "knight", "援军-1", 3, 8, 1, 1, 3, 3, 1, 1, [], "blue"),
			_make_unit(21, "knight", "援军-2", 3, 7, 1, 1, 3, 3, 1, 1, [], "blue"),
		])
	]'''

if old_b02 not in src:
    print("ERROR: old_b02 not found")
    raise SystemExit(1)
src = src.replace(old_b02, new_b02)

# === Battle 03: boss 在 (3,8) ===
old_b03 = '''func _make_battle_03_snapshots() -> Array:
	# battle_03: boss 战. 1 个 1-HP boss
	return [
		_make_snapshot(9003, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 35, 35, 10, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 32, 32, 8, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(99, "knight", "kalde", 5, 5, 1, 1, 5, 4, 1, 1, ["heroic_strike"], "blue", true),
		])
	]'''

new_b03 = '''func _make_battle_03_snapshots() -> Array:
	# battle_03: boss 战. 1 个 1-HP boss 在射程内
	return [
		_make_snapshot(9003, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 35, 35, 10, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 32, 32, 8, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(99, "knight", "kalde", 3, 8, 1, 1, 5, 4, 1, 1, ["heroic_strike"], "blue", true),
		])
	]'''

if old_b03 not in src:
    print("ERROR: old_b03 not found")
    raise SystemExit(1)
src = src.replace(old_b03, new_b03)

path.write_text(src, encoding="utf-8")
print("patched battle_02 + battle_03")
