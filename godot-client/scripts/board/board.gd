extends Node2D
class_name Board
## 正式棋盘统一使用高差3D舞台；保留业务接口，菜单/HUD仍在原2D坐标中。
const Model = preload("res://scripts/board/height_map/board_model.gd")
const Terrain = preload("res://scripts/board/height_map/terrain_view.gd")
const Camera = preload("res://scripts/board/height_map/orbit_camera.gd")
const Marks = preload("res://scripts/board/height_map/highlights_3d.gd")
const Controls = preload("res://scripts/board/height_map/board_controls.gd")
const Metrics = preload("res://scripts/core/map_metrics.gd")
signal map_loaded(width: int, height: int, biome: String)
signal unit_clicked(unit_id: int)
signal tile_clicked(tile: Vector2i)

var model: RefCounted
var terrain: Node3D
var board_camera: Camera3D
var highlights: Node3D
var controls: Node
var surface: SubViewportContainer
var stage: SubViewport
var world: Node3D
var units: Node3D
var flag_layer: Node3D
var effects: Node3D
var metrics: RefCounted
var map_size := Vector2i.ZERO
var map_biome := "grass"
var initial_units: Array = []
var tile_lookup: Dictionary = {}
var _unit_nodes_by_id: Dictionary = {}
var _panning := false
var _silence_pick_active := false
var _silence_hover_cell := Vector2i(-1,-1)
var _last_cursor := Vector2i(-1,-1)
var _owner_signature := ""
var _move_tweens: Dictionary = {}
var preview_mode := false
var view_size := Vector2.ZERO

func _ready() -> void:
	model = Model.new()
	_setup_stage()
	controls = Controls.new()
	add_child(controls)
	controls.board = self
	get_viewport().size_changed.connect(_resize_stage)
	visibility_changed.connect(_sync_visibility)
	_resize_stage()
	_sync_visibility()
	# 编辑棋盘只消费编辑器数据，避免后台战斗快照覆盖正在画的地图。
	if name != "EditorBoard" and not preview_mode:
		GameState.units_changed.connect(_on_units_changed)

func _setup_stage() -> void:
	surface = SubViewportContainer.new()
	surface.name = "HeightMapSurface"
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	surface.stretch = true
	add_child(surface)
	stage = SubViewport.new()
	stage.name = "HeightMapViewport"
	stage.own_world_3d = true
	stage.handle_input_locally = false
	stage.gui_disable_input = true
	surface.add_child(stage)
	world = Node3D.new()
	stage.add_child(world)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color("172633")
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("c6d9e7")
	env.environment.ambient_light_energy = 0.45
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55,-35,0)
	sun.light_energy = 0.85
	sun.shadow_enabled = true
	world.add_child(sun)
	board_camera = Camera.new()
	board_camera.name = "BoardCamera"
	world.add_child(board_camera)
	board_camera.setup(model.settings)
	board_camera.top_inset = 120
	highlights = Marks.new()
	world.add_child(highlights)
	highlights.setup(model)
	flag_layer = Node3D.new()
	world.add_child(flag_layer)
	effects = Node3D.new()
	world.add_child(effects)

func _resize_stage() -> void:
	# Board可置于编辑器的偏移节点下，舞台仍覆盖完整屏幕。
	surface.position = Vector2.ZERO if preview_mode else -global_position
	surface.size = view_size if view_size!=Vector2.ZERO else get_viewport_rect().size
	board_camera.update_view()

func _sync_visibility() -> void:
	if stage:
		stage.render_target_update_mode = SubViewport.UPDATE_ALWAYS if is_visible_in_tree() else SubViewport.UPDATE_DISABLED
	if controls and not is_visible_in_tree():
		controls.cancel_drag()

