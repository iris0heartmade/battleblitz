extends Node2D
class_name Board
## Board coordinates the tile layers, static unit presenters, highlight
## overlay, and camera behavior for the current map.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")
const TEXTURE_LOADER := preload("res://scripts/core/texture_loader.gd")

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
@onready var flag_layer: Node2D = $FlagLayer
@onready var units: Node2D = $UnitLayer
@onready var effects: Node2D = $EffectsLayer
@onready var board_camera: Camera2D = $BoardCamera

# M4.16+:建筑归属旗锚定在 tile 左下角附近。
# 有主建筑用玩家色贴图;中立建筑用白旗贴图。
const _OWNER_FLAG_TEXTURES := {
	"neutral": "res://assets/ui/building_flags/flag_neutral.png",
	"red": "res://assets/ui/building_flags/flag_red.png",
	"blue": "res://assets/ui/building_flags/flag_blue.png",
	"green": "res://assets/ui/building_flags/flag_green.png",
	"yellow": "res://assets/ui/building_flags/flag_yellow.png",
}
# M4.16+:哪些 terrain 算"建筑",显示阵营旗
const _BUILDING_TERRAINS := ["barracks", "castle", "village"]

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
			existing.setup(unit_data, _team_color_for_unit(unit_data), _team_id_for_unit(unit_data))
			var new_cell := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
			var new_pos: Vector2 = metrics.cell_to_local(new_cell)
			var prev_pos: Vector2 = existing.position  # 截图前一帧位置
			if prev_pos != new_pos:
				var optimistic_target: Variant = existing.get_meta("optimistic_target_cell") if existing.has_meta("optimistic_target_cell") else null
				if optimistic_target != null and Vector2i(optimistic_target) == new_cell:
					var optimistic_tween: Tween = existing.get_meta("move_tween") if existing.has_meta("move_tween") else null
					if optimistic_tween != null and optimistic_tween.is_running():
						optimistic_tween.kill()
					existing.position = new_pos
					existing.remove_meta("optimistic_target_cell")
					continue
				# 位置变化 — 用 Tween 0.32s 插值(FLIP 等价)
				var old_tween: Tween = existing.get_meta("move_tween") if existing.has_meta("move_tween") else null
				if old_tween != null and old_tween.is_running():
					old_tween.kill()
				var t: Tween = create_tween()
				existing.set_meta("move_tween", t)
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
	presenter.setup(unit_dict, _team_color_for_unit(unit_dict), _team_id_for_unit(unit_dict))
	presenter.position = metrics.cell_to_local(cell)
	units.add_child(presenter)
	var uid: int = int(unit_dict.get("id", -1))
	if uid >= 0:
		_unit_nodes_by_id[uid] = presenter


# M4.16+:查 unit owner 的 team_id(从 GameState.players[] 取)。
# 1V1 free-for-all(team_id=None)→ 返回 None,unit_node 不显示 team 字母。
# 2V2 队战 → 返回 "team_a"/"team_b" 等。
func _team_id_for_unit(unit_data: Dictionary) -> Variant:
	if GameState == null:
		return null
	var owner_pid: int = int(unit_data.get("player_id", -1))
	if owner_pid <= 0:
		return null
	var owner: Dictionary = GameState.get_player(owner_pid)
	if owner.is_empty():
		return null
	return owner.get("team", null)


func _team_color_for_unit(unit_data: Dictionary) -> Color:
	var team_id: Variant = _team_id_for_unit(unit_data)
	var team_key: String = String(team_id) if team_id != null else ""
	match team_key:
		"team_a": return Config.player_color("red")
		"team_b": return Config.player_color("blue")
		"team_c": return Config.player_color("green")
		"team_d": return Config.player_color("yellow")
	var color_name := String(unit_data.get("color", "red"))
	return Config.player_color(color_name)


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


func show_selected_mark(tile: Vector2i) -> void:
	if highlights != null:
		highlights.show_selected(tile)


# M4.2:进入攻击模式 — 红色 outline(Highlights.Mode.ATTACK)
func show_attack_marks(range_tiles: Array) -> void:
	if highlights == null:
		return
	highlights.clear()
	if range_tiles.size() > 0:
		highlights.show_outline(Highlights.Mode.ATTACK, range_tiles)


