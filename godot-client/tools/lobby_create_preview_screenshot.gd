extends Node

const SCREENSHOT_DIR := "res://screenshots"


func _ready() -> void:
	get_window().size = Vector2i(1600, 900)
	var native_dir := ProjectSettings.globalize_path(SCREENSHOT_DIR)
	DirAccess.make_dir_recursive_absolute(native_dir)

	var scene: PackedScene = load("res://scenes/main.tscn")
	var main: Node = scene.instantiate()
	add_child(main)
	await _settle()
	var lobby: Node = main.get_node_or_null("Lobby")
	if lobby == null:
		printerr("Lobby node unavailable")
		get_tree().quit(1)
		return

	if lobby.has_method("_enter_lobby_view"):
		lobby.call("_enter_lobby_view")
	await _settle()
	await _capture("lobby_mode_select.png")

	if lobby.has_method("_on_join_card_pressed"):
		lobby.call("_on_join_card_pressed")
	if lobby.has_method("_on_room_list_response"):
		lobby.call("_on_room_list_response", [
			{"id": 21, "name": "周末练兵 2P", "status": "waiting", "map_preset": "balanced_2p_15", "capacity": 2},
			{"id": 42, "name": "四方会战 4P", "status": "waiting", "map_preset": "balanced_4p_20", "capacity": 4},
		], 200)
	await _settle()
	await _capture("lobby_join.png")

	await _show_create_preview(lobby, "balanced_2p_15", "lobby_create_2p.png")
	await _show_create_preview(lobby, "balanced_4p_20", "lobby_create_4p.png")

	get_tree().quit(0)


func _show_create_preview(lobby: Node, map_id: String, filename: String) -> void:
	if lobby.has_method("_on_create_card_pressed"):
		lobby.call("_on_create_card_pressed")
	if lobby.has_method("_on_lobby_presets_response"):
		var players := 2
		if map_id.contains("_3p_"):
			players = 3
		elif map_id.contains("_4p_"):
			players = 4
		lobby.call("_on_lobby_presets_response", {
			"maps": [{
				"id": map_id,
				"name": map_id,
				"biome": "grass",
				"recommended_players": players,
			}]
		}, 200)
	await _settle()
	await _capture(filename)


func _settle() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().create_timer(0.2).timeout


func _capture(filename: String) -> void:
	await get_tree().process_frame
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport image unavailable")
		get_tree().quit(1)
		return
	var path := "%s/%s" % [SCREENSHOT_DIR, filename]
	var err := img.save_png(path)
	if err != OK:
		printerr("failed to save %s: %s" % [path, error_string(err)])
		get_tree().quit(1)
		return
	print("saved: %s" % path)
