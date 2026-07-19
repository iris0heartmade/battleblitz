extends Node
## lobby_subview_screenshot.gd — 截 3 张图:自由模式 choose / create / join

const _OUT_DIR := "user://"
const _STEP_DELAY := 0.6


func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "1")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main: Node = get_tree().current_scene
	if main == null:
		printerr("no current scene")
		get_tree().quit(1); return

	# === Frame 1: 自由模式 choose 层 ===
	if main.has_method("_on_free_play_pressed"):
		main.call("_on_free_play_pressed")
		print("[lobby] frame 1: _on_free_play_pressed")
	await get_tree().create_timer(_STEP_DELAY).timeout
	for i in 3:
		await RenderingServer.frame_post_draw
	_save(main, "lobby_subview_1_choose.png")

	# === Frame 2: create view ===
	if main.has_method("_on_create_card_pressed"):
		main.call("_on_create_card_pressed")
		print("[lobby] frame 2: _on_create_card_pressed")
	await get_tree().create_timer(_STEP_DELAY).timeout
	for i in 3:
		await RenderingServer.frame_post_draw
	_save(main, "lobby_subview_2_create.png")

	# === Frame 3: join view ===
	if main.has_method("_on_join_card_pressed"):
		main.call("_on_join_card_pressed")
		print("[lobby] frame 3: _on_join_card_pressed")
	await get_tree().create_timer(_STEP_DELAY).timeout
	for i in 3:
		await RenderingServer.frame_post_draw
	_save(main, "lobby_subview_3_join.png")

	print("[lobby] done — 3 frames in user:// & res://")
	get_tree().quit(0)


func _save(_main: Node, name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("WARN: %s viewport image null" % name)
		return
	img.save_png(_OUT_DIR + name)
	img.save_png("res://" + name)
	print("  saved: %s" % name)