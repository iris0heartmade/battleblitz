class_name MapLoader
extends RefCounted
## MapLoader translates BattleBlitz map JSON into layer-aware TileMap
## writes plus unit placement metadata for the Board scene.

const MAP_THEME_SCRIPT := preload("res://scripts/core/map_theme.gd")

const _CASTLE_SUBTYPE_CHARS := {
	"f": "castle_floor", "w": "castle_wall", "t": "castle_throne",
	"d": "castle_door", "s": "castle_stairs", "V": "castle_vault",
	"F": "castle_floor", "W": "castle_wall", "T": "castle_throne",
	"D": "castle_door", "S": "castle_stairs", "v": "castle_vault",
}


static func apply_to_board(board: Node, map_json: Dictionary) -> Dictionary:
	var size_dict: Dictionary = _size_dict(map_json)
	var width: int = int(size_dict.get("width", size_dict.get("size", Config.MAP_SIZE_DEFAULT)))
	var height: int = int(size_dict.get("height", size_dict.get("size", Config.MAP_SIZE_DEFAULT)))
	var biome: String = String(map_json.get("biome", Config.DEFAULT_BIOME))
	if biome not in Config.BIOMES:
		biome = Config.DEFAULT_BIOME

	var layout: Array = map_json.get("layout", [])
	if layout.size() != height:
		push_warning("MapLoader: layout rows %d != height %d" % [layout.size(), height])

	board.ground_layer.clear()
	board.structure_layer.clear()
	board.decor_layer.clear()

	var tile_lookup: Dictionary = {}
	for y in height:
		if y >= layout.size():
			break
		var row: String = String(layout[y])
		for x in width:
			if x >= row.length():
				break
			var char_a: String = row[x]
			var char_b: String = ""
			if x + 1 < row.length() and _CASTLE_SUBTYPE_CHARS.has(row[x + 1]):
				char_b = row[x + 1]
			var decoded := _decode_cell(char_a, char_b)
			var terrain: String = String(decoded["terrain"])
			var subtype: String = String(decoded["subtype"])
			var layer_kind: int = MAP_THEME_SCRIPT.layer_for_cell(terrain, subtype)
			_apply_ground_cell(board.ground_layer, x, y, terrain, subtype, biome)
			if layer_kind == MAP_THEME_SCRIPT.LayerKind.STRUCTURE:
				_apply_layer_cell(board.structure_layer, x, y, MAP_THEME_SCRIPT.source_lookup_key(terrain, subtype), biome)
			elif layer_kind == MAP_THEME_SCRIPT.LayerKind.DECOR:
				_apply_layer_cell(board.decor_layer, x, y, MAP_THEME_SCRIPT.source_lookup_key(terrain, subtype), biome)
			tile_lookup[Vector2i(x, y)] = decoded

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
	var size_raw: Variant = map_json.get("size", Config.MAP_SIZE_DEFAULT)
	if typeof(size_raw) == TYPE_INT:
		return {"width": int(size_raw), "height": int(size_raw)}
	if typeof(size_raw) == TYPE_DICTIONARY:
		return size_raw
	return {"width": Config.MAP_SIZE_DEFAULT, "height": Config.MAP_SIZE_DEFAULT}


static func _apply_ground_cell(layer: TileMapLayer, x: int, y: int, terrain: String, subtype: String, biome: String) -> void:
	var ground_key := MAP_THEME_SCRIPT.ground_lookup_key(terrain, subtype)
	_apply_layer_cell(layer, x, y, ground_key, biome)


static func _apply_layer_cell(layer: TileMapLayer, x: int, y: int, terrain_key: String, biome: String) -> void:
	var lookup_biome := biome if MAP_THEME_SCRIPT.uses_biome(terrain_key) else ""
	var source_id: int = TileSetBuilder.source_id_for(terrain_key, lookup_biome)
	if source_id < 0:
		source_id = TileSetBuilder.source_id_for(terrain_key, Config.DEFAULT_BIOME)
	if source_id < 0:
		push_warning("MapLoader: no source for %s (%s)" % [terrain_key, biome])
		return
	if Config.FE8_TILE_COORDS.has(terrain_key):
		var atlas_coord: Vector2i = Config.FE8_TILE_COORDS[terrain_key]
		layer.set_cell(Vector2i(x, y), source_id, atlas_coord, 0)
		return
	var n_variants: int = int(Config.TERRAIN_VARIANT_COUNTS.get(terrain_key, 1))
	var variant: int = Config.pick_tile_variant(terrain_key, x, y)
	if n_variants <= 0:
		variant = 0
	elif variant >= n_variants:
		variant = variant % n_variants
	layer.set_cell(Vector2i(x, y), source_id, Vector2i(0, 0), variant)
