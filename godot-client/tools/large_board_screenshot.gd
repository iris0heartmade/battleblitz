extends Node

const OUT_PATH := "res://screenshots/game_large_board_20p.png"


func _ready() -> void:
	get_window().size = Vector2i(1600, 900)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://screenshots"))
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main: Node = scene.instantiate()
	add_child(main)
	await get_tree().process_frame
	if main.has_method("_show_view"):
		main.call("_show_view", "game")
	var board: Board = main.find_child("Board", true, false)
	if board == null:
		printerr("large_board_screenshot: no Board")
		get_tree().quit(1)
		return
	var path := _map_path_for_id("balanced_4p_20")
	if path == "":
		printerr("large_board_screenshot: map not found")
		get_tree().quit(1)
		return
	var f := FileAccess.open(path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	if parsed is Dictionary:
		board.load_map(parsed)
	for i in range(4):
		await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img == null:
		printerr("large_board_screenshot: viewport image unavailable")
		get_tree().quit(1)
		return
	img.save_png(OUT_PATH)
	var cam: Camera2D = board.get_node_or_null("BoardCamera") as Camera2D
	var cam_info := "none"
	if cam != null:
		cam_info = "pos=%s zoom=%s limits=(%d,%d,%d,%d) enabled=%s" % [
			str(cam.position), str(cam.zoom),
			cam.limit_left, cam.limit_top, cam.limit_right, cam.limit_bottom,
			str(cam.enabled),
		]
	print("saved: %s map_size=%s tile_lookup=%d camera=%s" % [OUT_PATH, str(board.map_size), board.tile_lookup.size(), cam_info])
	get_tree().quit(0)


func _map_path_for_id(map_id: String) -> String:
	var candidates := [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	return ""