# 鸢影·沉默领域选中心模式(P+):
# on=True 时显示中央提示气泡 + hover 时绘制 5×5 outline;
# on=False 清。
var _silence_pick_label: Label = null
var _silence_pick_active: bool = false
var _silence_hover_cell: Vector2i = Vector2i(-1, -1)


func highlight_silence_pick_mode(on: bool) -> void:
	_silence_pick_active = on
	if on:
		if _silence_pick_label == null:
			_silence_pick_label = Label.new()
			_silence_pick_label.name = "SilencePickHint"
			_silence_pick_label.text = "⚡ 沉默领域:点选 5×5 中心(右键取消)"
			_silence_pick_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			_silence_pick_label.add_theme_color_override("font_color", Color(0.85, 0.55, 1.0))
			_silence_pick_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
			_silence_pick_label.add_theme_constant_override("shadow_offset_x", 2)
			_silence_pick_label.add_theme_constant_override("shadow_offset_y", 2)
			_silence_pick_label.add_theme_font_size_override("font_size", 18)
			var sz := Vector2(420, 32)
			_silence_pick_label.size = sz
			_silence_pick_label.position = Vector2(-sz.x * 0.5, -sz.y * 0.5 + 24)
		if not _silence_pick_label.is_inside_tree():
			add_child(_silence_pick_label)
		_silence_pick_label.visible = true
		if highlights != null:
			highlights.clear()
	else:
		if _silence_pick_label != null:
			_silence_pick_label.visible = false
		if highlights != null:
			highlights.clear_mode(Highlights.Mode.SILENCE_PICK)
			highlights.clear_mode(Highlights.Mode.HOVER)
		_silence_hover_cell = Vector2i(-1, -1)


# 鸢影·沉默领域:鼠标移动时更新 5×5 outline 中心点。
# 由 main.gd 转发 InputEventMouseMotion 调用,避免 board 自己 hook input 引发层级冲突。
func update_silence_pick_hover(global_pos: Vector2) -> void:
	if not _silence_pick_active:
		return
	if metrics == null or ground_layer == null:
		return
	# 相机禁用/null 时跳过 hover 映射,避免把 viewport 坐标误当世界坐标
	# 产生错误的 cell 高亮。生产环境相机总是 enabled,这条路径基本 dead code,
	# 但保底 early return 比给一个错位置的高亮更安全。
	if board_camera == null or not board_camera.enabled:
		return
	var world_pos: Vector2 = board_camera.get_canvas_transform().affine_inverse() * global_pos
	var local: Vector2 = ground_layer.to_local(world_pos)
	var cell: Vector2i = ground_layer.local_to_map(local)
	# 限制在地图范围内
	if cell.x < 0 or cell.y < 0 or cell.x >= map_size.x or cell.y >= map_size.y:
		_silence_hover_cell = Vector2i(-1, -1)
	else:
		_silence_hover_cell = cell
	_refresh_silence_pick_outline()


# 鸢影·沉默领域:刷新 5×5 outline(中心 ±2)。
func _refresh_silence_pick_outline() -> void:
	if highlights == null:
		return
	highlights.clear_mode(Highlights.Mode.SILENCE_PICK)
	highlights.clear_mode(Highlights.Mode.HOVER)
	if _silence_hover_cell.x < 0:
		return
	var tiles: Array = []
	for dx in range(-2, 3):
		for dy in range(-2, 3):
			var t: Vector2i = Vector2i(_silence_hover_cell.x + dx, _silence_hover_cell.y + dy)
			if t.x >= 0 and t.y >= 0 and t.x < map_size.x and t.y < map_size.y:
				tiles.append(t)
	if tiles.size() > 0:
		highlights.show_outline(Highlights.Mode.SILENCE_PICK, tiles)


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

