extends RefCounted
## Demo独立数据模型；所有坐标均为逻辑格，不受相机旋转影响。

const TERRAINS := ["grass", "rock", "sand", "water"]
var settings: Dictionary
var cells: Array = []
var undo_stack: Array = []
var redo_stack: Array = []
var revision := 0
var saved_revision := 0
var units: Array = []
var map_id := "height_sandbox"
var map_name := "高度试验场"
var rules: Dictionary
var sandbox_size := Vector2i.ZERO

func _init(config: Dictionary) -> void:
	settings = config.duplicate(true)
	sandbox_size = Vector2i(int(config.width),int(config.depth))
	rules = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/catalog.json"))
	make_sample()

func size() -> Vector2i:
	return Vector2i(int(settings.width), int(settings.depth))

func contains(p: Vector2i) -> bool:
	return p.x >= 0 and p.y >= 0 and p.x < size().x and p.y < size().y

func index(p: Vector2i) -> int:
	return p.y * size().x + p.x

func cell(p: Vector2i) -> Dictionary:
	return cells[index(p)]

func elevation(p: Vector2i) -> int:
	return int(cell(p).height)

func surface(p: Vector2i) -> Vector3:
	return Vector3(p.x * float(settings.cell_size), elevation(p) * float(settings.height_step), p.y * float(settings.cell_size))

func make_sample() -> void:
	settings.width = sandbox_size.x
	settings.depth = sandbox_size.y
	units.clear()
	map_id = "height_sandbox"
	map_name = "高度试验场"
	cells.clear()
	for y in size().y:
		for x in size().x:
			var h := clampi(4 - absi(x - 4) - absi(y - 4), 0, int(settings.max_height))
			if x >= 8 and y >= 7:
				h = -mini(4, 1 + mini(x - 8, y - 7))
			cells.append({"height": h, "terrain": "rock" if h >= 2 else ("sand" if h < 0 else "grass")})
	# 极限悬崖放在前侧：相邻两格分别为-5与+5。
	cells[index(Vector2i(8, 3))] = {"height": int(settings.min_height), "terrain": "water"}
	cells[index(Vector2i(9, 3))] = {"height": int(settings.max_height), "terrain": "rock"}
	undo_stack.clear()
	redo_stack.clear()
	revision = 0
	saved_revision = 0

func edit(p: Vector2i, height: int, terrain: String = "") -> bool:
	if not contains(p):
		return false
	var next := cell(p).duplicate(true)
	next.height = clampi(height, int(settings.min_height), int(settings.max_height))
	next.terrain = cell(p).terrain if terrain.is_empty() else terrain
	if next.terrain not in TERRAINS or next == cell(p):
		return false
	undo_stack.append({"index": index(p), "before": cell(p).duplicate(), "after": next.duplicate(), "revision": revision})
	redo_stack.clear()
	cells[index(p)] = next
	revision += 1
	return true

func undo() -> bool:
	if undo_stack.is_empty():
		return false
	var action: Dictionary = undo_stack.pop_back()
	cells[action.index] = action.before.duplicate()
	redo_stack.append(action)
	revision -= 1
	return true

func redo() -> bool:
	if redo_stack.is_empty():
		return false
	var action: Dictionary = redo_stack.pop_back()
	cells[action.index] = action.after.duplicate()
	undo_stack.append(action)
	revision += 1
	return true

func snapshot() -> Dictionary:
	return {"format": "battleblitz-height-demo", "version": 2, "width": size().x, "depth": size().y, "cells": cells.duplicate(true), "units": units.duplicate(true), "map_id": map_id, "map_name": map_name}

