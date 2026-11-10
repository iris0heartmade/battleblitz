extends Node3D

const Model = preload("res://demos/height_map/map_model.gd")
const View = preload("res://scripts/board/height_map/terrain_view.gd")
const Camera = preload("res://scripts/board/height_map/orbit_camera.gd")
const Editor = preload("res://demos/height_map/editor_ui.gd")
const Battle = preload("res://demos/height_map/battle_controller.gd")
const SAVE_PATH := "user://height_map_demo/map.json"

var model: RefCounted
var terrain: Node3D
var camera: Camera3D
var editor: CanvasLayer
var selected := Vector2i(4, 4)
var left_drag_origin := Vector2.ZERO
var left_dragging := false
var left_pointer_down := false
var start_with_standard := true
var battle: Node

func _ready() -> void:
	get_window().title = "BattleBlitz · 手绘高差地图 · 近景与光标跟随"
	# Demo以1280×720作为界面基准，避免沿用主游戏1920基准后小窗口文字过小。
	get_window().content_scale_size = Vector2i(1280, 720)
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/geometry.json"))
	model = Model.new(config)
	var import_error := ""
	if start_with_standard and model.rules.default_map == "standard":
		import_error = model.import_standard()
		if import_error.is_empty():
			selected = Vector2i(int(model.units[0].x),int(model.units[0].y))
	_setup_world()
	terrain = View.new()
	terrain.selected = selected
	add_child(terrain)
	terrain.setup(model)
	camera = Camera.new()
	add_child(camera)
	camera.setup(config)
	camera.focus_on(model.surface(selected) - Vector3.UP * float(config.camera_frame_drop))
	editor = Editor.new()
	add_child(editor)
	editor.action.connect(handle_action)
	editor.height_changed.connect(func(h: int): edit_selected(h))
	editor.terrain_changed.connect(func(t: String): edit_selected(model.elevation(selected), t))
	editor.pitch_changed.connect(func(v: float):
		camera.pitch = v
		camera.update_view())
	editor.file_dialog.file_selected.connect(_file_selected)
	editor.preset_changed.connect(_change_preset)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("user://height_map_demo"))
	_sync()
	battle = Battle.new()
	add_child(battle)
	battle.setup(self)
	if not import_error.is_empty():
		_message(import_error)

func _change_preset(preset: String) -> void:
	if _editing_locked():
		return
	var error := ""
	if preset == "standard":
		error = model.import_standard()
	else:
		model.make_sample()
	if not error.is_empty():
		_message(error)
		return
	selected = Vector2i(4,4) if model.units.is_empty() else Vector2i(int(model.units[0].x),int(model.units[0].y))
	_reload_board()
	_message("已切换：" + model.map_name)

func _reload_board() -> void:
	selected = Vector2i(clampi(selected.x,0,model.size().x-1),clampi(selected.y,0,model.size().y-1))
	terrain.selected = selected
	terrain.rebuild()
	terrain.unit.visible = model.units.is_empty()
	camera.defaults = model.settings
	handle_action("reset")
	_sync()

func _setup_world() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("172633")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("c6d9e7")
	environment.ambient_light_energy = 0.45
	world.environment = environment
	add_child(world)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 0.85
	sun.shadow_enabled = true
	add_child(sun)

func _process(_delta: float) -> void:
	if editor != null:
		editor.sync_camera(camera)

func select_cell(p: Vector2i) -> void:
	if model.contains(p):
		# 点击地图后将键盘交还棋盘，避免方向键仍在上次按钮间跳焦点。
		get_viewport().gui_release_focus()
		selected = p
		terrain.select(p)
		camera.keep_visible(model.surface(p) + Vector3.UP * 0.6)
		_sync()

func edit_selected(h: int, t: String = "") -> void:
	if _editing_locked():
		return
	if model.edit(selected, h, t):
		terrain.rebuild()
		camera.keep_visible(model.surface(selected) + Vector3.UP * 0.6)
		_message("已修改；保存后可在下次启动加载")
	_sync()

func _sync() -> void:
	get_window().title = "BattleBlitz · %s · 高差地图Demo" % model.map_name
	editor.sync(model, selected)