func preview_unit_move(unit_id: int, to_cell: Vector2i, duration_sec: float = 0.28) -> void:
	if metrics == null:
		return
	var existing: Node2D = _unit_nodes_by_id.get(unit_id) as Node2D
	if existing == null or not is_instance_valid(existing):
		return
	var new_pos: Vector2 = metrics.cell_to_local(to_cell)
	var old_tween: Tween = existing.get_meta("move_tween") if existing.has_meta("move_tween") else null
	if old_tween != null and old_tween.is_running():
		old_tween.kill()
	if existing.position == new_pos:
		return
	var start_pos: Vector2 = existing.position
	existing.position = start_pos.lerp(new_pos, 0.08)
	if duration_sec <= 0.0:
		existing.position = new_pos
		return
	var t: Tween = create_tween()
	existing.set_meta("move_tween", t)
	t.set_trans(Tween.TRANS_CUBIC)
	t.set_ease(Tween.EASE_OUT)
	t.tween_property(existing, "position", new_pos, duration_sec)


func preview_unit_path(unit_id: int, path_cells: Array, max_total_sec: float = 0.45) -> void:
	if path_cells.is_empty():
		return
	var expanded_path: Array = _expand_to_orthogonal_path(path_cells)
	if expanded_path.size() <= 2:
		preview_unit_move(unit_id, Vector2i(expanded_path[-1]), min(max_total_sec, 0.28))
		return
	if metrics == null:
		return
	var existing: Node2D = _unit_nodes_by_id.get(unit_id) as Node2D
	if existing == null or not is_instance_valid(existing):
		return
	var old_tween: Tween = existing.get_meta("move_tween") if existing.has_meta("move_tween") else null
	if old_tween != null and old_tween.is_running():
		old_tween.kill()
	existing.position = metrics.cell_to_local(Vector2i(expanded_path[0]))
	var steps: Array = expanded_path.slice(1)
	var step_sec: float = min(0.10, max_total_sec / float(max(1, steps.size())))
	var t: Tween = create_tween()
	existing.set_meta("move_tween", t)
	existing.set_meta("optimistic_target_cell", Vector2i(expanded_path[-1]))
	t.set_trans(Tween.TRANS_LINEAR)
	t.set_ease(Tween.EASE_IN_OUT)
	for cell in steps:
		t.tween_property(existing, "position", metrics.cell_to_local(Vector2i(cell)), step_sec)
	t.tween_callback(func() -> void:
		if is_instance_valid(existing) and existing.has_meta("optimistic_target_cell"):
			existing.remove_meta("optimistic_target_cell")
	)


func _expand_to_orthogonal_path(path_cells: Array) -> Array:
	var out: Array = []
	for raw_cell in path_cells:
		var cell := Vector2i(raw_cell)
		if out.is_empty():
			out.append(cell)
			continue
		var cur := Vector2i(out[-1])
		while cur.x != cell.x:
			cur.x += 1 if cell.x > cur.x else -1
			out.append(cur)
		while cur.y != cell.y:
			cur.y += 1 if cell.y > cur.y else -1
			out.append(cur)
	return out


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
	_handle_cursor_input(event)
	_handle_camera_input(event)


func handle_camera_input_from_owner(event: InputEvent) -> void:
	_handle_camera_input(event)


func _handle_camera_input(event: InputEvent) -> void:
	# 2026-08-09:鼠标移动时同步光标 cell — 鼠标/手柄玩家看到的"当前格"一致
	if event is InputEventMouseMotion and InputState != null and InputState.board_focused:
		var world_pos: Vector2 = event.global_position
		if board_camera != null and board_camera.enabled:
			world_pos = board_camera.get_canvas_transform().affine_inverse() * event.global_position
		if ground_layer != null:
			var local: Vector2 = ground_layer.to_local(world_pos)
			var cell: Vector2i = ground_layer.local_to_map(local)
			if cell.x >= 0 and cell.y >= 0 and cell.x < map_size.x and cell.y < map_size.y:
				if InputState.cursor_cell != cell:
					InputState.cursor_cell = cell
		# 不 return — 后续相机/pan 逻辑继续走
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
		if mb.button_index == MOUSE_BUTTON_LEFT or mb.button_index == MOUSE_BUTTON_MIDDLE:
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
		# 用 _safe_set_position 让 camera 走「框不能越过 board」clamp,
		# 而不是 Camera2D 内置 limit_* (那个会把 position 吸附到 limit 边界,体感很奇怪)。
		board_camera._safe_set_position(_pan_start_cam_pos - pan_delta)
		board_camera.mark_user_positioned()
		get_viewport().set_input_as_handled()
		return


