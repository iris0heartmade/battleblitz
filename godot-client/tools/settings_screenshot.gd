extends Node
## settings_screenshot.gd — capture the settings + pause panels for visual review.

const _OUT_PATH := "user://settings_screenshot.png"


func _ready() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	var root: Node = get_tree().current_scene
	var main: Node = root
	if root.name == "SettingsScreenshot":
		main = root.get_child(0) if root.get_child_count() > 0 else root
	# Show game view, hide menu/connecting.
	var game_view: Node = main.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main.find_child("Menu", true, false)
		if menu != null:
			menu.visible = false
	# Load map for background context.
	var board: Board = main.find_child("Board", true, false)
	if board != null:
		var map_paths := [
			"res://../../game/maps/balanced_2p_15.json",
			"res://../game/maps/balanced_2p_15.json",
			"res://game/maps/balanced_2p_15.json",
		]
		for mp in map_paths:
			if FileAccess.file_exists(mp):
				var f := FileAccess.open(mp, FileAccess.READ)
				var text := f.get_as_text()
				f.close()
				var parsed: Variant = JSON.parse_string(text)
				if parsed is Dictionary:
					board.load_map(parsed)
				break
	# Show settings panel.
	var settings: Panel = main.find_child("SettingsPanel", true, false)
	if settings != null:
		settings.visible = true
	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://settings_screenshot.png")
	print("Saved settings screenshot → %s" % _OUT_PATH)
	get_tree().quit(0)