func restore(data: Variant) -> String:
	if not data is Dictionary:
		return "文件内容必须是地图对象"
	if data.get("format") != "battleblitz-height-demo" or not _integer(data.get("version")) or int(data.version) not in [1,2]:
		return "地图格式或版本不支持"
	for dimension in [data.get("width"), data.get("depth")]:
		if not _integer(dimension) or dimension < 1 or dimension > rules.max_map_dimension:
			return "地图尺寸不支持"
	var width := int(data.width)
	var depth := int(data.depth)
	var incoming: Variant = data.get("cells")
	if not incoming is Array or incoming.size() != width * depth:
		return "地块数量不正确"
	for entry in incoming:
		if not entry is Dictionary:
			return "地块数据不正确"
		var h: Variant = entry.get("height")
		if not (h is int or h is float) or not is_finite(float(h)):
			return "高度必须是整数"
		if float(h) != floorf(float(h)) or h < settings.min_height or h > settings.max_height:
			return "高度超出范围或不是整数"
		if entry.get("terrain") not in TERRAINS:
			return "包含未知地形"
		if entry.get("feature", "") not in rules.feature_names or entry.get("faction", "neutral") not in rules.factions:
			return "包含未知地貌或归属"
	var incoming_units: Variant = data.get("units", [])
	var unit_error := _validate_units(incoming_units, width, depth)
	if not unit_error.is_empty():
		return unit_error
	# JSON数字读回为浮点数；统一回整数高度，保持存读前后数据类型一致。
	var normalized: Array = []
	for entry in incoming:
		var normalized_cell: Dictionary = entry.duplicate(true)
		normalized_cell.height = int(entry.height)
		normalized.append(normalized_cell)
	# 所有验证结束后统一提交，非法单位或建筑不会造成半张地图被替换。
	settings.width = width
	settings.depth = depth
	cells = normalized
	units = []
	for source_unit in incoming_units:
		units.append({"x": int(source_unit.x), "y": int(source_unit.y), "type": String(source_unit.type), "color": String(source_unit.color), "level": int(source_unit.level)})
	map_id = String(data.get("map_id", "height_sandbox"))
	map_name = String(data.get("map_name", "高度试验场"))
	undo_stack.clear()
	redo_stack.clear()
	revision = 0
	saved_revision = 0
	return ""

func _integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floorf(float(value))

func _validate_units(incoming: Variant, width: int, depth: int) -> String:
	if not incoming is Array or incoming.size() > width * depth:
		return "预设单位数量不正确"
	var occupied: Dictionary = {}
	for entry in incoming:
		if not entry is Dictionary:
			return "预设单位数据不正确"
		for key in ["x", "y", "level"]:
			if not _integer(entry.get(key)):
				return "单位坐标与等级必须是整数"
		var p := Vector2i(int(entry.x), int(entry.y))
		if p.x < 0 or p.y < 0 or p.x >= width or p.y >= depth or occupied.has(p):
			return "单位坐标越界或重复"
		if entry.level < 1 or entry.level > 100 or entry.get("type") not in rules.unit_textures or entry.get("color") not in rules.hq_factions:
			return "单位兵种、等级或阵营不支持"
		occupied[p] = true
	return ""

func import_standard() -> String:
	var source: Variant = JSON.parse_string(FileAccess.get_file_as_string(String(rules.source_map)))
	var converted: Dictionary = preload("res://demos/height_map/preset_importer.gd").convert(source, rules)
	if not String(converted.error).is_empty():
		return converted.error
	return restore(converted.map)

func unit_at(p: Vector2i) -> Dictionary:
	for entry in units:
		if int(entry.x) == p.x and int(entry.y) == p.y:
			return entry
	return {}

func save_map(path: String) -> String:
	var temp_path := path + ".tmp"
	var file := FileAccess.open(temp_path, FileAccess.WRITE)
	if file == null:
		return "无法写入文件：%s" % error_string(FileAccess.get_open_error())
	file.store_string(JSON.stringify(snapshot(), "\t"))
	file.flush()
	var write_error := file.get_error()
	file.close()
	if write_error != OK:
		return "地图写入失败：%s" % error_string(write_error)
	var result := DirAccess.rename_absolute(ProjectSettings.globalize_path(temp_path), ProjectSettings.globalize_path(path))
	if result != OK:
		return "替换地图失败：%s" % error_string(result)
	saved_revision = revision
	return ""

func load_map(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return "无法打开地图：%s" % error_string(FileAccess.get_open_error())
	if file.get_length() > 1024 * 1024:
		return "地图文件超过大小限制"
	return restore(JSON.parse_string(file.get_as_text()))