func _zoom_at_point(screen_pos: Vector2, delta: float) -> void:
	if board_camera == null:
		return
	# user_factor 是相对 fit_zoom 的乘数;ZOOM_MIN/MAX 直接作用于 user_factor。
	# camera 内部会把 user_factor 乘 fit_zoom 得到最终 zoom,这里不用算实际值。
	var old_user_factor: float = board_camera.get_user_zoom_factor()
	var new_user_factor: float = clamp(old_user_factor + delta, ZOOM_MIN, ZOOM_MAX)
	if new_user_factor == old_user_factor:
		return
	# 把鼠标下的世界点保持不动,先算旧/新 zoom 下的 mouse world,差量补偿到 position。
	# camera.zoom.x = fit_zoom * user_factor,这里用旧/新值算。
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	# fit_zoom 不能直接拿(camera 私有),用旧 zoom / 旧 user_factor 推出 fit_zoom。
	var fit_zoom: float = 1.0
	if old_user_factor > 0.0:
		fit_zoom = board_camera.zoom.x / old_user_factor
	var old_zoom: float = fit_zoom * old_user_factor
	var new_zoom: float = fit_zoom * new_user_factor
	var mouse_world_before: Vector2 = (screen_pos - vp_size * 0.5) / old_zoom + board_camera.position
	board_camera.apply_user_zoom_factor_delta(new_user_factor - old_user_factor)
	var mouse_world_after: Vector2 = (screen_pos - vp_size * 0.5) / new_zoom + board_camera.position
	board_camera._safe_set_position(board_camera.position + (mouse_world_before - mouse_world_after))
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


# M4.16+:重建建筑阵营旗。tile_data 是 Array[Dictionary](server TileOut shape),
# 包含 terrain / owner_id / x / y。pending_claims 用独立徽标显示,避免误读为已过户。
func rebuild_flags(tiles: Array) -> void:
	if flag_layer == null or metrics == null:
		return
	# 清旧
	for child in flag_layer.get_children():
		child.queue_free()
	if tiles.is_empty():
		return
	var pending := _collect_pending_claim_tiles()
	for t in tiles:
		if not t is Dictionary:
			continue
		var terrain: String = String(t.get("terrain", ""))
		if not _BUILDING_TERRAINS.has(terrain):
			continue
		var owner_v: Variant = t.get("owner_id", null)
		var owner_pid: int = 0
		if owner_v != null:
			owner_pid = int(owner_v)
		var cell := Vector2i(int(t.get("x", 0)), int(t.get("y", 0)))
		_add_flag_at(cell, owner_pid)
	for cell in pending.keys():
		_add_claim_badge_at(cell, pending[cell])
	_update_flag_blink()


# M4.16+:从 GameState.pending_claims 收集正在占领的 (x,y) -> claim。
# owner flag 代表当前归属;claim badge 代表正在过户。
func _collect_pending_claim_tiles() -> Dictionary:
	var claiming: Dictionary = {}
	if GameState == null:
		return claiming
	for c in GameState.pending_claims:
		if not c is Dictionary:
			continue
		claiming[Vector2i(int(c.get("tile_x", -1)), int(c.get("tile_y", -1)))] = c
	return claiming


func _flag_color_for_owner(owner_pid: int) -> String:
	if owner_pid <= 0:
		return "neutral"
	var color_name := "red"
	if GameState != null:
		var owner: Dictionary = GameState.get_player(owner_pid)
		if not owner.is_empty():
			color_name = String(owner.get("color", "red"))
	if not _OWNER_FLAG_TEXTURES.has(color_name):
		return "neutral"
	return color_name


# M4.16+:在 cell 左下角放一面像素风归属旗贴图。
# 比代码绘制的几何旗更像正式资产,同时不盖住建筑主体。
func _add_flag_at(cell: Vector2i, owner_pid: int) -> void:
	if metrics == null:
		return
	var holder := Node2D.new()
	holder.name = "OwnerFlag"
	holder.position = metrics.cell_to_local(cell)
	# Z 索引:在 UnitLayer 之前(在 GroundLayer 之上)。
	flag_layer.add_child(holder)
	holder.set_meta("tile_cell", cell)

	var key := _flag_color_for_owner(owner_pid)
	var tex: Texture2D = TEXTURE_LOADER.load_resized(String(_OWNER_FLAG_TEXTURES.get(key, _OWNER_FLAG_TEXTURES["neutral"])), 18)
	if tex == null:
		return
	var sprite := Sprite2D.new()
	sprite.texture = tex
	sprite.position = Vector2(-14, 8)
	holder.add_child(sprite)


