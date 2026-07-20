extends RefCounted

const SEAT_COLORS := ["red", "blue", "green", "yellow"]
const NEUTRAL_LABEL := "中立"
const COLOR_LABELS := {
	"red": "红方",
	"blue": "蓝方",
	"green": "绿方",
	"yellow": "黄方",
}
const UNIT_LABELS := {
	"swordsman": "剑",
	"archer": "弓",
	"knight": "骑",
	"healer": "疗",
	"warlock": "术",
}
const BUILDING_CHARS := {
	"H": "hq",
	"C": "castle",
	"v": "village",
	"b": "barracks",
	"$": "castle_vault",
}
const TERRAIN_COLORS := {
	"P": Color(0.42, 0.62, 0.34),
	"F": Color(0.14, 0.34, 0.19),
	"M": Color(0.46, 0.43, 0.38),
	"S": Color(0.82, 0.78, 0.58),
	"R": Color(0.35, 0.25, 0.18),
	"r": Color(0.48, 0.36, 0.24),
	"H": Color(0.56, 0.48, 0.34),
	"C": Color(0.42, 0.39, 0.34),
	"v": Color(0.62, 0.45, 0.26),
	"b": Color(0.38, 0.35, 0.32),
	"$": Color(0.72, 0.58, 0.24),
}
const PLAYER_COLORS := {
	"red": Color(0.84, 0.2, 0.16),
	"blue": Color(0.18, 0.38, 0.86),
	"green": Color(0.18, 0.6, 0.28),
	"yellow": Color(0.88, 0.72, 0.18),
}


static func summarize_map(map_data: Dictionary) -> Dictionary:
	var size: Dictionary = _size_dict(map_data)
	var width := int(size.get("width", 0))
	var height := int(size.get("height", 0))
	var layout: Array = map_data.get("layout", []) if map_data.get("layout", []) is Array else []
	var hqs := _collect_hqs(layout)
	var players := int(map_data.get("recommended_players", hqs.size()))
	if players <= 0:
		players = mini(maxi(hqs.size(), 2), SEAT_COLORS.size())
	players = mini(players, SEAT_COLORS.size())
	var summary := {
		"id": str(map_data.get("id", "")),
		"name": str(map_data.get("name", map_data.get("id", ""))),
		"width": width,
		"height": height,
		"recommended_players": players,
		"factions": {},
		"neutral_buildings": {
			"village": 0,
			"barracks": 0,
			"castle_vault": 0,
		},
	}
	for i in range(players):
		var color: String = SEAT_COLORS[i]
		summary["factions"][color] = {
			"hq": 0,
			"castle": 0,
			"village": 0,
			"barracks": 0,
			"castle_vault": 0,
			"units": 0,
			"unit_types": {},
		}
	for i in range(mini(hqs.size(), players)):
		var color: String = SEAT_COLORS[i]
		summary["factions"][color]["hq"] = int(summary["factions"][color].get("hq", 0)) + 1
	_count_buildings(layout, hqs, summary)
	_count_neutral_buildings(layout, summary)
	_count_units(map_data, summary)
	return summary


static func build_faction_lines(summary: Dictionary) -> String:
	var factions: Dictionary = summary.get("factions", {})
	var lines: Array[String] = []
	for color in SEAT_COLORS:
		if not factions.has(color):
			continue
		var item: Dictionary = factions[color]
		var unit_text: String = _format_unit_types(item.get("unit_types", {}))
		var line: String = "%s  总部%d  村%d  佣兵站%d  单位%d" % [
			COLOR_LABELS.get(color, color),
			int(item.get("hq", 0)),
			int(item.get("village", 0)),
			int(item.get("barracks", 0)),
			int(item.get("units", 0)),
		]
		var vault_count: int = int(item.get("castle_vault", 0))
		if vault_count > 0:
			line += "  金库%d" % vault_count
		if unit_text != "":
			line += "  %s" % unit_text
		lines.append(line)
	var neutral_line := _format_neutral_buildings(summary.get("neutral_buildings", {}))
	if neutral_line != "":
		lines.append(neutral_line)
	return "\n".join(lines)


