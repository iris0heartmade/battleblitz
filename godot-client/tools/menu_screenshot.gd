extends Node
## menu_screenshot.gd — capture the GBA-style main menu for visual review.

const _OUT_PATH := "user://menu_screenshot.png"


func _ready() -> void:
	for i in 5:
		await RenderingServer.frame_post_draw
	var main: Node = get_tree().current_scene
	var menu: Node = main.find_child("Menu", true, false)
	if menu != null:
		menu.visible = true
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://menu_screenshot.png")
	print("Saved menu screenshot → %s (%s)" % [_OUT_PATH, str(img.get_size())])
	get_tree().quit(0)