func _claim_target_color(claim: Dictionary) -> Color:
	if GameState != null:
		var target: Dictionary = GameState.get_player(int(claim.get("target_player_id", -1)))
		if not target.is_empty():
			return Config.player_color(String(target.get("color", "red")))
	return Color("#f0c75e")


func _claim_badge_text(claim: Dictionary) -> String:
	var remaining: int = max(0, int(claim.get("turns_remaining", 0)))
	var total: int = max(1, int(claim.get("total_turns", Config.CLAIM_TURNS_REQUIRED)))
	return "%d/%d" % [remaining, total]


func _claim_progress(claim: Dictionary) -> float:
	var total: int = max(1, int(claim.get("total_turns", Config.CLAIM_TURNS_REQUIRED)))
	var remaining: int = clamp(int(claim.get("turns_remaining", total)), 0, total)
	return clamp(1.0 - float(remaining) / float(total), 0.0, 1.0)


func _add_claim_badge_at(cell: Vector2i, claim: Dictionary) -> void:
	if metrics == null:
		return
	var holder := Node2D.new()
	holder.name = "ClaimBadge"
	holder.position = metrics.cell_to_local(cell) + Vector2(0, -19)
	flag_layer.add_child(holder)

	var bg := Polygon2D.new()
	bg.polygon = PackedVector2Array([
		Vector2(-15, -6), Vector2(15, -6), Vector2(15, 6), Vector2(-15, 6),
	])
	bg.color = Color(0.05, 0.06, 0.07, 0.72)
	holder.add_child(bg)

	var fill_w: float = max(3.0, 30.0 * _claim_progress(claim))
	var fill := Polygon2D.new()
	fill.polygon = PackedVector2Array([
		Vector2(-15, -6), Vector2(-15 + fill_w, -6),
		Vector2(-15 + fill_w, 6), Vector2(-15, 6),
	])
	fill.color = _claim_target_color(claim)
	holder.add_child(fill)

	var label := Label.new()
	label.text = _claim_badge_text(claim)
	label.position = Vector2(-15, -8)
	label.size = Vector2(30, 16)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 8)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	label.add_theme_constant_override("shadow_offset_x", 1)
	label.add_theme_constant_override("shadow_offset_y", 1)
	holder.add_child(label)


# M4.16+:让属于 pending_claims 的旗闪烁(其他静态显示)。
# 闪烁频率 0.5s on/off,用 _process 里的 accumulate timer 实现,避免
# 频繁 Tween 创建/销毁。
var _flag_blink_t: float = 0.0
const _FLAG_BLINK_HALF_PERIOD := 0.45
# 2026-08-09:棋盘光标脉动(呼吸效果,sin 波)— 让玩家在棋盘上一眼看见光标位置
var _cursor_visible: bool = false
var _cursor_pulse_phase: float = 0.0
const _CURSOR_PULSE_PERIOD := 0.9

func _process(delta: float) -> void:
	if flag_layer != null:
		_flag_blink_t += delta
		# 每隔 _FLAG_BLINK_HALF_PERIOD 秒翻转一次 modulate.a
		if _flag_blink_t >= _FLAG_BLINK_HALF_PERIOD:
			_flag_blink_t = 0.0
			_update_flag_blink()
	# 光标脉动:在 board_focused 时才绘制
	if InputState != null and InputState.board_focused and InputState.cursor_cell.x >= 0:
		_cursor_pulse_phase += delta
		_update_cursor_render()
	# 2026-08-09:持续按住方向键 / 摇杆时光标持续移动
	_tick_cursor_repeat(delta)


