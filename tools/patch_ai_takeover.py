#!/usr/bin/env python3
"""Patch chapter_06_ai_takeover.gd to use:
- test_arena_10x10_2v2 map (no villages/castles)
- Enemy units all 1 HP (AI can 1-shot them)
- Smaller battle sizes
"""
from pathlib import Path

path = Path("godot-client/tools/chapter_06_ai_takeover.gd")
src = path.read_text(encoding="utf-8")

# === Replace _make_battle_01_snapshots ===
old_b01 = '''func _make_battle_01_snapshots() -> Array:
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
			_make_unit(20, "sniper", "方标狙", 14, 2, 22, 22, 3, 3, 3, 2, [], "blue"),
			_make_unit(21, "warlock", "方术士", 13, 1, 22, 22, 6, 3, 1, 1, [], "blue"),
		])
	]'''

new_b01 = '''func _make_battle_01_snapshots() -> Array:
	# 10x10 地图, 6 玩家全 HP, 1 个 1-HP 敌人在射程内
	# AI 跑 2-3 回合就能赢
	return [
		_make_snapshot(9001, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
			_make_unit(12, "archer", "红", 3, 8, 25, 25, 3, 3, 3, 2, [], "red"),
			_make_unit(14, "knight", "近卫", 2, 7, 32, 32, 3, 3, 1, 1, ["guard"], "red"),
			_make_unit(15, "healer", "医师", 1, 7, 18, 18, 5, 3, 1, 1, ["heal"], "red"),
			_make_unit(16, "warlock", "术士", 3, 7, 22, 22, 7, 3, 1, 1, ["fireball"], "red"),
		], [
			_make_unit(20, "sniper", "方标狙", 5, 5, 1, 1, 3, 3, 3, 2, [], "blue"),
		])
	]'''

assert old_b01 in src, "old_b01 not found"
src = src.replace(old_b01, new_b01)

# === Replace _make_battle_02_snapshots ===
old_b02 = '''func _make_battle_02_snapshots() -> Array:
	return [
		_make_snapshot(9002, 1, [
			_make_unit(10, "warlock", "云", 3, 11, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 4, 12, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
			_make_unit(14, "knight", "近卫", 1, 12, 32, 32, 3, 3, 1, 1, ["guard"], "red"),
			_make_unit(15, "healer", "医师", 6, 12, 18, 18, 5, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(22, "knight", "援军-1", 0, 7, 30, 30, 3, 3, 1, 1, [], "blue"),
			_make_unit(23, "knight", "援军-2", 0, 5, 30, 30, 3, 3, 1, 1, [], "blue"),
			_make_unit(24, "knight", "援军-3", 0, 9, 30, 30, 3, 3, 1, 1, [], "blue"),
		])
	]'''

new_b02 = '''func _make_battle_02_snapshots() -> Array:
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

assert old_b02 in src, "old_b02 not found"
src = src.replace(old_b02, new_b02)

# === Replace _make_battle_03_snapshots ===
old_b03 = '''func _make_battle_03_snapshots() -> Array:
	return [
		_make_snapshot(9003, 1, [
			_make_unit(10, "warlock", "云", 3, 11, 35, 35, 10, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 4, 12, 32, 32, 8, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(99, "knight", "kalde", 7, 7, 80, 80, 5, 4, 1, 1, ["heroic_strike"], "blue", true),
			_make_unit(60, "knight", "kalde-副将", 9, 7, 50, 50, 4, 3, 1, 1, ["guard"], "blue"),
			_make_unit(61, "knight", "kalde-副将", 5, 7, 50, 50, 4, 3, 1, 1, ["guard"], "blue"),
		])
	]'''

new_b03 = '''func _make_battle_03_snapshots() -> Array:
	# battle_03: boss 战. 1 个 1-HP boss
	return [
		_make_snapshot(9003, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 35, 35, 10, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 32, 32, 8, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(99, "knight", "kalde", 5, 5, 1, 1, 5, 4, 1, 1, ["heroic_strike"], "blue", true),
		])
	]'''

assert old_b03 in src, "old_b03 not found"
src = src.replace(old_b03, new_b03)

path.write_text(src, encoding="utf-8")
print("patched 3 snapshot factories")
