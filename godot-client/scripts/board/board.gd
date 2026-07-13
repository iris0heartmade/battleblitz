extends Node2D
class_name Board
## Board — the tile board scene. M1 renders a map JSON as a TileMap;
## M2 will add units, highlights, and click handling.
##
## Children (created in the .tscn or via `_ready`):
##   - terrain_layer : TileMapLayer  — base terrain (plain/forest/...)
##   - castle_layer  : TileMapLayer  — castle sub-features (above terrain)
##   - highlights    : Highlights    — overlay node (M2 visuals)
##   - units         : Node2D        — unit sprites (M2)
##   - effects       : Node2D        — floating-text / animations (M2)
##   - camera        : Camera2D      — pan/zoom

signal map_loaded(width: int, height: int, biome: String)

@onready var terrain_layer: TileMapLayer = $TerrainLayer
@onready var castle_layer: TileMapLayer = $CastleLayer
@onready var highlights: Node2D = $Highlights
@onready var units: Node2D = $Units
@onready var effects: Node2D = $Effects
@onready var camera: Camera2D = $Camera2D

var tile_set: TileSet = null
var map_size: Vector2i = Vector2i.ZERO
var map_biome: String = Config.DEFAULT_BIOME

# Loaded metadata from the most recent `load_map_json_file()` call.
# Mirrored into GameState once the M2 WebSocket wiring lands.
var initial_units: Array = []
var tile_lookup: Dictionary = {}        # Vector2i -> {terrain, subtype}


func _ready() -> void:
	tile_set = TileSetBuilder.build()
	terrain_layer.tile_set = tile_set
	if castle_layer != null:
		castle_layer.tile_set = tile_set
	# Highlights needs the terrain layer for tile→world conversion.
	highlights.bind_terrain_layer(terrain_layer)
	# Map size / camera tuning: a 15×15 board (48px tiles) is 720px
	# square. 1280×720 viewport needs no scaling by default.
	if camera != null:
		camera.zoom = Vector2.ONE
		camera.position_smoothing_enabled = true


# ============================================================
# Loading
# ============================================================

## Load a map from a parsed JSON dictionary. Returns the
## `MapLoader.apply_to_board` result for callers that want
## per-tile metadata.
func load_map(map_json: Dictionary) -> Dictionary:
	var result := MapLoader.apply_to_board(self, map_json)
	map_size = Vector2i(int(result["width"]), int(result["height"]))
	map_biome = String(result["biome"])
	initial_units = result.get("initial_units", [])
	tile_lookup = result.get("tile_lookup", {})
	highlights.reset(map_size)
	map_loaded.emit(map_size.x, map_size.y, map_biome)
	return result

## Convenience wrapper for "load by file path inside the project
## or an absolute path". Path resolution mirrors NetworkClient's
## rules (res:// for project assets, otherwise absolute).
func load_map_json_file(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_error("Board.load_map_json_file: cannot open %s" % path)
		return {}
	var text := f.get_as_text()
	f.close()
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary:
		push_error("Board.load_map_json_file: %s is not a JSON object" % path)
		return {}
	return load_map(parsed)


# ============================================================
# Camera helpers
# ============================================================

## Centre the camera on the board and adjust zoom to fit.
## Called by MapLoader after writing all cells.
func center_camera_on_board(width: int, height: int) -> void:
	if camera == null:
		return
	var center: Vector2 = Vector2(width, height) * Vector2(TileSetBuilder.TILE_SIZE) * 0.5
	camera.position = center
	# Fit-to-screen with 8px margin on each side, so the full board
	# is visible at 1280×720 / 1920×1080. M2 will replace this with
	# a "click-to-zoom" mode for big maps (25×25 doesn't fit on
	# 1280×720 at 1×).
	var viewport := get_viewport().get_visible_rect().size
	var zoom_x: float = (viewport.x - 16.0) / (width * TileSetBuilder.TILE_SIZE.x)
	var zoom_y: float = (viewport.y - 16.0) / (height * TileSetBuilder.TILE_SIZE.y)
	camera.zoom = Vector2(min(zoom_x, zoom_y), min(zoom_x, zoom_y))


# ============================================================
# Coordinate helpers
# ============================================================

## Convert a click position (viewport-local) to a tile coord.
## Returns `Vector2i(-1, -1)` for out-of-board clicks.
func viewport_to_tile(pos: Vector2) -> Vector2i:
	if terrain_layer == null:
		return Vector2i(-1, -1)
	var local: Vector2 = terrain_layer.to_local(pos)
	return terrain_layer.local_to_map(local)

## Inverse of `viewport_to_tile` — handy for placing highlight
## sprites at a cell centre.
func tile_to_viewport(tile: Vector2i) -> Vector2:
	if terrain_layer == null:
		return Vector2.ZERO
	return terrain_layer.to_global(terrain_layer.map_to_local(tile))

## Look up the decoded terrain for a tile. Returns "plain" if
## the cell hasn't been written (out of bounds / unloaded).
func terrain_at(tile: Vector2i) -> String:
	if tile_lookup.has(tile):
		return String(tile_lookup[tile].get("terrain", "plain"))
	return "plain"

func subtype_at(tile: Vector2i) -> String:
	if tile_lookup.has(tile):
		return String(tile_lookup[tile].get("subtype", ""))
	return ""
