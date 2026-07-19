## Verifies the GUI entry points that hand off into a real game:
## mainline chapter start and online lobby create-room start.

extends Node

const MAIN_SCENE := preload("res://scenes/main.tscn")
const MAINLINE_ID := "chapter_01_steel_rebellion"
const WAIT_SEC := 25.0

var _failed := false


func _ready() -> void:
	print("=== BattleBlitz Godot entry-flow e2e ===")
	await get_tree().process_frame
	await _run_mainline_flow()
	await _run_lobby_create_flow()
	print("[entry-flow] PASS")
	get_tree().quit(0)


func _run_mainline_flow() -> void:
	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	print("[entry-flow] mainline: start %s" % MAINLINE_ID)
	main.call("_on_mainline_pressed")
	await get_tree().create_timer(0.5).timeout
	main.call("_on_ml_card_pressed", MAINLINE_ID)
	await _wait_game_ready(main, "mainline")
	await _save("entry_flow_mainline_game.png")
	main.queue_free()
	await get_tree().process_frame


func _run_lobby_create_flow() -> void:
	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	print("[entry-flow] lobby: create room and start")
	main.call("_on_lobby_pressed")
	await get_tree().create_timer(0.5).timeout
	main.call("_on_create_card_pressed")
	await get_tree().create_timer(0.2).timeout
	var name_input: LineEdit = main.get_node_or_null("Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateNameInput")
	if name_input != null:
		name_input.text = "entry-flow-%d" % Time.get_unix_time_from_system()
	main.call("_on_create_room_pressed")
	var join_deadline := Time.get_ticks_msec() + int(WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < join_deadline:
		if int(main.get("_game_id")) > 0 and int(main.get("_player_id")) > 0:
			break
		await get_tree().create_timer(0.25).timeout
	if int(main.get("_game_id")) <= 0 or int(main.get("_player_id")) <= 0:
		_fail("lobby did not create+join a room")
		return
	await get_tree().create_timer(1.0).timeout
	main.call("_on_lobby_start_pressed")
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


func _fail(message: String) -> void:
	if _failed:
		return
	_failed = true
	printerr("[entry-flow] FAIL: " + message)
	get_tree().quit(1)