# 2026-08-09:根据 InputState.cursor_cell 渲染光标。
# 复用 highlights.show_cursor_at + 脉动 alpha(0.65 ~ 1.0)。
func _update_cursor_render() -> void:
	if highlights == null:
		return
	if InputState == null:
		return
	var cell: Vector2i = InputState.cursor_cell
	if cell.x < 0 or cell.y < 0 or cell.x >= map_size.x or cell.y >= map_size.y:
		_cursor_visible = false
		highlights.clear_mode(Highlights.Mode.CURSOR)
		return
	# 脉动 alpha:0.65 ~ 1.0,周期 0.9s
	var phase01: float = 0.5 + 0.5 * sin(_cursor_pulse_phase * TAU / _CURSOR_PULSE_PERIOD)
	var alpha: float = lerp(0.65, 1.0, phase01)
	var base_color: Color = Highlights._COLORS[Highlights.Mode.CURSOR]
	var pulsed: Color = Color(base_color.r, base_color.g, base_color.b, alpha)
	highlights.show_cursor_at(cell, pulsed)
	_cursor_visible = true


func _update_flag_blink() -> void:
	if flag_layer == null:
		return
	var claiming := _collect_pending_claim_tiles()
	for child in flag_layer.get_children():
		if String(child.name) != "OwnerFlag":
			continue
		var cell_v: Variant = child.get_meta("tile_cell", null)
		if cell_v == null:
			continue
		var cell: Vector2i = cell_v
		var is_being_claimed: bool = claiming.has(cell)
		# 闪烁:每 _FLAG_BLINK_HALF_PERIOD 翻转 — 用 sin 让淡入淡出
		var phase: float = fmod(Time.get_ticks_msec() / 1000.0, _FLAG_BLINK_HALF_PERIOD * 2.0)
		var on: bool = phase < _FLAG_BLINK_HALF_PERIOD
		child.modulate.a = 0.4 if (is_being_claimed and not on) else 1.0


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
		if board_camera.has_method("apply_new_map_metrics"):
			board_camera.apply_new_map_metrics(metrics)
		else:
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


func tile_to_screen(tile: Vector2i) -> Vector2:
	if ground_layer == null:
		return Vector2.ZERO
	var world_pos: Vector2
	if metrics == null:
		world_pos = ground_layer.to_global(ground_layer.map_to_local(tile))
	else:
		world_pos = ground_layer.to_global(metrics.cell_to_local(tile))
	if board_camera != null and board_camera.enabled:
		return board_camera.get_canvas_transform() * world_pos
	return world_pos


# Compatibility alias for older callers. The returned value is a CanvasLayer
# screen coordinate, not an untransformed board-world position.
func tile_to_viewport(tile: Vector2i) -> Vector2:
	return tile_to_screen(tile)


func screen_rect() -> Rect2:
	var viewport := get_viewport()
	var fallback := viewport.get_visible_rect() if viewport != null else Rect2()
	if ground_layer == null or metrics == null or not metrics.has_method("bounds_rect"):
		return fallback
	var local_rect: Rect2 = metrics.bounds_rect()
	if local_rect.size.x <= 0.0 or local_rect.size.y <= 0.0:
		return fallback
	var corners: Array[Vector2] = [
		local_rect.position,
		local_rect.position + Vector2(local_rect.size.x, 0.0),
		local_rect.position + local_rect.size,
		local_rect.position + Vector2(0.0, local_rect.size.y),
	]
	var min_point := Vector2(INF, INF)
	var max_point := Vector2(-INF, -INF)
	for local_point in corners:
		var screen_point := ground_layer.to_global(local_point)
		if board_camera != null and board_camera.enabled:
			screen_point = board_camera.get_canvas_transform() * screen_point
		min_point.x = min(min_point.x, screen_point.x)
		min_point.y = min(min_point.y, screen_point.y)
		max_point.x = max(max_point.x, screen_point.x)
		max_point.y = max(max_point.y, screen_point.y)
	return Rect2(min_point, max_point - min_point)


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


# ============================================================
# 2026-08-09:棋盘虚拟光标 + 键盘/手柄操作路由
# 设计:光标 cell 走 InputState.cursor_cell,确认 / 取消 / 缩放走专属 action
#   (Switch 反转 B=确认 A=取消)。所有现有"点击 cell" / "右键 cell"逻辑
#   全部复用,不绕过。
# ============================================================

