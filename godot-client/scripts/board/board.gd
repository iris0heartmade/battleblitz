extends Node2D
class_name Board
## Board coordinates the tile layers, static unit presenters, highlight
## overlay, and camera behavior for the current map.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")

signal map_loaded(width: int, height: int, biome: String)

@onready var ground_layer: TileMapLayer = $GroundLayer
@onready var structure_layer: TileMapLayer = $StructureLayer
@onready var decor_layer: TileMapLayer = $DecorLayer
@onready var highlights: Node2D = $HighlightLayer
@onready var units: Node2D = $UnitLayer
@onready var effects: Node2D = $EffectsLayer
@onready var board_camera: Camera2D = $BoardCamera

var tile_set: TileSet = null
var metrics = null
var map_size: Vector2i = Vector2i.ZERO
var map_biome: String = Config.DEFAULT_BIOME
var initial_units: Array = []
var tile_lookup: Dictionary = {}        # Vector2i -> {terrain, subtype}


func _ready() -> void:
	tile_set = TileSetBuilder.build()
	ground_layer.tile_set = tile_set
	structure_layer.tile_set = tile_set
	decor_layer.tile_set = tile_set
	highlights.bind_terrain_layer(ground_layer)
	if board_camera != null:
		board_camera.position_smoothing_enabled = true


func load_map(map_json: Dictionary) -> Dictionary:
	var result := MapLoader.apply_to_board(self, map_json)
	map_size = Vector2i(int(result["width"]), int(result["height"]))
	map_biome = String(result["biome"])
	metrics = MAP_METRICS_SCRIPT.new(map_size)
	initial_units = result.get("initial_units", [])
	tile_lookup = result.get("tile_lookup", {})
	_rebuild_units(initial_units)
	highlights.reset(metrics)
	if board_camera != null:
		board_camera.apply_metrics(metrics)
	map_loaded.emit(map_size.x, map_size.y, map_biome)
	return result


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


func viewport_to_tile(pos: Vector2) -> Vector2i:
	if ground_layer == null:
		return Vector2i(-1, -1)
	var local: Vector2 = ground_layer.to_local(pos)
	return ground_layer.local_to_map(local)


func tile_to_viewport(tile: Vector2i) -> Vector2:
	if ground_layer == null:
		return Vector2.ZERO
	if metrics == null:
		return ground_layer.to_global(ground_layer.map_to_local(tile))
	return ground_layer.to_global(metrics.cell_to_local(tile))


func terrain_at(tile: Vector2i) -> String:
	if tile_lookup.has(tile):
		return String(tile_lookup[tile].get("terrain", "plain"))
	return "plain"


func subtype_at(tile: Vector2i) -> String:
	if tile_lookup.has(tile):
		return String(tile_lookup[tile].get("subtype", ""))
	return ""


func _rebuild_units(units_data: Array) -> void:
	for child in units.get_children():
		child.queue_free()
	if metrics == null:
		return
	for unit_data in units_data:
		if not (unit_data is Dictionary):
			continue
		var presenter = UNIT_NODE_SCRIPT.new()
		var unit_dict: Dictionary = unit_data
		var color_name := String(unit_dict.get("color", "red"))
		var cell := Vector2i(int(unit_dict.get("x", 0)), int(unit_dict.get("y", 0)))
		presenter.setup(unit_dict, Config.player_color(color_name))
		presenter.position = metrics.cell_to_local(cell)
		units.add_child(presenter)
