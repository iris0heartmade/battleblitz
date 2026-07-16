extends Node2D
class_name Board
## Board coordinates the tile layers, static unit presenters, highlight
## overlay, and camera behavior for the current map.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")

signal map_loaded(width: int, height: int, biome: String)
signal unit_clicked(unit_id: int)
signal tile_clicked(tile: Vector2i)

# M4.7:增量刷新用 — unit_id (int) -> UnitNode 实例
var _unit_nodes_by_id: Dictionary = {}

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
	# M4.7:订阅 GameState.units_changed 做增量刷新(HP/MP/士气变化)
	if Engine.has_singleton("GameState") == false:
		# autoload 在 _ready 之前已注入;若取不到则跳过(防 headless 重入)
		var gs: Node = get_node_or_null("/root/GameState")
		if gs != null and not gs.units_changed.is_connected(_on_units_changed):
			gs.units_changed.connect(_on_units_changed)


# M4.7:由 GameState.units_changed 触发。把已存在的 markers 用新数据重画
# (HP/MP/士气条/已行动 overlay),位置不变。新 ID → 走 _add_unit_node。
func _on_units_changed(units_data: Array) -> void:
	if metrics == null:
		return
	var seen_ids := {}
	for unit_data in units_data:
		if not (unit_data is Dictionary):
			continue
		var uid: int = int(unit_data.get("id", -1))
		if uid < 0:
			continue
		seen_ids[uid] = true
		var existing: Node = _unit_nodes_by_id.get(uid)
		if existing != null and is_instance_valid(existing):
			# 增量:update data + 位置(单位可能移动过)
			existing.setup(unit_data, Config.player_color(String(unit_data.get("color", "red"))))
			var cell := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
			existing.position = metrics.cell_to_local(cell)
			continue
		# 新单位:完整插入
		_add_unit_node(unit_data)
	# 清理掉已不存在的
	for uid in _unit_nodes_by_id.keys():
		var n: Node = _unit_nodes_by_id[uid]
		if n != null and is_instance_valid(n):
			if not seen_ids.has(uid):
				n.queue_free()
		_unit_nodes_by_id.erase(uid)


# M4.7:把 1 个单位作为 UnitNode 插入 UnitLayer
func _add_unit_node(unit_data: Dictionary) -> void:
	if metrics == null or not (unit_data is Dictionary):
		return
	var presenter = UNIT_NODE_SCRIPT.new()
	var unit_dict: Dictionary = unit_data
	var color_name := String(unit_dict.get("color", "red"))
	var cell := Vector2i(int(unit_dict.get("x", 0)), int(unit_dict.get("y", 0)))
	presenter.setup(unit_dict, Config.player_color(color_name))
	presenter.position = metrics.cell_to_local(cell)
	units.add_child(presenter)
	var uid: int = int(unit_dict.get("id", -1))
	if uid >= 0:
		_unit_nodes_by_id[uid] = presenter


# M4.10:屏幕坐标 → cell,找该 cell 的单位
func pick_unit_at_screen(global_pos: Vector2) -> int:
	if metrics == null or ground_layer == null:
		return -1
	var local: Vector2 = ground_layer.to_local(global_pos)
	var cell: Vector2i = ground_layer.local_to_map(local)
	return _unit_id_at_cell(cell)


func _unit_id_at_cell(cell: Vector2i) -> int:
	for uid in _unit_nodes_by_id.keys():
		var n: Node = _unit_nodes_by_id[uid]
		if n == null or not is_instance_valid(n):
			continue
		var ud: Dictionary = n.unit_data if n.has_method("get") else {}
		# UnitNode 暴露 unit_data 字段;直接读
		if ud.is_empty():
			continue
		if int(ud.get("x", -1)) == cell.x and int(ud.get("y", -1)) == cell.y:
			return int(uid)
	return -1


# M4.10:选中单位后,展示可达范围 + 路径 dots。
# 1) reachable tiles (cyan outline) → use board.highlights.show_outline()
# 2) path dots 的渲染入口留下 — main 调 board.show_path_for_unit(uid)
func clear_selection_marks() -> void:
	if highlights != null:
		highlights.clear()


# M4.10:把"从起点到当前 hover 路径"作为 dot 渲染出来。
# tiles 是 List of Vector2i(只包含 unit 步过的 path)。
func show_path_marks(path_tiles: Array, reachable_tiles: Array) -> void:
	if highlights == null:
		return
	highlights.clear()
	if reachable_tiles.size() > 0:
		highlights.show_outline(Highlights.Mode.MOVE, reachable_tiles)
	if path_tiles.size() > 0:
		highlights.show_path(path_tiles)


# M4.2:进入攻击模式 — 红色 outline(Highlights.Mode.ATTACK)
func show_attack_marks(range_tiles: Array) -> void:
	if highlights == null:
		return
	highlights.clear()
	if range_tiles.size() > 0:
		highlights.show_outline(Highlights.Mode.ATTACK, range_tiles)


# M4.10:让 main 主动 emit unit_clicked 信号 — 在 _unhandled_input 中
# 调 pick_unit_at_screen 取到 id 后调用本函数,main 那边订阅即可。
func emit_unit_clicked(unit_id: int) -> void:
	unit_clicked.emit(unit_id)


# M4.1:把屏幕坐标转成 tile,emit tile_clicked 信号
func emit_tile_clicked(global_pos: Vector2) -> void:
	if metrics == null or ground_layer == null:
		tile_clicked.emit(Vector2i(-1, -1))
		return
	var local: Vector2 = ground_layer.to_local(global_pos)
	tile_clicked.emit(ground_layer.local_to_map(local))


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
	_unit_nodes_by_id.clear()
	if metrics == null:
		return
	for unit_data in units_data:
		if not (unit_data is Dictionary):
			continue
		_add_unit_node(unit_data)