func load_map(map_json: Dictionary) -> Dictionary:
	var result := MapLoader.decode_map(map_json)
	map_size = Vector2i(int(result.width),int(result.height))
	map_biome = str(result.biome)
	metrics = Metrics.new(map_size)
	tile_lookup = result.tile_lookup
	model.load_cells(map_size,tile_lookup,map_biome,map_json.get("elevations",[]))
	model.units = _normalize_units(result.initial_units)
	initial_units = model.units
	var owners: Array = map_json.get("tile_owners",[])
	for owner in owners:
		var p := Vector2i(int(owner.x),int(owner.y))
		if model.contains(p):
			model.cell(p).faction = str(owner.get("color","neutral"))
	if terrain == null:
		terrain = Terrain.new()
		world.add_child(terrain)
		terrain.setup(model)
	else:
		_kill_move_tweens()
		terrain.rebuild()
	terrain.unit.visible = false
	terrain.marker.visible = false
	units = terrain.contents.units
	_reindex_units()
	highlights.clear()
	_owner_signature = ""
	board_camera.defaults.width = map_size.x
	board_camera.defaults.depth = map_size.y
	# 同一张编辑图重绘保留镜头，新图只在首次或尺寸改变时归位。
	var key := str(map_json.get("__id",map_json.get("id",map_json.get("name",""))))+str(map_size)
	if get_meta("map_key","") != key:
		set_meta("map_key",key)
		board_camera.reset_view()
		if not model.units.is_empty():
			var u: Dictionary = model.units[0]
			board_camera.focus_on(model.surface(Vector2i(int(u.x),int(u.y))))
	map_loaded.emit(map_size.x,map_size.y,map_biome)
	return result