func handle_action(action: String) -> void:
	if _editing_locked() and action in ["raise","lower","zero","undo","redo","save","load","files","open"]:
		return
	match action:
		"raise": edit_selected(model.elevation(selected) + 1)
		"lower": edit_selected(model.elevation(selected) - 1)
		"zero": edit_selected(0)
		"undo", "redo":
			var changed: bool = model.undo() if action == "undo" else model.redo()
			if changed:
				terrain.rebuild()
			_sync()
		"grid": terrain.grid.visible = not terrain.grid.visible
		"unit": terrain.toggle_units()
		"red", "blue":
			for entry in model.units:
				if entry.color == action:
					select_cell(Vector2i(int(entry.x),int(entry.y)))
					handle_action("focus")
					break
		"left", "right":
			camera.turn(float(model.settings.camera_turn_step) * (-1 if action == "left" else 1))
		"focus":
			camera.focus_on(model.surface(selected))
		"xray":
			terrain.set_xray(not terrain.xray_selected)
			editor.buttons.xray.set_pressed_no_signal(terrain.xray_selected)
			_message("透视选中已开启：仅显示被遮挡的选中框与角色" if terrain.xray_selected else "已恢复正常遮挡")
		"reset":
			camera.reset_view()
			camera.focus_on(model.surface(selected) - Vector3.UP * float(model.settings.camera_frame_drop))
			editor.pitch_input.value = camera.pitch
		"save": save_to(SAVE_PATH)
		"load": load_from(SAVE_PATH)
		"files", "open":
			editor.file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE if action == "open" else FileDialog.FILE_MODE_SAVE_FILE
			editor.file_dialog.current_file = "height-map.json"
			editor.file_dialog.title = "打开地图" if action == "open" else "另存为地图"
			editor.file_dialog.popup_centered_ratio(0.65)

func save_to(path: String) -> bool:
	if _editing_locked():
		return false
	var error: String = model.save_map(path)
	_message("已保存：" + ProjectSettings.globalize_path(path) if error.is_empty() else error)
	return error.is_empty()

func load_from(path: String) -> bool:
	if _editing_locked():
		return false
	var error: String = model.load_map(path)
	if error.is_empty():
		_reload_board()
	_message("已加载地图" if error.is_empty() else error)
	return error.is_empty()

func _file_selected(path: String) -> void:
	if editor.file_dialog.file_mode == FileDialog.FILE_MODE_OPEN_FILE:
		load_from(path)
	else:
		save_to(path)

func _message(text: String) -> void:
	editor.status.text = text

func _editing_locked() -> bool:
	return battle != null and (battle.active or battle.busy)

func _unhandled_input(event: InputEvent) -> void:
	if editor.file_dialog.visible or (battle != null and battle.ui.confirmation.visible):
		return
	if event is InputEventMouseMotion:
		if event.button_mask & MOUSE_BUTTON_MASK_LEFT and event.position.distance_to(left_drag_origin) > float(model.settings.camera_drag_threshold):
			left_dragging = true
			camera.pan(event.relative)
		elif event.button_mask & MOUSE_BUTTON_MASK_MIDDLE or (event.button_mask & MOUSE_BUTTON_MASK_RIGHT and event.shift_pressed):
			camera.pan(event.relative)
		elif event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
			camera.orbit_drag(event.relative)
	elif event is InputEventMouseButton:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP:
				if event.pressed: camera.zoom(0.9)
			MOUSE_BUTTON_WHEEL_DOWN:
				if event.pressed: camera.zoom(1.1)
			MOUSE_BUTTON_LEFT:
				if event.pressed:
					left_drag_origin = event.position
					left_dragging = false
					left_pointer_down = true
				elif left_pointer_down:
					left_pointer_down = false
					if not left_dragging and event.position.distance_to(left_drag_origin) <= float(model.settings.camera_drag_threshold):
						_click_cell(event.position)
	elif event is InputEventKey and event.pressed:
		if event.echo and event.keycode not in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN]:
			return
		var focused := get_viewport().gui_get_focus_owner()
		if focused is LineEdit:
			return
		if event.ctrl_pressed:
			match event.keycode:
				KEY_ENTER, KEY_SPACE:
					if battle != null and battle.active:
						battle.select_cell(selected)
				KEY_ESCAPE:
					if battle != null and battle.active and not battle.busy:
						battle.mode = "idle"
						battle.overlay.clear()
				KEY_Z: handle_action("undo")
				KEY_Y: handle_action("redo")
				KEY_S: handle_action("save")
		else:
			match event.keycode:
				KEY_Q: handle_action("left")
				KEY_E: handle_action("right")
				KEY_F: handle_action("focus")
				KEY_X: handle_action("xray")
				KEY_LEFT: select_cell(selected + Vector2i.LEFT)
				KEY_RIGHT: select_cell(selected + Vector2i.RIGHT)
				KEY_UP: select_cell(selected + Vector2i.UP)
				KEY_DOWN: select_cell(selected + Vector2i.DOWN)
				KEY_EQUAL, KEY_PLUS, KEY_KP_ADD: handle_action("raise")
				KEY_MINUS, KEY_KP_SUBTRACT: handle_action("lower")

func _click_cell(position: Vector2) -> void:
	var hit: Dictionary = terrain.pick(camera,position)
	if not hit.is_empty() and hit.top:
		if battle != null and battle.active:
			battle.select_cell(hit.cell)
		else:
			select_cell(hit.cell)
	elif not hit.is_empty():
		_message("这是悬崖侧面；请旋转视角后点击顶面")
