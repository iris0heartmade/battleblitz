extends Node2D

const OUT_PATH := "res://screenshots/claim_badge_check.png"


func _ready() -> void:
	get_window().size = Vector2i(360, 180)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://screenshots"))

	var scene: PackedScene = load("res://scenes/board.tscn")
	var board: Board = scene.instantiate()
	board.position = Vector2(80, 70)
	add_child(board)
	await get_tree().process_frame

	GameState.players = [
		{"id": 1, "user_name": "Red", "color": "red"},
		{"id": 2, "user_name": "Blue", "color": "blue"},
	]
	GameState.pending_claims = [
		{"tile_x": 1, "tile_y": 0, "turns_remaining": 1, "total_turns": 2, "target_player_id": 2},
		{"tile_x": 2, "tile_y": 0, "turns_remaining": 1, "total_turns": 2, "target_player_id": 1},
	]

	board.load_map({
		"width": 3,
		"height": 1,
		"biome": "grass",
		"layout": ["vbv"],
	})
	board.rebuild_flags([
		{"x": 0, "y": 0, "terrain": "village", "owner_id": 1},
		{"x": 1, "y": 0, "terrain": "barracks", "owner_id": 1},
		{"x": 2, "y": 0, "terrain": "village", "owner_id": null},
	])

	for i in range(3):
		await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img == null:
		printerr("claim_badge_screenshot: viewport image unavailable")
		get_tree().quit(1)
		return
	img.save_png(OUT_PATH)
	print("claim_badge_screenshot: saved %s (%dx%d)" % [OUT_PATH, img.get_width(), img.get_height()])
	get_tree().quit(0)