const _CURSOR_REPEAT_DELAY := 0.18  # 持续按方向键时光标移动间隔
const _CURSOR_REPEAT_INITIAL := 0.32  # 第一次重复前等待
var _cursor_hold_dir: Vector2i = Vector2i.ZERO
var _cursor_hold_t: float = 0.0
var _cursor_initial_t: float = 0.0
var _cursor_hold_axis: Vector2 = Vector2.ZERO


func _handle_cursor_input(event: InputEvent) -> void:
	if InputState == null:
		return
	# board_focused == false 时,光标不动(玩家在 UI 面板里)
	if not InputState.board_focused:
		return
	if map_size.x <= 0 or map_size.y <= 0:
		return
	# 只在 GameView 顶层(没被 modal 锁)时响应
	if InputState.is_input_locked():
		return

	# === 光标移动:方向键 / 摇杆(单次 + 持续) ===
	if event.is_action_pressed("board_cursor_up"):
		_move_cursor(Vector2i(0, -1))
		_begin_cursor_repeat(Vector2i(0, -1))
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("board_cursor_down"):
		_move_cursor(Vector2i(0, 1))
		_begin_cursor_repeat(Vector2i(0, 1))
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("board_cursor_left"):
		_move_cursor(Vector2i(-1, 0))
		_begin_cursor_repeat(Vector2i(-1, 0))
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("board_cursor_right"):
		_move_cursor(Vector2i(1, 0))
		_begin_cursor_repeat(Vector2i(1, 0))
		get_viewport().set_input_as_handled()
		return
	# 摇杆持续按住 → 持续移动
	if event is InputEventJoypadMotion:
		var jm: InputEventJoypadMotion = event
		if jm.axis == 0 or jm.axis == 1:
			_update_cursor_hold_axis(jm.axis, jm.axis_value)
	# 方向键松开 → 停掉 repeat
	if event is InputEventKey:
		var k: InputEventKey = event
		if not k.pressed:
			match k.keycode:
				KEY_UP, KEY_W:    _end_cursor_repeat_if_dir(Vector2i(0, -1))
				KEY_DOWN, KEY_S:  _end_cursor_repeat_if_dir(Vector2i(0, 1))
				KEY_LEFT, KEY_A:  _end_cursor_repeat_if_dir(Vector2i(-1, 0))
				KEY_RIGHT, KEY_D: _end_cursor_repeat_if_dir(Vector2i(1, 0))
	if event is InputEventJoypadMotion:
		var jm2: InputEventJoypadMotion = event
		if jm2.axis == 0 or jm2.axis == 1:
			_update_cursor_hold_axis(jm2.axis, jm2.axis_value)

	# === 缩放 ===
	if event.is_action_pressed("board_zoom_in"):
		_zoom_at_viewport_center(ZOOM_STEP)
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("board_zoom_out"):
		_zoom_at_viewport_center(-ZOOM_STEP)
		get_viewport().set_input_as_handled()
		return

	# === 确认(Switch 反转:B = 确认)===
	# 复用 _unhandled_input 在 main.gd 里的"左键点击"分支:把光标 cell 当成"鼠标点的那格"。
	# 通过 emit_unit_clicked / emit_tile_clicked 走现成路径。
	if event.is_action_pressed("board_confirm"):
		_confirm_cursor()
		get_viewport().set_input_as_handled()
		return

	# === 取消(Switch 反转:A = 取消)===
	# 复用"右键空地"分支 — 取消行动模式 + 清高亮。
	if event.is_action_pressed("board_cancel"):
		_cancel_cursor()
		get_viewport().set_input_as_handled()
		return


# 持续按住方向键 / 摇杆时光标持续移动
func _tick_cursor_repeat(delta: float) -> void:
	if _cursor_hold_dir == Vector2i.ZERO:
		return
	if InputState == null or not InputState.board_focused:
		_cursor_hold_dir = Vector2i.ZERO
		return
	_cursor_hold_t += delta
	# 第一次重复等 _CURSOR_REPEAT_INITIAL,之后 _CURSOR_REPEAT_DELAY 间隔
	if _cursor_initial_t < _CURSOR_REPEAT_INITIAL:
		_cursor_initial_t += delta
		return
	if _cursor_hold_t < _CURSOR_REPEAT_DELAY:
		return
	_cursor_hold_t = 0.0
	_move_cursor(_cursor_hold_dir)


