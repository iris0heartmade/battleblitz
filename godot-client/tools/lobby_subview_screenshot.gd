extends Node
## lobby_subview_screenshot.gd — 截 4 张图:联机大厅 choose / create / join / in-room

const _OUT_DIR := "user://"
const _STEP_DELAY := 0.6


func _ready() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	var main: Node = get_tree().current_scene
	if main == null:
		printerr("no current scene")
		get_tree().quit(1); return

	# === Frame 1: lobby choose 层 ===
	if main.has_method("_on_lobby_pressed"):
		main.call("_on_lobby_pressed")
		print("[lobby] frame 1: _on_lobby_pressed")
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

	# === Frame 4: in_room 视图(房主控制台)— 走真实创建流程
	# 先回到 choose → 创建卡片 → 触发 create_game
	if main.has_method("_show_lobby_choose"):
		main.call("_show_lobby_choose")
		print("[lobby] frame 4a: back to choose")
	await get_tree().create_timer(0.3).timeout
	# 点 CreateCardBtn 触发创建
	if main.has_method("_on_create_card_pressed"):
		main.call("_on_create_card_pressed")
		print("[lobby] frame 4b: click create card")
	await get_tree().create_timer(0.4).timeout
	# 点 CreateRoomBtn 提交创建表单
	var create_btn: Button = main.get_node_or_null(
		"Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateRoomBtn"
	) as Button
	if create_btn != null:
		create_btn.pressed.emit()
		print("[lobby] frame 4c: click CreateRoomBtn")
	# 等后端 create + join 完成,自动跳到 in_room
	await get_tree().create_timer(3.0).timeout
	for i in 3:
		await RenderingServer.frame_post_draw
	_save(main, "lobby_subview_4_in_room.png")
	print("[lobby] frame 4: in_room (real create+join)")

	print("[lobby] done — 4 frames in user:// & res://")
	get_tree().quit(0)


func _save(_main: Node, name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("WARN: %s viewport image null" % name)
		return
	img.save_png(_OUT_DIR + name)
	img.save_png("res://" + name)
	print("  saved: %s" % name)
