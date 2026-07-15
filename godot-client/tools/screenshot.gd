extends Node
## screenshot.gd — render the main scene to a PNG for visual review.
##
## Run with:
##   "<godot_exe>" --rendering-driver opengl3 --path godot-client res://tools/screenshot.tscn
## or open the project in the editor and run the Screenshot scene.
##
## Forces a few redraws and then writes `user://screenshot.png` AND
## `res://screenshot.png` (the latter for easier discovery in the
## project tree).

const MAP_TO_RENDER := "balanced_2p_15"
const _OUT_PATH := "user://screenshot.png"


func _ready() -> void:
	await get_tree().process_frame
	# Load the map.
	var board: Board = get_tree().current_scene.find_child("Board")
	if board == null:
		# We might be the current scene. Walk children for a Board.
		for c in get_tree().current_scene.get_children():
			if c is Board:
				board = c
				break
	if board == null:
		printerr("screenshot.gd: no Board found in scene")
		get_tree().quit(1)
		return
	var map_path := _map_path_for_id(MAP_TO_RENDER)
	if map_path == "":
		printerr("screenshot.gd: no map file found for %s" % MAP_TO_RENDER)
		get_tree().quit(1)
		return
	var f := FileAccess.open(map_path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()
	var parsed: Variant = JSON.parse_string(text)
	board.load_map(parsed)
	# Wait a few frames for the renderer to settle.
	for i in 3:
		await RenderingServer.frame_post_draw
	# Grab the viewport image.
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("screenshot.gd: viewport returned null image (headless?)")
		get_tree().quit(1)
		return
	var err := img.save_png(_OUT_PATH)
	if err != OK:
		printerr("screenshot.gd: save_png failed: %s" % error_string(err))
		get_tree().quit(1)
		return
	# Mirror to res:// so it shows up in the editor.
	img.save_png("res://screenshot.png")
	# Debug: count how many cells were actually set on the TileMapLayers.
	var terrain_layer: TileMapLayer = board.ground_layer
	var castle_layer: TileMapLayer = board.structure_layer
	var set_count := 0
	var seen_coords: Dictionary = {}
	for y in 30:
		for x in 30:
			var c := terrain_layer.get_cell_source_id(Vector2i(x, y))
			if c != -1:
				set_count += 1
				seen_coords[Vector2i(x, y)] = true
	print("Saved screenshot → %s" % _OUT_PATH)
	print("  terrain_layer cells set (30x30 sample): %d" % set_count)
	print("  tile_lookup size: %d" % board.tile_lookup.size())
	print("  board.map_size: %s" % str(board.map_size))
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
