#!/usr/bin/env python3
"""Patch chapter_06_ai_takeover.gd battle_01 (current file content)."""
from pathlib import Path

path = Path("godot-client/tools/chapter_06_ai_takeover.gd")
src = path.read_text(encoding="utf-8")

# === Replace _make_battle_01_snapshots (current content) ===
old = '''func _make_battle_01_snapshots() -> Array:
	# 同前: 3 段, 但用一个数组演示 wave 触发
	return [
		_make_snapshot(9001, 1, [
			_make_unit(10, "warlock", "云", 3, 11, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 4, 12, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
			_make_unit(12, "archer", "红", 5, 12, 25, 25, 3, 3, 2, 2, [], "red"),
			_make_unit(13, "archer", "游骑", 2, 12, 22, 22, 3, 3, 2, 2, [], "red"),
			_make_unit(14, "knight", "近卫", 1, 12, 32, 32, 3, 3, 1, 1, ["guard"], "red"),
			_make_unit(15, "healer", "医师", 6, 12, 18, 18, 5, 3, 1, 1, ["heal"], "red"),
			_make_unit(16, "warlock", "术士", 7, 12, 22, 22, 7, 3, 1, 1, ["fireball"], "red"),
		], [
			_make_unit(20, "sniper", "敌方狙击", 14, 2, 22, 22, 3, 3, 3, 2, [], "blue"),
			_make_unit(21, "warlock", "敌方术士", 13, 1, 22, 22, 6, 3, 1, 1, [], "blue"),
		])
	]'''

new = '''func _make_battle_01_snapshots() -> Array:
	# 10x10 地图, 6 玩家全 HP, 1 个 1-HP 敌人在射程内
	return [
		_make_snapshot(9001, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
			_make_unit(12, "archer", "红", 3, 8, 25, 25, 3, 3, 3, 2, [], "red"),
			_make_unit(14, "knight", "近卫", 2, 7, 32, 32, 3, 3, 1, 1, ["guard"], "red"),
			_make_unit(15, "healer", "医师", 1, 7, 18, 18, 5, 3, 1, 1, ["heal"], "red"),
			_make_unit(16, "warlock", "术士", 3, 7, 22, 22, 7, 3, 1, 1, ["fireball"], "red"),
		], [
			_make_unit(20, "sniper", "敌方狙击", 5, 5, 1, 1, 3, 3, 3, 2, [], "blue"),
		])
	]'''

if old not in src:
    print("ERROR: old_b01 not found")
    import re
    for m in re.finditer(r'func _make_battle_01', src):
        print("found at", m.start())
        print(src[m.start():m.start()+1500])
    raise SystemExit(1)
src = src.replace(old, new)
path.write_text(src, encoding="utf-8")
print("patched battle_01")
