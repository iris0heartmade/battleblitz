extends Node
## move_screenshot.gd — 走"移动模式"完整流程并截图。
##
## Prereq: FastAPI backend 在 127.0.0.1:8000 listening。
## 走完 create + join + add AI + start → WS connect → 等待 snapshot →
## 模拟鼠标点击己方单位 → 进入移动模式 → 模拟鼠标点击落点 →
## 等待 unit_moved event → 截图。

const _OUT_PATH := "user://move_screenshot.png"
const _WAIT_FOR_SNAPSHOT_SEC := 8.0
const _WAIT_FOR_MOVE_SEC := 4.0


func _ready() -> void:
	# 进游戏视图
	OS.set_environment("BB_AUTO_PLAY", "1")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main_app: Node = get_tree().current_scene
	if main_app.name == "MoveScreenshot":
		main_app = main_app.get_child(0) if main_app.get_child_count() > 0 else main_app
	if main_app != null and main_app.has_method("_on_free_play_pressed"):
		main_app.call("_on_free_play_pressed")
	# 等 snapshot
	var deadline: float = Time.get_ticks_msec() + int(_WAIT_FOR_SNAPSHOT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if GameState != null and GameState.players.size() > 0 and GameState.tiles.size() > 0:
			break
		await RenderingServer.frame_post_draw
	# 切到 game 视图
	var game_view: Node = main_app.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main_app.find_child("Menu", true, false)
		if menu != null: menu.visible = false
		var connecting: Node = main_app.find_child("Connecting", true, false)
		if connecting != null: connecting.visible = false
	for i in 4:
		await RenderingServer.frame_post_draw

	# 第一步:模拟点击 screen 上的一个己方单位
	# main_app.board 是 Board;每个 _unit_nodes_by_id 持有 UnitNode
	var board: Node = main_app.get("board") if main_app.get("board") != null else main_app.find_child("Board", true, false)
	if board == null:
		printerr("no board found")
		get_tree().quit(1)
		return
	var unit_nodes: Dictionary = board.get("_unit_nodes_by_id") if board.get("_unit_nodes_by_id") != null else {}
	# 找到第一个 owner_id == main_app._player_id 的单位
	var player_id: int = int(main_app.get("_player_id"))
	var units_layer: Node2D = board.get_node("UnitLayer") if board.has_node("UnitLayer") else null
	if units_layer == null or units_layer.get_child_count() == 0:
		printerr("no unit markers on board")
		get_tree().quit(1)
		return
	var target_unit: Node2D = null
	# UnitOut 用 player_id (int) 不是 color。Unit_data 是 dict
	# 包含 id/player_id/type/level/hp/...
	for child in units_layer.get_children():
		if child == null or not child.has_method("get"):
			continue
		var ud: Dictionary = child.get("unit_data") if child.get("unit_data") != null else {}
		var upid: int = int(ud.get("player_id", -1))
		if upid == player_id \
				and not bool(ud.get("has_acted", false)) \
				and not bool(ud.get("has_moved", false)):
			target_unit = child
			break
	if target_unit == null:
		print("DEBUG units on board: ", units_layer.get_child_count())
		for child in units_layer.get_children():
			if child != null:
				var ud: Dictionary = child.get("unit_data")
				print("  - id=%s type=%s player_id=%s has_acted=%s has_moved=%s pos=(%s,%s)" % [
					str(ud.get("id")), str(ud.get("unit_type", ud.get("type"))),
					str(ud.get("player_id")), str(ud.get("has_acted")),
					str(ud.get("has_moved")), str(ud.get("x")), str(ud.get("y"))
				])
		# fallback: 取第一个 unit
		var first: Node2D = units_layer.get_child(0) as Node2D if units_layer.get_child_count() > 0 else null
		if first != null:
			target_unit = first
			print("WARNING: no unacted unit owned by player %d; falling back to first unit (might be enemy)" % player_id)
	print("DEBUG picked unit: id=%s player_id=%s type=%s" % [
		str(target_unit.unit_data.get("id")), str(target_unit.unit_data.get("player_id")),
		str(target_unit.unit_data.get("unit_type", target_unit.unit_data.get("type")))
	])
	if target_unit == null:
		printerr("no unit found on board")
		get_tree().quit(1)
		return
	# 直接调 handler(不用 Input.parse_input_event — headless 难以走完整 _unhandled_input 链)
	# 1) 选中单位(走 board.emit_unit_clicked,但 board.pick_unit_at_screen 走 screen→cell → 这里直接 emit)
	# 2) 走 main._handle_unit_click(由 board unit_clicked signal 触发)
	board.emit_unit_clicked(int(target_unit.unit_data.get("id", -1)) if target_unit.unit_data != null else -1)
	for i in 4:
		await RenderingServer.frame_post_draw
	# 现在弹了 action bubble + 蓝色 reachable outline。
	# 模拟点移动按钮(走主函数 _on_move_pressed — ActionBubble 的 move_btn.pressed signal 已经连它)
	var move_btn_path: String = "GameView/HUD/ActionBubble/ActionList/MoveBtn"
	var move_btn: Button = main_app.get_node_or_null(move_btn_path)
	if move_btn != null and is_instance_valid(move_btn):
		move_btn.pressed.emit()
	for i in 4:
		await RenderingServer.frame_post_draw
	# 等 1 秒让状态机稳
	await get_tree().create_timer(1.0).timeout
	for i in 2:
		await RenderingServer.frame_post_draw

	# 第二步:模拟点击一个 reachable tile
	# 简单做法:取 _move_reachable_set 的一个非起点
	var mov_set: Dictionary = main_app.get("_move_reachable_set") if main_app.get("_move_reachable_set") != null else {}
	var picked_tile: Vector2i = Vector2i(-1, -1)
	var ud: Dictionary = target_unit.get("unit_data")
	var origin := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	for k in mov_set.keys():
		if Vector2i(k) != origin:
			picked_tile = Vector2i(k)
			break
	if picked_tile.x < 0:
		printerr("no reachable tile picked from set %s" % str(mov_set))
		get_tree().quit(1)
		return
	# 直接调 main._move_unit_to — 走 action_move + REST
	var uid: int = int(target_unit.unit_data.get("id", -1)) if target_unit.unit_data != null else -1
	main_app.call("_move_unit_to", uid, picked_tile.x, picked_tile.y)
	for i in 6:
		await RenderingServer.frame_post_draw

	# 等 unit_moved(原始位置 x/y 变化 → GameState更新)
	var deadline2: float = Time.get_ticks_msec() + int(_WAIT_FOR_MOVE_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline2:
		var moved := false
		# 查 GameState 里该 unit_id 的 x/y 是否已变
		if uid >= 0 and GameState != null:
			var u: Dictionary = GameState.get_unit(uid)
			if int(u.get("x", -1)) == picked_tile.x and int(u.get("y", -1)) == picked_tile.y:
				moved = true
		if moved:
			break
		await RenderingServer.frame_post_draw

	for i in 6:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://move_screenshot.png")
	print("Saved move screenshot → %s (moved unit to %s)" % [_OUT_PATH, str(picked_tile)])
	get_tree().quit(0)