func load_map_json_file(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return load_map(value) if value is Dictionary else {}

func _kill_move_tweens() -> void:
	for tween in _move_tweens.values():
		if tween and tween.is_running():
			tween.kill()
	_move_tweens.clear()

func _reindex_units() -> void:
	_unit_nodes_by_id.clear()
	for entry in terrain.contents.unit_nodes.values():
		var data: Dictionary = entry.anchor.get_meta("unit",{})
		var uid := int(data.get("id",-1))
		if uid>=0:
			_unit_nodes_by_id[uid] = entry.anchor

func _on_units_changed(entries: Array) -> void:
	if terrain == null:
		return
	var old_positions: Dictionary = {}
	for uid in _unit_nodes_by_id:
		old_positions[uid] = _unit_nodes_by_id[uid].position
	_kill_move_tweens()
	model.units = _normalize_units(entries)
	initial_units = model.units
	terrain.contents.rebuild_units()
	_reindex_units()
	for uid in _unit_nodes_by_id:
		var anchor: Node3D = _unit_nodes_by_id[uid]
		var target := anchor.position
		if old_positions.has(uid) and old_positions[uid] != target:
			anchor.position = old_positions[uid]
			var tween := create_tween()
			_move_tweens[uid] = tween
			tween.tween_property(anchor,"position",target,0.28).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _normalize_units(entries: Array) -> Array:
	var result: Array = model.normalize_units(entries)
	for entry in result:
		if entry.get("player_id") != null:
			var owner: Dictionary = GameState.get_player(int(entry.player_id))
			entry.color = str(owner.get("color",entry.color))
			entry.team = owner.get("team")
	return result

func viewport_to_tile(pos: Vector2) -> Vector2i:
	if terrain == null:
		return Vector2i(-1,-1)
	var hit: Dictionary = terrain.pick(board_camera,pos)
	return hit.cell if not hit.is_empty() and hit.top else Vector2i(-1,-1)

func tile_to_screen(tile: Vector2i) -> Vector2:
	return board_camera.unproject_position(model.surface(tile)) if model.contains(tile) else Vector2(-1,-1)

func tile_to_viewport(tile: Vector2i) -> Vector2:
	return tile_to_screen(tile)

func screen_rect() -> Rect2:
	return get_viewport_rect()

func terrain_at(tile: Vector2i) -> String:
	return str(tile_lookup.get(tile,{}).get("terrain","plain"))

func subtype_at(tile: Vector2i) -> String:
	return str(tile_lookup.get(tile,{}).get("subtype",""))

func _unit_id_at_cell(cell: Vector2i) -> int:
	for uid in _unit_nodes_by_id:
		var data: Dictionary = _unit_nodes_by_id[uid].get_meta("unit",{})
		if Vector2i(int(data.x),int(data.y)) == cell:
			return uid
	return -1

func pick_unit_at_screen(pos: Vector2) -> int:
	return _unit_id_at_cell(viewport_to_tile(pos))

func emit_unit_clicked(uid: int) -> void:
	unit_clicked.emit(uid)

func emit_tile_clicked(pos: Vector2) -> void:
	var cell := viewport_to_tile(pos)
	if model.contains(cell):
		tile_clicked.emit(cell)

func clear_selection_marks() -> void:
	highlights.clear()

func show_path_marks(path: Array, reachable: Array) -> void:
	highlights.clear()
	highlights.show_outline(Highlights.Mode.MOVE,reachable)
	highlights.show_path(path)

func show_selected_mark(cell: Vector2i) -> void:
	highlights.show_selected(cell)
	board_camera.keep_visible(model.surface(cell))

func show_attack_marks(tiles: Array) -> void:
	highlights.clear()
	highlights.show_outline(Highlights.Mode.ATTACK,tiles)

func highlight_silence_pick_mode(on: bool) -> void:
	_silence_pick_active = on
	if not on:
		highlights.clear_mode(Highlights.Mode.SILENCE_PICK)

func update_silence_pick_hover(pos: Vector2) -> void:
	if not _silence_pick_active:
		return
	_silence_hover_cell = viewport_to_tile(pos)
	var cells: Array = []
	if model.contains(_silence_hover_cell):
		for y in range(-2,3):
			for x in range(-2,3):
				cells.append(_silence_hover_cell+Vector2i(x,y))
	highlights.show_outline(Highlights.Mode.SILENCE_PICK,cells)

func rebuild_flags(tiles: Array) -> void:
	if terrain == null:
		return
	var signature := str(tiles)+str(GameState.pending_claims)
	if signature == _owner_signature:
		return
	_owner_signature = signature
	for tile in tiles:
		var p := Vector2i(int(tile.x),int(tile.y))
		if not model.contains(p):
			continue
		tile_lookup[p] = tile.duplicate(true)
		var owner: Dictionary = GameState.get_player(int(tile.owner_id)) if tile.get("owner_id") != null else {}
		model.cell(p).faction = str(owner.get("color","neutral"))
	terrain.contents.rebuild_features()
	for child in flag_layer.get_children():
		child.free()
	for claim in GameState.pending_claims:
		var p := Vector2i(int(claim.get("tile_x",-1)),int(claim.get("tile_y",-1)))
		if model.contains(p):
			var label := _label_at(p,"占领 %d/%d" % [int(claim.get("turns_remaining",0)),int(claim.get("total_turns",3))],Color("e7c661"))
			label.name = "ClaimBadge"
			label.set_meta("cell",p)
			flag_layer.add_child(label)

func _label_at(cell: Vector2i, text: String, color: Color) -> Label3D:
	var label := Label3D.new()
	label.text = text
	label.modulate = color
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.font_size = 36
	label.outline_size = 8
	label.pixel_size = 0.005
	label.position = model.surface(cell)+Vector3.UP*1.45
	return label

func spawn_floating_text_at_cell(cell: Vector2i, text: String, color_hex: String = "#e85a6a", _kind: String = "damage") -> void:
	if not model.contains(cell):
		return
	var label := _label_at(cell,text,Color(color_hex))
	effects.add_child(label)
	var tween := create_tween().set_parallel(true)
	tween.tween_property(label,"position:y",label.position.y+0.7,0.9)
	tween.tween_property(label,"modulate:a",0.0,0.9)
	tween.chain().tween_callback(label.queue_free)

func preview_unit_move(uid: int, cell: Vector2i, duration_sec: float = 0.28) -> void:
	preview_unit_path(uid,[cell],duration_sec)

func preview_unit_path(uid: int, path: Array, duration_sec: float = 0.45) -> void:
	if not _unit_nodes_by_id.has(uid) or path.is_empty():
		return
	if _move_tweens.has(uid) and _move_tweens[uid].is_running():
		_move_tweens[uid].kill()
	path = _expand_grid_path(path)
	var anchor: Node3D = _unit_nodes_by_id[uid]
	var tween := create_tween()
	_move_tweens[uid] = tween
	for cell in path:
		if model.contains(cell):
			tween.tween_property(anchor,"position",model.surface(cell),duration_sec/path.size())

func _expand_grid_path(path: Array) -> Array:
	var expanded: Array = [path[0]]
	for index in range(1,path.size()):
		var cell: Vector2i = expanded.back()
		var target: Vector2i = path[index]
		while cell.x != target.x:
			cell.x += 1 if target.x>cell.x else -1
			expanded.append(cell)
		while cell.y != target.y:
			cell.y += 1 if target.y>cell.y else -1
			expanded.append(cell)
	return expanded

func _process(_delta: float) -> void:
	if not is_visible_in_tree() or preview_mode or name == "EditorBoard" or terrain == null:
		return
	if InputState.board_focused and model.contains(InputState.cursor_cell):
		highlights.show_cursor_at(InputState.cursor_cell,Color.WHITE)
		if _last_cursor != InputState.cursor_cell:
			_last_cursor = InputState.cursor_cell
			board_camera.keep_visible(model.surface(_last_cursor))
	else:
		highlights.clear_mode(Highlights.Mode.CURSOR)

func handle_camera_input_from_owner(event: InputEvent) -> void:
	controls.handle_event(event)

func _unhandled_input(event: InputEvent) -> void:
	if not preview_mode and controls.handle_event(event):
		get_viewport().set_input_as_handled()

func show_preview(map_data: Dictionary, dimensions: Vector2) -> void:
	view_size = dimensions
	_resize_stage()
	load_map(map_data)
	board_camera.defaults.camera_safe_left = 0
	board_camera.top_inset = 0
	board_camera.right_inset = 0
	board_camera.size = maxf(map_size.x,map_size.y)*0.95+3.0
	board_camera.focus_on(Vector3((map_size.x-1)*0.5,0,(map_size.y-1)*0.5))
	_fit_preview()

func _fit_preview() -> void:
	# 缩略图按真实地形、地貌和柱底的投影包围范围取景，避免不同尺寸地图过小。
	var points: Array[Vector3] = []
	for y in map_size.y:
		for x in map_size.x:
			var p := Vector2i(x,y)
			points.append(model.surface(p))
			if not str(model.cell(p).feature).is_empty():
				points.append(model.surface(p)+Vector3.UP*1.4)
	for entry in model.units:
		points.append(model.surface(Vector2i(int(entry.x),int(entry.y)))+Vector3.UP*float(model.rules.unit_height))
	for x in [-0.5,float(map_size.x)-0.5]:
		for z in [-0.5,float(map_size.y)-0.5]:
			points.append(Vector3(x,float(model.settings.base_height),z))
	var bounds := _project_bounds(points)
	var available := Vector2(stage.size)-Vector2(24,24)
	board_camera.size *= maxf(bounds.size.x/maxf(1,available.x),bounds.size.y/maxf(1,available.y))
	board_camera.update_view()
	bounds = _project_bounds(points)
	board_camera.pan(Vector2(stage.size)*0.5-bounds.get_center())

func _project_bounds(points: Array[Vector3]) -> Rect2:
	var bounds := Rect2(board_camera.unproject_position(points[0]),Vector2.ZERO)
	for point in points:
		bounds = bounds.expand(board_camera.unproject_position(point))
	return bounds

func shake() -> void:
	var baseline: float = board_camera.h_offset
	var tween := create_tween().set_loops(6)
	tween.tween_property(board_camera,"h_offset",baseline+0.05,0.035)
	tween.tween_property(board_camera,"h_offset",baseline-0.05,0.035)
	tween.tween_property(board_camera,"h_offset",baseline,0.035)