static func render_preview_texture(map_data: Dictionary, cell_px: int = 9) -> ImageTexture:
	var size: Dictionary = _size_dict(map_data)
	var width: int = max(1, int(size.get("width", 1)))
	var height: int = max(1, int(size.get("height", 1)))
	var layout: Array = map_data.get("layout", []) if map_data.get("layout", []) is Array else []
	var img: Image = Image.create(width * cell_px, height * cell_px, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.08, 0.08, 0.07, 1.0))
	for y in range(height):
		var row := ""
		if y < layout.size():
			row = str(layout[y])
		for x in range(width):
			var ch := "P"
			if x < row.length():
				ch = row.substr(x, 1)
			_fill_cell(img, x, y, cell_px, TERRAIN_COLORS.get(ch, TERRAIN_COLORS["P"]))
			if BUILDING_CHARS.has(ch):
				_draw_cell_outline(img, x, y, cell_px, Color(0.95, 0.86, 0.45))
	_draw_hq_seat_outlines(img, layout, cell_px)
	for unit in (map_data.get("initial_units", []) if map_data.get("initial_units", []) is Array else []):
		if not unit is Dictionary:
			continue
		var color := str(unit.get("color", "red"))
		var ux := int(unit.get("x", -1))
		var uy := int(unit.get("y", -1))
		if ux < 0 or uy < 0:
			continue
		_draw_unit_marker(img, ux, uy, cell_px, PLAYER_COLORS.get(color, Color.WHITE))
	return ImageTexture.create_from_image(img)


static func _size_dict(map_data: Dictionary) -> Dictionary:
	if map_data.has("width") or map_data.has("height"):
		return {
			"width": int(map_data.get("width", 0)),
			"height": int(map_data.get("height", 0)),
		}
	var raw: Variant = map_data.get("size", {})
	if raw is Dictionary:
		return raw
	if typeof(raw) == TYPE_INT or typeof(raw) == TYPE_FLOAT:
		var n := int(raw)
		return {"width": n, "height": n}
	return {"width": 0, "height": 0}


static func _collect_hqs(layout: Array) -> Array[Vector2i]:
	var hqs: Array[Vector2i] = []
	for y in range(layout.size()):
		var row := str(layout[y])
		for x in range(row.length()):
			var ch := row.substr(x, 1)
			if ch == "H" or ch == "C":
				hqs.append(Vector2i(x, y))
	return hqs


static func _count_buildings(layout: Array, hqs: Array[Vector2i], summary: Dictionary) -> void:
	var factions: Dictionary = summary.get("factions", {})
	for y in range(layout.size()):
		var row := str(layout[y])
		for x in range(row.length()):
			var ch := row.substr(x, 1)
			if not BUILDING_CHARS.has(ch):
				continue
			var kind := str(BUILDING_CHARS[ch])
			if kind == "hq":
				continue
			var color := _nearest_hq_color(Vector2i(x, y), hqs, factions.size())
			if color == "" or not factions.has(color):
				continue
			factions[color][kind] = int(factions[color].get(kind, 0)) + 1


static func _count_neutral_buildings(layout: Array, summary: Dictionary) -> void:
	var totals := {
		"village": 0,
		"barracks": 0,
		"castle_vault": 0,
	}
	for y in range(layout.size()):
		var row := str(layout[y])
		for x in range(row.length()):
			var ch := row.substr(x, 1)
			if not BUILDING_CHARS.has(ch):
				continue
			var kind := str(BUILDING_CHARS[ch])
			if totals.has(kind):
				totals[kind] = int(totals.get(kind, 0)) + 1
	var factions: Dictionary = summary.get("factions", {})
	for color in factions.keys():
		var faction: Dictionary = factions[color]
		for kind in totals.keys():
			totals[kind] = max(0, int(totals.get(kind, 0)) - int(faction.get(kind, 0)))
	summary["neutral_buildings"] = totals


