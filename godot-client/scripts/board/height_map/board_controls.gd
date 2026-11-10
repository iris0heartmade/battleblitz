extends Node
## 输入只转换成逻辑格信号；业务动作仍由正式main.gd处理。
var board: Node2D
var pointer := 0
var origin := Vector2.ZERO
var dragged := false
var held := Vector2i.ZERO
var repeat_time := 0.0
var editor_cursor := Vector2i.ZERO

func cancel_drag() -> void:
	pointer = 0
	dragged = false
	board._panning = false
	held = Vector2i.ZERO

func handle_event(event: InputEvent) -> bool:
	if not board.is_visible_in_tree() or board.map_size == Vector2i.ZERO:
		return false
	if InputState.is_input_locked():
		cancel_drag()
		return false
	var main := get_node_or_null("/root/Main")
	if board.name != "EditorBoard" and main:
		for prop in ["pause_panel","settings_panel","war_report_panel","recruit_panel","attack_confirm_panel","battle_result_panel"]:
			var panel: Variant = main.get(prop)
			if panel is CanvasItem and panel.is_visible_in_tree():
				cancel_drag()
				return false
	if event is InputEventMouseButton:
		if event.button_index in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN] and event.pressed:
			board.board_camera.zoom(0.9 if event.button_index==MOUSE_BUTTON_WHEEL_UP else 1.1)
			return true
		if event.button_index in [MOUSE_BUTTON_LEFT,MOUSE_BUTTON_MIDDLE,MOUSE_BUTTON_RIGHT]:
			if event.pressed:
				pointer = event.button_index
				origin = event.position
				dragged = false
				board._panning = true
			elif pointer == event.button_index:
				var clicked := not dragged
				cancel_drag()
				if clicked and event.button_index == MOUSE_BUTTON_LEFT:
					click_cell(event.position)
				elif clicked and event.button_index == MOUSE_BUTTON_RIGHT and main:
					if main._move_mode_unit_id>0 or main._attack_mode_unit_id>0 or main._skill_mode_unit_id>0:
						main.call("_cursor_cancel_action")
					else:
						var uid: int = board.pick_unit_at_screen(event.position)
						if uid>0:
							board.show_attack_marks(main._get_attack_range_tiles(get_node("/root/GameState").get_unit(uid)))
						else:
							main.call("_cursor_cancel_action")
			return true
	if event is InputEventMouseMotion:
		InputState.hover_tile = board.viewport_to_tile(event.position)
		if pointer:
			if event.position.distance_to(origin)>float(board.model.settings.camera_drag_threshold):
				dragged = true
			if dragged:
				if pointer == MOUSE_BUTTON_RIGHT:
					board.board_camera.orbit_drag(event.relative)
				else:
					board.board_camera.pan(event.relative)
			return true
		return false
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode in [KEY_Q,KEY_E]:
			board.board_camera.turn(float(board.model.settings.camera_turn_step)*(-1 if event.keycode==KEY_Q else 1))
			return true
		if event.keycode == KEY_F:
			var cell: Vector2i = InputState.cursor_cell
			if board.model.contains(cell):
				board.board_camera.focus_on(board.model.surface(cell))
			return true
	if board.name == "EditorBoard":
		if event is InputEventKey and event.pressed:
			var direction := Vector2i.ZERO
			match event.keycode:
				KEY_UP: direction = Vector2i.UP
				KEY_DOWN: direction = Vector2i.DOWN
				KEY_LEFT: direction = Vector2i.LEFT
				KEY_RIGHT: direction = Vector2i.RIGHT
				KEY_ENTER, KEY_SPACE:
					dispatch_cell(editor_cursor)
					return true
			if direction!=Vector2i.ZERO:
				select_editor_cell((editor_cursor+direction).clamp(Vector2i.ZERO,board.map_size-Vector2i.ONE))
				return true
		return false
	if not InputState.board_focused:
		return false
	for pair in [["board_cursor_up",Vector2i.UP],["board_cursor_down",Vector2i.DOWN],["board_cursor_left",Vector2i.LEFT],["board_cursor_right",Vector2i.RIGHT]]:
		if event.is_action_pressed(pair[0]):
			move_cursor(pair[1])
			held = pair[1]
			repeat_time = 0.32
			return true
		if event.is_action_released(pair[0]) and held == pair[1]:
			held = Vector2i.ZERO
			return true
	if event.is_action_pressed("board_confirm"):
		var cell: Vector2i = InputState.cursor_cell
		if board.model.contains(cell):
			dispatch_cell(cell)
		return true
	if event.is_action_pressed("board_cancel"):
		if main:
			main.call("_cursor_cancel_action")
		return true
	if event.is_action_pressed("board_zoom_in") or event.is_action_pressed("board_zoom_out"):
		board.board_camera.zoom(0.9 if event.is_action_pressed("board_zoom_in") else 1.1)
		return true
	return false

func click_cell(pos: Vector2) -> void:
	var cell: Vector2i = board.viewport_to_tile(pos)
	if board.model.contains(cell):
		dispatch_cell(cell)

func dispatch_cell(cell: Vector2i) -> void:
	board.get_viewport().gui_release_focus()
	if board.name == "EditorBoard":
		select_editor_cell(cell)
		board.tile_clicked.emit(cell)
		return
	InputState.cursor_cell = cell
	var uid: int = board._unit_id_at_cell(cell)
	if uid>0:
		board.unit_clicked.emit(uid)
	else:
		board.tile_clicked.emit(cell)

func select_editor_cell(cell: Vector2i) -> void:
	editor_cursor = cell
	board.terrain.marker.visible = true
	board.terrain.set_xray(true)
	board.terrain.select(cell)
	board.board_camera.keep_visible(board.model.surface(cell))
	var editor := board.get_parent()
	if editor.has_method("show_elevation_selection"):
		editor.show_elevation_selection(cell)

func move_cursor(direction: Vector2i) -> void:
	var cell: Vector2i = InputState.cursor_cell
	cell = (cell+direction).clamp(Vector2i.ZERO,board.map_size-Vector2i.ONE)
	InputState.cursor_cell = cell
	InputState.hover_tile = cell
	var main := get_node_or_null("/root/Main")
	if main:
		main.call("_update_path_dots_at_cell",cell)

func _process(delta: float) -> void:
	if held == Vector2i.ZERO:
		return
	if not board.is_visible_in_tree() or not InputState.board_focused or InputState.is_input_locked():
		held = Vector2i.ZERO
		return
	repeat_time -= delta
	if repeat_time<=0:
		repeat_time = 0.18
		move_cursor(held)

func _input(event: InputEvent) -> void:
	# 拖动后在HUD上松开时，GUI会吃掉release；帧末清理未送达的拖动。
	if event is InputEventMouseButton and not event.pressed and pointer==event.button_index:
		call_deferred("_cancel_unhandled_release",event.button_index)

func _cancel_unhandled_release(button: int) -> void:
	if pointer==button:
		cancel_drag()
