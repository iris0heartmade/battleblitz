class_name MapLoader
extends RefCounted
## 纯数据解码：逻辑格、地形和原始子类型由正式高差棋盘呈现。

const _CASTLE_SUBTYPE_CHARS := {
	"f": "castle_floor", "w": "castle_wall", "t": "castle_throne",
	"d": "castle_door", "s": "castle_stairs", "V": "castle_vault",
	"F": "castle_floor", "W": "castle_wall", "T": "castle_throne",
	"D": "castle_door", "S": "castle_stairs", "v": "castle_vault",
}


static func apply_to_board(board: Node, map_json: Dictionary) -> Dictionary:
	# 公共兼容入口；正式Board使用decode_map，不再创建旧TileMap资源。
	return board.load_map(map_json)

static func decode_map(map_json: Dictionary) -> Dictionary:
	var size_dict: Dictionary = _size_dict(map_json)
	var width: int = int(size_dict.get("width", size_dict.get("size", Config.MAP_SIZE_DEFAULT)))
	var height: int = int(size_dict.get("height", size_dict.get("size", Config.MAP_SIZE_DEFAULT)))
	var biome: String = String(map_json.get("biome", Config.DEFAULT_BIOME))
	if biome not in Config.BIOMES:
		biome = Config.DEFAULT_BIOME

	var layout: Array = map_json.get("layout", [])
	if layout.size() != height:
		push_warning("MapLoader: layout rows %d != height %d" % [layout.size(), height])

	var tile_lookup: Dictionary = {}
	for y in height:
		if y >= layout.size():
			break
		var row: String = String(layout[y])
		for x in width:
			if x >= row.length():
				break
			var char_a: String = row[x]
			# 一格一字符；城堡旁的森林/村庄不是城堡子类型。
			var decoded := _decode_cell(char_a, "")
			tile_lookup[Vector2i(x, y)] = decoded
	# 服务端快照优先，避免城堡子类型被重新编码成双字符后错位。
	for source in map_json.get("tiles",[]):
		var p := Vector2i(int(source.x),int(source.y))
		if p.x>=0 and p.y>=0 and p.x<width and p.y<height:
			tile_lookup[p] = source.duplicate(true)

	return {
		"width": width,
		"height": height,
		"biome": biome,
		"initial_units": map_json.get("initial_units", []),
		"tile_lookup": tile_lookup,
	}


static func _decode_cell(char_a: String, char_b: String) -> Dictionary:
	var base: String = String(Config.TERRAIN_CHAR_TO_NAME.get(char_a, "plain"))
	if base == "castle" and char_b != "":
		var sub: String = String(_CASTLE_SUBTYPE_CHARS.get(char_b, "castle_floor"))
		return {"terrain": "castle", "subtype": sub}
	if base.begins_with("castle_") and char_b != "":
		return {"terrain": "castle", "subtype": base}
	return {"terrain": base, "subtype": ""}


static func _size_dict(map_json: Dictionary) -> Dictionary:
	if map_json.has("width") or map_json.has("height"):
		return {
			"width": int(map_json.get("width", Config.MAP_SIZE_DEFAULT)),
			"height": int(map_json.get("height", Config.MAP_SIZE_DEFAULT)),
		}
	var size_raw: Variant = map_json.get("size", Config.MAP_SIZE_DEFAULT)
	if typeof(size_raw) in [TYPE_INT,TYPE_FLOAT]:
		return {"width": int(size_raw), "height": int(size_raw)}
	if typeof(size_raw) == TYPE_DICTIONARY:
		return size_raw
	return {"width": Config.MAP_SIZE_DEFAULT, "height": Config.MAP_SIZE_DEFAULT}
