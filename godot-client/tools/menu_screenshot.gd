extends Node
## menu_screenshot.gd — capture the GBA-style main menu for visual review.

const _OUT_PATH := "user://menu_screenshot.png"


func _ready() -> void:
	for i in 5:
		await RenderingServer.frame_post_draw
	# Manually draw a known-size ColorRect over everything to confirm
	# where the viewport actually renders.
	var root_vp := get_viewport()
	printerr("=== viewport ===")
	printerr("  visible_rect: %s" % str(root_vp.get_visible_rect()))
	printerr("  size: %s" % str(root_vp.size))
	printerr("  transform: %s" % str(root_vp.get_canvas_transform()))
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	printerr("image size: %s" % str(img.get_size()))
	img.save_png(_OUT_PATH)
	img.save_png("res://menu_screenshot.png")
	print("Saved → %s" % _OUT_PATH)
	get_tree().quit(0)