extends Node
## flow_screenshot.gd — v0.3 端到端 demo 录制
## 把 M4 三个动作(选中 → 移动 → 攻击)串起来 + 截图,
## 演示"完整 1 局 vs AI"的核心循环。
##
## Prereq: FastAPI backend 在 127.0.0.1:8000 listening.
## 流程:create + join + AI + start → WS snapshot → 选中己方 →
##       移动到邻居 → 攻击敌方(force range) → 截图存到 tsscreenshots/。

const _OUT_DIR := "user://"
const _WAIT_SNAPSHOT_SEC := 8.0
const _WAIT_ACTION_SEC := 5.0
const _STEP_DELAY := 0.4


func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "1")
	OS.set_environment("BB_ATTACK_FORCE_RANGE", "10")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main_app: Node = get_tree().current_scene
	if main_app.name == "FlowScreenshot":
		main_app = main_app.get_child(0) if main_app.get_child_count() > 0 else main_app
	if main_app != null and main_app.has_method("_start_dev_ai_game"):
		main_app.call("_start_dev_ai_game")
	# 等 snapshot
	var deadline: float = Time.get_ticks_msec() + int(_WAIT_SNAPSHOT_SEC * 1000.0)
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
	for i in 6:
		await RenderingServer.frame_post_draw

	# Frame 0:"开局 — 选单位"
	await get_tree().create_timer(0.3).timeout
	_save(main_app, "flow_v0_3_d0_setup.png")
	print("[v0.3 demo] frame 0 saved: setup")

	# Frame 1:"选中己方单位 — 行动气泡"
	var board: Node = main_app.get("board") if main_app.get("board") != null else main_app.find_child("Board", true, false)
	var units_layer: Node2D = board.get_node_or_null("UnitLayer") if board != null else null
	if units_layer == null or units_layer.get_child_count() == 0:
		printerr("no units")
		get_tree().quit(1); return
	var player_id: int = int(main_app.get("_player_id"))
	var attacker: Node2D = null
	for child in units_layer.get_children():
		if child == null or not child.has_method("get"): continue
		var ud: Dictionary = child.get("unit_data") if child.get("unit_data") != null else {}
		if int(ud.get("player_id", -1)) == player_id \
				and not bool(ud.get("has_acted", false)):
			attacker = child
			break
	if attacker == null:
		attacker = units_layer.get_child(0) as Node2D
	if attacker == null:
		printerr("no attacker")
		get_tree().quit(1); return
	# 选中
	board.emit_unit_clicked(int(attacker.unit_data.get("id", -1)))
	await get_tree().create_timer(_STEP_DELAY).timeout
	for i in 2: await RenderingServer.frame_post_draw
	_save(main_app, "flow_v0_3_d1_selected.png")
	print("[v0.3 demo] frame 1 saved: unit selected — bubble visible")

	# Frame 2:"移动模式 — 蓝框"
	var move_btn: Button = main_app.get_node_or_null("GameView/HUD/ActionBubble/ActionList/MoveBtn")
	if move_btn != null:
		move_btn.pressed.emit()
	await get_tree().create_timer(_STEP_DELAY).timeout
	for i in 2: await RenderingServer.frame_post_draw
	_save(main_app, "flow_v0_3_d2_move_mode.png")
	print("[v0.3 demo] frame 2 saved: move mode — blue reachable outline")

	# 选择 reachable set 内 1 个 tile → POST /move
	var mov_set: Dictionary = main_app.get("_move_reachable_set") if main_app.get("_move_reachable_set") != null else {}
	var origin_x: int = int(attacker.unit_data.get("x", -1))
	var origin_y: int = int(attacker.unit_data.get("y", -1))
	var pick: Vector2i = Vector2i(-1, -1)
	for k in mov_set.keys():
		if Vector2i(k) != Vector2i(origin_x, origin_y):
			pick = Vector2i(k)
			break
	if pick.x >= 0:
		main_app.call("_move_unit_to", int(attacker.unit_data.get("id")), pick.x, pick.y)
		await get_tree().create_timer(_STEP_DELAY).timeout
		for i in 2: await RenderingServer.frame_post_draw
		_save(main_app, "flow_v0_3_d3_after_move.png")
		print("[v0.3 demo] frame 3 saved: after POST /move")

	# Frame 4:"进入攻击模式 — 红框"
	# 重新选中 attacker(可能已移动过,id 不变)
	var new_attacker: Node2D = null
	for child in units_layer.get_children():
		if child == null or not child.has_method("get"): continue
		var ud2: Dictionary = child.get("unit_data") if child.get("unit_data") != null else {}
		if int(ud2.get("id", -1)) == int(attacker.unit_data.get("id", -1)):
			new_attacker = child
			break
	if new_attacker != null:
		board.emit_unit_clicked(int(attacker.unit_data.get("id", -1)))
		await get_tree().create_timer(_STEP_DELAY).timeout
		var attack_btn: Button = main_app.get_node_or_null("GameView/HUD/ActionBubble/ActionList/AttackBtn")
		if attack_btn != null:
			attack_btn.pressed.emit()
		await get_tree().create_timer(_STEP_DELAY).timeout
		for i in 2: await RenderingServer.frame_post_draw
		_save(main_app, "flow_v0_3_d4_attack_mode.png")
		print("[v0.3 demo] frame 4 saved: attack mode — red outline")

	# Frame 5:"挑第一个目标 → POST /attack → 截图"
	var atk_targets: Dictionary = main_app.get("_attack_targets") if main_app.get("_attack_targets") != null else {}
	if not atk_targets.is_empty():
		var first_tid: int = int(atk_targets.keys()[0])
		main_app.call("_attack_unit_to", int(attacker.unit_data.get("id")), first_tid)
		await get_tree().create_timer(_WAIT_ACTION_SEC).timeout
		for i in 2: await RenderingServer.frame_post_draw
		_save(main_app, "flow_v0_3_d5_after_attack.png")
		print("[v0.3 demo] frame 5 saved: after POST /attack (defender hp reduced)")
	else:
		print("[v0.3 demo] frame 5 skipped: no attack targets (force range too small)")

	# Frame 6:Inspect bubble — 选中敌方(已 action)单位
	var board2: Node = main_app.get("board") if main_app.get("board") != null else main_app.find_child("Board", true, false)
	if board2 != null:
		var t_layer: Node2D = board2.get_node_or_null("UnitLayer")
		if t_layer != null and t_layer.get_child_count() > 0:
			var enemy: Node2D = null
			for c in t_layer.get_children():
				if c == null or not c.has_method("get"): continue
				var ud2: Dictionary = c.get("unit_data") if c.get("unit_data") != null else {}
				if int(ud2.get("player_id", -1)) != player_id:
					enemy = c
					break
			if enemy != null:
				board2.emit_unit_clicked(int(enemy.unit_data.get("id", -1)))
				await get_tree().create_timer(_STEP_DELAY).timeout
				for i in 2: await RenderingServer.frame_post_draw
				_save(main_app, "flow_v0_3_d6_inspect.png")
				print("[v0.3 demo] frame 6 saved: inspect enemy unit — InfoPanel filled")
			else:
				print("[v0.3 demo] frame 6 skipped: no enemy found")
		else:
			print("[v0.3 demo] frame 6 skipped: UnitLayer empty or null")
	else:
		print("[v0.3 demo] frame 6 skipped: no board")

	# Frame 7:end_turn after action
	var end_turn_button_path: String = "GameView/HUD/TopRight/EndTurnButton"
	var end_turn_button: Button = main_app.get_node_or_null(end_turn_button_path) as Button
	if end_turn_button != null and is_instance_valid(end_turn_button):
		end_turn_button.pressed.emit()
		await get_tree().create_timer(_WAIT_ACTION_SEC).timeout
		for i in 2: await RenderingServer.frame_post_draw
		_save(main_app, "flow_v0_3_d7_after_endturn.png")
		print("[v0.3 demo] frame 7 saved: after end-turn (AI thinking phase)")
	else:
		print("[v0.3 demo] frame 7 skipped: no EndTurnButton")

	print("[v0.3 demo] done — 6 frames in res://  &  user://")
	get_tree().quit(0)


# 同步 save — 调用者需自己 await frame_post_draw 后再调用。
func _save(main_app: Node, name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("WARN: %s viewport image null" % name)
		return
	img.save_png(_OUT_DIR + name)
	img.save_png("res://" + name)
	print("  saved: %s" % name)
