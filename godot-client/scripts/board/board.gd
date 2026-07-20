extends Node2D
class_name Board
## Board coordinates the tile layers, static unit presenters, highlight
## overlay, and camera behavior for the current map.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")

# M4.11:FLIP 动画 — unit 位置变化时从旧坐标平滑插值到新坐标
const _FLIP_DURATION := 0.32

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
# M4.11:已有 uid 位置变化时 FLIP 动画(从旧坐标 tween 到新坐标)。
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
			# 增量:update data + FLIP 动画(如果位置变化)。
			existing.setup(unit_data, Config.player_color(String(unit_data.get("color", "red"))))
			var new_cell := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
			var new_pos: Vector2 = metrics.cell_to_local(new_cell)
			var prev_pos: Vector2 = existing.position  # 截图前一帧位置
			if prev_pos != new_pos:
				# 位置变化 — 用 Tween 0.32s 插值(FLIP 等价)
				var t: Tween = create_tween()
				t.set_trans(Tween.TRANS_CUBIC)
				t.set_ease(Tween.EASE_OUT)
				# FIX: tween 从 prev_pos → new_pos。
				existing.position = prev_pos
				t.tween_property(existing, "position", new_pos, _FLIP_DURATION)
			continue
		# 新单位:完整插入(无动画,瞬时出现)
		_add_unit_node(unit_data)
		# 清理掉已不存在的(只在 not seen 时 erase)
	for uid in _unit_nodes_by_id.keys():
		if seen_ids.has(uid):
			continue
		var n: Node = _unit_nodes_by_id[uid]
		_unit_nodes_by_id.erase(uid)
		if n != null and is_instance_valid(n):
				n.queue_free()


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
	var world_pos: Vector2 = global_pos
	if board_camera != null and board_camera.enabled:
		world_pos = board_camera.get_canvas_transform().affine_inverse() * global_pos
	var local: Vector2 = ground_layer.to_local(world_pos)
	var cell: Vector2i = ground_layer.local_to_map(local)
	return _unit_id_at_cell(cell)


func _unit_id_at_cell(cell: Vector2i) -> int:
	for uid in _unit_nodes_by_id.keys():
		var n: Node = _unit_nodes_by_id[uid]
		if n == null or not is_instance_valid(n):
			continue
		var ud: Dictionary = n.get("unit_data") if n != null else {}
		# UnitNode 暴露 unit_data 字段;直接读
		if typeof(ud) != TYPE_DICTIONARY or ud.is_empty():
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


# M4.12:在指定 board-local 位置弹出浮动文字(damage/heal/kill/crit)。
# 颜色按 kind 选:damage 红 / crit 烫金 / heal 绿 / kill 烫红
# / levelup 蓝 — 由调用方传 color 字符串(#rrggbb)即可。
func spawn_floating_text(local_pos: Vector2, text: String, color_hex: String = "#e85a6a", kind: String = "damage") -> void:
	if effects == null:
		return
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", Color(color_hex))
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	label.add_theme_constant_override("shadow_offset_x", 2)
	label.add_theme_constant_override("shadow_offset_y", 2)
	label.add_theme_font_size_override("font_size", 22)
	# 居中
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var sz := Vector2(80, 28)
	label.size = sz
	label.position = local_pos - sz * 0.5
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	effects.add_child(label)
	# Tween 上浮 60px + 0.8s 后 fade out。
	var t: Tween = create_tween()
	t.set_parallel(true)
	t.tween_property(label, "position:y", local_pos.y - 60, 0.8).set_trans(Tween.TRANS_CUBIC)
	t.tween_property(label, "modulate:a", 0.0, 0.8).set_trans(Tween.TRANS_LINEAR)
	t.set_parallel(false)
	t.tween_callback(label.queue_free)


