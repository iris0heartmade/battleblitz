extends RefCounted
## 只适配本轮标准图的已知字符；未知字符明确拒绝，避免静默丢失地图语义。

static func convert(source: Variant, rules: Dictionary) -> Dictionary:
	if not source is Dictionary or not source.get("size") is Dictionary:
		return {"error": "原图尺寸缺失"}
	var width := int(source.size.get("width", 0))
	var depth := int(source.size.get("height", 0))
	if width < 1 or depth < 1 or width > int(rules.max_map_dimension) or depth > int(rules.max_map_dimension):
		return {"error": "原图尺寸不支持"}
	var layout: Variant = source.get("layout")
	if not layout is Array or layout.size() != depth:
		return {"error": "原图行数不正确"}
	var cells: Array = []
	var hq_index := 0
	for y in depth:
		if not layout[y] is String or layout[y].length() != width:
			return {"error": "原图列数不正确"}
		for x in width:
			var code: String = layout[y][x]
			if not rules.codes.has(code):
				return {"error": "尚不支持地形字符：%s，位置(%d,%d)" % [code,x,y]}
			var cell: Dictionary = rules.codes[code].duplicate(true)
			cell.faction = "neutral"
			if code == "H":
				if hq_index >= rules.hq_factions.size():
					return {"error": "城堡数量超过已配置席位"}
				cell.faction = rules.hq_factions[hq_index]
				hq_index += 1
			cells.append(cell)
	return {"error": "", "map": {"format": "battleblitz-height-demo", "version": 2, "width": width, "depth": depth, "cells": cells, "map_id": source.get("id", ""), "map_name": source.get("name", ""), "units": source.get("initial_units", []).duplicate(true)}}
