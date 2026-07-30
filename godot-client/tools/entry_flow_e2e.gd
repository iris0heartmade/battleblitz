## Verifies the GUI entry points that hand off into a real game:
## mainline chapter start and online lobby create-room start.

extends Node

const MAIN_SCENE := preload("res://scenes/main.tscn")
const MAINLINE_ID := "chapter_01_steel_rebellion"
const WAIT_SEC := 25.0

var _failed := false


func _ready() -> void:
	print("=== BattleBlitz Godot entry-flow e2e ===")
	NetworkClient.api_error.connect(func(method: String, path: String, error: String, code: int) -> void:
		print("[entry-flow] API_ERROR %s %s code=%d error=%s" % [method, path, code, error])
	)
	NetworkClient.api_response.connect(func(method: String, path: String, _body: Variant, code: int) -> void:
		print("[entry-flow] API_OK %s %s code=%d" % [method, path, code])
	)
	await get_tree().process_frame
	await _run_mainline_flow()
	if _failed:
		return
	await _run_lobby_create_flow()
	if _failed:
		return
	print("[entry-flow] PASS")
	get_tree().quit(0)


func _run_mainline_flow() -> void:
	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	print("[entry-flow] mainline: start %s" % MAINLINE_ID)
	main.call("_on_mainline_pressed")
	await get_tree().create_timer(0.5).timeout
	var mainline_view: Node = main.get_node_or_null("MainlineView")
	if mainline_view == null or not mainline_view.has_method("_on_slot_new_game_pressed"):
		_fail("mainline controller cannot start a slot")
		return
	mainline_view.call("_on_slot_new_game_pressed", 0)
	await _wait_prebattle_dialogue(main)
	if _failed:
		return
	await _save("entry_flow_mainline_dialogue.png")
	DialogManager.hide_dialog()
	await _wait_game_ready(main, "mainline")
	await _save("entry_flow_mainline_game.png")
	if main.has_method("_reset_game_state_for_main_menu"):
		main.call("_reset_game_state_for_main_menu")
	main.queue_free()
	await _await_http_idle()
	await get_tree().create_timer(1.0).timeout


func _run_lobby_create_flow() -> void:
	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	print("[entry-flow] lobby: create room and start")
	main.call("_on_lobby_pressed")
	await get_tree().create_timer(0.5).timeout
	var lobby: Node = main.get_node_or_null("Lobby")
	if lobby == null:
		_fail("lobby controller not found")
		return
	lobby.call("_on_create_card_pressed")
	await get_tree().create_timer(1.0).timeout
	var name_input: LineEdit = main.get_node_or_null("Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateNameInput")
	if name_input != null:
		name_input.text = "entry-flow-%d" % Time.get_unix_time_from_system()
	if lobby.has_method("_on_lobby_seat_ai_toggled"):
		lobby.call("_on_lobby_seat_ai_toggled", true, 1)
		await get_tree().create_timer(0.2).timeout
	lobby.call("_on_create_room_pressed")
	var join_deadline := Time.get_ticks_msec() + int(WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < join_deadline:
		if int(main.get("_game_id")) > 0 and int(main.get("_player_id")) > 0:
			break
		await get_tree().create_timer(0.25).timeout
	if int(main.get("_game_id")) <= 0 or int(main.get("_player_id")) <= 0:
		_fail("lobby did not create+join a room")
		return
	await get_tree().create_timer(1.0).timeout
	lobby.call("_on_lobby_start_pressed")
	await _wait_game_ready(main, "lobby")
	await _save("entry_flow_lobby_game.png")
	main.queue_free()
	await get_tree().process_frame


func _wait_game_ready(main: Node, label: String) -> void:
	var deadline := Time.get_ticks_msec() + int(WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		var game_id := int(main.get("_game_id"))
		var game_view: Node = main.get_node_or_null("GameView")
		var summary_id := int(GameState.game_summary.get("id", 0)) if GameState.game_summary is Dictionary else 0
		if game_id > 0 and game_view != null and game_view.visible and GameState.tiles.size() > 0 and summary_id == game_id:
			print("[entry-flow] %s ready: game=%d player=%d tiles=%d" % [
				label, game_id, int(main.get("_player_id")), GameState.tiles.size()
			])
			return
		await get_tree().create_timer(0.25).timeout
	_fail("%s did not enter a populated GameView" % label)


func _wait_prebattle_dialogue(main: Node) -> void:
	var deadline := Time.get_ticks_msec() + int(WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		var game_view: CanvasItem = main.get_node_or_null("GameView") as CanvasItem
		if game_view != null and game_view.visible and not DialogManager.is_playing():
			_fail("mainline entered GameView before pre-battle dialogue")
			return
		if DialogManager.is_playing() and _dialog_panel_visible():
			print("[entry-flow] mainline pre-battle dialogue visible")
			return
		await get_tree().create_timer(0.1).timeout
	_fail("mainline pre-battle dialogue did not appear")


func _dialog_panel_visible() -> bool:
	var panel: CanvasItem = DialogManager.get_node_or_null("DialogPanel") as CanvasItem
	return panel != null and panel.visible


func _save(name: String) -> void:
	if DisplayServer.get_name() == "headless":
		print("[entry-flow] screenshot skipped in headless: %s" % name)
		return
	for i in 3:
		await get_tree().process_frame
	var texture := get_viewport().get_texture()
	if texture == null:
		print("[entry-flow] screenshot skipped, viewport texture is null: %s" % name)
		return
	var img := texture.get_image()
	if img == null:
		return
	img.save_png("user://" + name)
	img.save_png("res://" + name)
	print("[entry-flow] screenshot saved: %s" % name)


func _await_http_idle(timeout_sec: float = 10.0) -> void:
	var deadline := Time.get_ticks_msec() + int(timeout_sec * 1000.0)
	while Time.get_ticks_msec() < deadline:
		var busy := bool(NetworkClient.get("_req_busy"))
		var queue: Array = NetworkClient.get("_req_queue")
		if not busy and queue.is_empty():
			return
		await get_tree().create_timer(0.1).timeout


func _fail(message: String) -> void:
	if _failed:
		return
	_failed = true
	printerr("[entry-flow] FAIL: " + message)
	get_tree().quit(1)