static func _count_units(map_data: Dictionary, summary: Dictionary) -> void:
	var factions: Dictionary = summary.get("factions", {})
	var units: Array = map_data.get("initial_units", []) if map_data.get("initial_units", []) is Array else []
	for unit in units:
		if not unit is Dictionary:
			continue
		var color := str(unit.get("color", ""))
		if not factions.has(color):
			continue
		var type_id := str(unit.get("type", unit.get("unit_type", "unit")))
		factions[color]["units"] = int(factions[color].get("units", 0)) + 1
		var types: Dictionary = factions[color].get("unit_types", {})
		types[type_id] = int(types.get(type_id, 0)) + 1
		factions[color]["unit_types"] = types


static func _nearest_hq_color(pos: Vector2i, hqs: Array[Vector2i], player_count: int) -> String:
	var best_index := -1
	var best_distance := 999999
	for i in range(mini(hqs.size(), player_count)):
		var hq: Vector2i = hqs[i]
		var dist: int = abs(pos.x - hq.x) + abs(pos.y - hq.y)
		if dist < best_distance:
			best_distance = dist
			best_index = i
	if best_index < 0 or best_index >= SEAT_COLORS.size():
		return ""
	return SEAT_COLORS[best_index]


static func _format_unit_types(types_value: Variant) -> String:
	if not types_value is Dictionary:
		return ""
	var types: Dictionary = types_value
	var parts: Array[String] = []
	for type_id in types.keys():
		parts.append("%s%d" % [UNIT_LABELS.get(str(type_id), str(type_id)), int(types[type_id])])
	return "/".join(parts)


static func _format_neutral_buildings(value: Variant) -> String:
	if not value is Dictionary:
		return ""
	var neutral: Dictionary = value
	var village_count := int(neutral.get("village", 0))
	var barracks_count := int(neutral.get("barracks", 0))
	var vault_count := int(neutral.get("castle_vault", 0))
	if village_count <= 0 and barracks_count <= 0 and vault_count <= 0:
		return "%s  村0  佣兵站0" % NEUTRAL_LABEL
	var line := "%s  村%d  佣兵站%d" % [NEUTRAL_LABEL, village_count, barracks_count]
	if vault_count > 0:
		line += "  金库%d" % vault_count
	return line


static func _fill_cell(img: Image, cell_x: int, cell_y: int, cell_px: int, color: Color) -> void:
	for py in range(cell_y * cell_px, (cell_y + 1) * cell_px):
		for px in range(cell_x * cell_px, (cell_x + 1) * cell_px):
			img.set_pixel(px, py, color)


static func _draw_cell_outline(img: Image, cell_x: int, cell_y: int, cell_px: int, color: Color) -> void:
	var left := cell_x * cell_px
	var top := cell_y * cell_px
	var right := left + cell_px - 1
	var bottom := top + cell_px - 1
	for px in range(left, right + 1):
		img.set_pixel(px, top, color)
		img.set_pixel(px, bottom, color)
	for py in range(top, bottom + 1):
		img.set_pixel(left, py, color)
		img.set_pixel(right, py, color)


static func _draw_hq_seat_outlines(img: Image, layout: Array, cell_px: int) -> void:
	var hqs: Array[Vector2i] = _collect_hqs(layout)
	for i in range(mini(hqs.size(), SEAT_COLORS.size())):
		var color: Color = PLAYER_COLORS.get(SEAT_COLORS[i], Color.WHITE)
		_draw_cell_outline(img, hqs[i].x, hqs[i].y, cell_px, color)


static func _draw_unit_marker(img: Image, cell_x: int, cell_y: int, cell_px: int, color: Color) -> void:
	var inset: int = max(1, int(cell_px / 3))
	var left: int = cell_x * cell_px + inset
	var top: int = cell_y * cell_px + inset
	var right: int = (cell_x + 1) * cell_px - inset - 1
	var bottom: int = (cell_y + 1) * cell_px - inset - 1
	for py in range(top, bottom + 1):
		for px in range(left, right + 1):
			if px >= 0 and py >= 0 and px < img.get_width() and py < img.get_height():
				img.set_pixel(px, py, color)