# helper:把 cell 转 local,然后 spawn floating text。
func spawn_floating_text_at_cell(cell: Vector2i, text: String, color_hex: String = "#e85a6a", kind: String = "damage") -> void:
	if metrics == null: return
	spawn_floating_text(metrics.cell_to_local(cell), text, color_hex, kind)


# M4.10:让 main 主动 emit unit_clicked 信号 — 在 _unhandled_input 中
# 调 pick_unit_at_screen 取到 id 后调用本函数,main 那边订阅即可。

# ============================================================
# 缩放(Zoom) + 拖拽(Pan) — 鼠标滚轮缩放,左键拖拽
# ============================================================

const ZOOM_MIN: float = 0.4
const ZOOM_MAX: float = 3.0
const ZOOM_STEP: float = 0.15
const DRAG_THRESHOLD_PX: float = 6.0
var _panning: bool = false
var _pan_was_dragging: bool = false
var _pan_start_mouse: Vector2 = Vector2.ZERO
var _pan_start_cam_pos: Vector2 = Vector2.ZERO
var _press_start_mouse: Vector2 = Vector2.ZERO


func _unhandled_input(event: InputEvent) -> void:
	_handle_camera_input(event)


func handle_camera_input_from_owner(event: InputEvent) -> void:
	_handle_camera_input(event)


func _handle_camera_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb: InputEventMouseButton = event
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			_zoom_at_point(mb.global_position, ZOOM_STEP)
			get_viewport().set_input_as_handled()
			return
		if mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			_zoom_at_point(mb.global_position, -ZOOM_STEP)
			get_viewport().set_input_as_handled()
			return
		if mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				_press_start_mouse = mb.global_position
				_pan_start_mouse = mb.global_position
				if board_camera != null:
					_pan_start_cam_pos = board_camera.position
				_panning = true
				_pan_was_dragging = false
			else:
				if _panning and _pan_was_dragging:
					get_viewport().set_input_as_handled()
				_panning = false
				if _pan_was_dragging and board_camera != null:
					board_camera.position_smoothing_enabled = true
				_pan_was_dragging = false
			return
	if event is InputEventMouseMotion and _panning and board_camera != null:
		var diff2: Vector2 = event.global_position - _press_start_mouse
		if not _pan_was_dragging and diff2.length() < DRAG_THRESHOLD_PX:
			return
		if not _pan_was_dragging:
			board_camera.position_smoothing_enabled = false
		_pan_was_dragging = true
		var pan_delta: Vector2 = (event.global_position - _pan_start_mouse) / board_camera.zoom.x
		board_camera.position = _pan_start_cam_pos - pan_delta
		board_camera.mark_user_positioned()
		get_viewport().set_input_as_handled()
		return


func _zoom_at_point(screen_pos: Vector2, delta: float) -> void:
	if board_camera == null:
		return
	var old_zoom: float = board_camera.zoom.x
	var new_zoom: float = clamp(old_zoom + delta, ZOOM_MIN, ZOOM_MAX)
	if new_zoom == old_zoom:
		return
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var mouse_world_before: Vector2 = (screen_pos - vp_size * 0.5) / old_zoom + board_camera.position
	board_camera.zoom = Vector2(new_zoom, new_zoom)
	var mouse_world_after: Vector2 = (screen_pos - vp_size * 0.5) / new_zoom + board_camera.position
	board_camera.position += mouse_world_before - mouse_world_after
	board_camera.mark_user_positioned()


func emit_unit_clicked(unit_id: int) -> void:
	unit_clicked.emit(unit_id)


# M4.1:把屏幕坐标转成 tile,emit tile_clicked 信号
func emit_tile_clicked(global_pos: Vector2) -> void:
	if metrics == null or ground_layer == null:
		tile_clicked.emit(Vector2i(-1, -1))
		return
	var world_pos: Vector2 = global_pos
	if board_camera != null and board_camera.enabled:
		world_pos = board_camera.get_canvas_transform().affine_inverse() * global_pos
	var local: Vector2 = ground_layer.to_local(world_pos)
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
