class_name MapLoader
extends RefCounted
## MapLoader — translate a map JSON file into `TileMapLayer.set_cell`
## calls on a `Board` scene. One map JSON, one TileMapLayer (terrain)
## + one optional CastleLayer (sub-features).
##
## The map JSON schema is defined in `docs/路线/Godot移植方案.md` §6.1
## and the source of truth lives in
## `game/app/map_generation/generator.py` (server-side generator).
##
## Layout encoding (per the Python docstring at game_logic.py:1391):
##   P = plain, F = forest, M = mountain, S = snow_peak, R = river,
##   C = castle, v = village, b = barracks, r = road, g = gate, j = bridge
##   Inside a castle cluster, the second char in the 2-char cell
##   encodes the sub-feature: f=castle_floor, w=castle_wall,
##   t=castle_throne, d=castle_door, s=castle_stairs, v2=castle_vault.
##   The generator uses upper/lower case for visual variety but both
##   decode to the same subtype.
##
## Initial units are stored but not yet rendered — UnitLayer is M2.

const _CASTLE_SUBTYPE_CHARS := {
	"f": "castle_floor", "w": "castle_wall", "t": "castle_throne",
	"d": "castle_door", "s": "castle_stairs", "V": "castle_vault",
	# Some maps use uppercase for the second char — same mapping.
	"F": "castle_floor", "W": "castle_wall", "T": "castle_throne",
	"D": "castle_door", "S": "castle_stairs", "v": "castle_vault",
}


# ============================================================
# Public entry point
# ============================================================

## Load `map_json` (a parsed Dictionary from a `game/maps/*.json`)
## into the provided `board` scene. The board must already have
## its `terrain_layer`, `castle_layer`, and `tile_set` wired up.
## Returns a Dictionary with `{ "width", "height", "biome",
## "initial_units", "tile_lookup" }` so callers can resolve
## `tile (x, y) -> { terrain, subtype }` cheaply.
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

	# 1. Clear any prior contents (in case the board is reused).
	var terrain_layer: TileMapLayer = board.terrain_layer
	var castle_layer: TileMapLayer = board.castle_layer
	terrain_layer.clear()
	if castle_layer != null:
		castle_layer.clear()

	# 2. Walk every cell of the layout.
	var tile_lookup: Dictionary = {}      # Vector2i -> {terrain, subtype}
	for y in height:
		if y >= layout.size():
			break
		var row: String = String(layout[y])
		for x in width:
			if x >= row.length():
				break
			var char_a: String = row[x]
			var char_b: String = ""
			# 2-char castle cluster encoding: take 2 chars when the
			# row column at x+1 looks like a subtype marker.
			if x + 1 < row.length() and _CASTLE_SUBTYPE_CHARS.has(row[x + 1]):
				char_b = row[x + 1]
			var decoded := _decode_cell(char_a, char_b)
			var terrain: String = decoded["terrain"]
			var subtype: String = decoded["subtype"]
			_apply_terrain_cell(terrain_layer, x, y, terrain, biome)
			if subtype != "" and castle_layer != null:
				_apply_terrain_cell(castle_layer, x, y, subtype, biome)
			tile_lookup[Vector2i(x, y)] = decoded

	# 3. Centre the camera on the board.
	board.center_camera_on_board(width, height)

	return {
		"width": width,
		"height": height,
		"biome": biome,
		"initial_units": map_json.get("initial_units", []),
		"tile_lookup": tile_lookup,
	}


# ============================================================
# Decoding
# ============================================================

## Decode a (char_a, char_b) pair into {terrain, subtype}.
##   char_a = base terrain letter (P / F / M / S / R / C / v / b / r / g / j)
##   char_b = empty, or a castle sub-feature marker
static func _decode_cell(char_a: String, char_b: String) -> Dictionary:
	# Explicit String annotation: Dictionary.get() returns Variant in
	# Godot 4, so `:=` would infer as Variant (warning-as-error here).
	var base: String = String(Config.TERRAIN_CHAR_TO_NAME.get(char_a, "plain"))
	if base == "castle" and char_b != "":
		var sub: String = String(_CASTLE_SUBTYPE_CHARS.get(char_b, "castle_floor"))
		return {"terrain": "castle", "subtype": sub}
	if base.begins_with("castle_") and char_b != "":
		# Defensive: a map that puts a 2-char castle cluster starting
		# with `C` and then `f` etc. Already handled above.
		return {"terrain": "castle", "subtype": base}
	return {"terrain": base, "subtype": ""}

## Pull a `{width, height}` out of the `size` field, which the schema
## permits as either an int (square) or a dict.
static func _size_dict(map_json: Dictionary) -> Dictionary:
	# `map_json.get()` returns Variant. Branch by runtime type to give
	# callers a uniform `{width, height}` dict.
	var size_raw: Variant = map_json.get("size", Config.MAP_SIZE_DEFAULT)
	if typeof(size_raw) == TYPE_INT:
		return {"width": int(size_raw), "height": int(size_raw)}
	if typeof(size_raw) == TYPE_DICTIONARY:
		return size_raw
	return {"width": Config.MAP_SIZE_DEFAULT, "height": Config.MAP_SIZE_DEFAULT}


# ============================================================
# Cell writing
# ============================================================

static func _apply_terrain_cell(layer: TileMapLayer, x: int, y: int, terrain: String, biome: String) -> void:
	# Non-biome-aware terrains (plain / mountain / road / ...) are
	# registered in TileSetBuilder with an EMPTY biome key.
	var lookup_biome: String = biome
	if terrain not in Config.BIOME_AWARE_TERRAINS:
		lookup_biome = ""
	var source_id: int = TileSetBuilder.source_id_for(terrain, lookup_biome)
	if source_id < 0:
		# Last-ditch: try the default biome.
		source_id = TileSetBuilder.source_id_for(terrain, Config.DEFAULT_BIOME)
	if source_id < 0:
		return
	# FE8 atlas branch: use the (col, row) tile coord from
	# Config.FE8_TILE_COORDS. variant is unused (always 0) since the
	# FE8 atlas doesn't have per-terrain alt-tiles.
	if terrain in Config.FE8_TILE_COORDS:
		var atlas_coord: Vector2i = Config.FE8_TILE_COORDS[terrain]
		layer.set_cell(Vector2i(x, y), source_id, atlas_coord, 0)
		return
	# Legacy per-terrain atlas: variant is the alternative_tile index.
	# CRITICAL: pass `Vector2i(0, 0)` as the atlas coord and `variant`
	# as the alternative_tile parameter, not the other way around.
	var n_variants: int = int(Config.TERRAIN_VARIANT_COUNTS.get(terrain, 1))
	var variant: int = Config.pick_tile_variant(terrain, x, y)
	if n_variants <= 0:
		variant = 0
	elif variant >= n_variants:
		variant = variant % n_variants
	layer.set_cell(Vector2i(x, y), source_id, Vector2i(0, 0), variant)