func _begin_cursor_repeat(dir: Vector2i) -> void:
	_cursor_hold_dir = dir
	_cursor_hold_t = 0.0
	_cursor_initial_t = 0.0


func _end_cursor_repeat_if_dir(dir: Vector2i) -> void:
	if _cursor_hold_dir == dir:
		_cursor_hold_dir = Vector2i.ZERO


func _update_cursor_hold_axis(axis: int, value: float) -> void:
	# 轴 0=X,轴 1=Y;每个轴独立评估。
	# 简单策略:哪个轴的 |value| > deadzone 就 update hold dir 对应方向。
	if axis == 0:
		if absf(value) < 0.3:
			_cursor_hold_axis.x = 0.0
		else:
			_cursor_hold_axis.x = value
	elif axis == 1:
		if absf(value) < 0.3:
			_cursor_hold_axis.y = 0.0
		else:
			_cursor_hold_axis.y = value
	# 决定 hold_dir
	var new_dir := Vector2i.ZERO
	if absf(_cursor_hold_axis.x) > 0.4:
		new_dir.x = 1 if _cursor_hold_axis.x > 0.0 else -1
	if absf(_cursor_hold_axis.y) > 0.4:
		new_dir.y = 1 if _cursor_hold_axis.y > 0.0 else -1
	# 同一行只 hold 一个方向(避免斜着走时光标走对角线 — 战棋是 4 方向)
	if new_dir.x != 0 and new_dir.y != 0:
		# 哪个轴的绝对值更大,留哪个
		if absf(_cursor_hold_axis.x) > absf(_cursor_hold_axis.y):
			new_dir.y = 0
		else:
			new_dir.x = 0
	if new_dir != _cursor_hold_dir:
		_cursor_hold_dir = new_dir
		_cursor_hold_t = 0.0
		_cursor_initial_t = 0.0


func _move_cursor(delta: Vector2i) -> void:
	if InputState == null:
		return
	var cur: Vector2i = InputState.cursor_cell
	if cur.x < 0:
		cur = Vector2i(0, 0)
	var next := Vector2i(
		clamp(cur.x + delta.x, 0, map_size.x - 1),
		clamp(cur.y + delta.y, 0, map_size.y - 1),
	)
	if next == cur:
		return
	InputState.cursor_cell = next
	# 同步 hover_tile(让现有的"hover 显示 info / 画 path dots"白嫖)
	InputState.hover_tile = next
	# 主动触发 main.gd 的 path-dots 更新(若在 move 模式)
	var main_node := get_node_or_null("/root/Main")
	if main_node != null and main_node.has_method("_update_path_dots_at_cell"):
		main_node.call("_update_path_dots_at_cell", next)


func _confirm_cursor() -> void:
	# 复用现成"鼠标左键点击 cell"逻辑 — emit unit_clicked / tile_clicked
	if InputState == null:
		return
	var cell: Vector2i = InputState.cursor_cell
	if cell.x < 0:
		return
	var unit_id: int = _unit_id_at_cell(cell)
	if unit_id > 0:
		emit_unit_clicked(unit_id)
		return
	# 没单位:走 tile 点击逻辑(行动模式时是落点,非模式时是清高亮)
	emit_tile_clicked(tile_to_screen(cell))


func _cancel_cursor() -> void:
	# 复用"右键"路径:取消行动模式 / 清高亮
	var main_node := get_node_or_null("/root/Main")
	if main_node != null and main_node.has_method("_cursor_cancel_action"):
		main_node.call("_cursor_cancel_action")
		return
	# 退路:自己清高亮
	if highlights != null:
		highlights.clear()


func _zoom_at_viewport_center(delta: float) -> void:
	# 屏幕中心而不是鼠标位置(手柄玩家没鼠标)
	if board_camera == null:
		return
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var center: Vector2 = vp_size * 0.5
	# _zoom_at_point 内部会读 board_camera 当前位置,直接复用即可
	_zoom_at_point(center, delta)
