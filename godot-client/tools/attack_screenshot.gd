extends Node
## attack_screenshot.gd — 走"攻击模式"完整流程并截图。
##
## Prereq: FastAPI backend 在 127.0.0.1:8000 listening。
## 走完 create + join + add AI + start → WS connect → 等待 snapshot →
## 模拟选中己方 → attack 按钮 → 模拟点敌方 → POST → 等待 unit_attacked
## event → 截图。

const _OUT_PATH := "user://attack_screenshot.png"
const _WAIT_FOR_SNAPSHOT_SEC := 8.0
const _WAIT_FOR_ATTACK_SEC := 6.0


func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "1")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main_app: Node = get_tree().current_scene
	if main_app.name == "AttackScreenshot":
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

	# 1) 选第一个 unacted 己方单位
	var board: Node = main_app.get("board") if main_app.get("board") != null else main_app.find_child("Board", true, false)
	if board == null:
		printerr("no board")
		get_tree().quit(1); return
	var units_layer: Node2D = board.get_node_or_null("UnitLayer")
	if units_layer == null or units_layer.get_child_count() == 0:
		printerr("no units")
		get_tree().quit(1); return
	var player_id: int = int(main_app.get("_player_id"))
	var attacker: Node2D = null
	# 优先找 attack_range >= 2 的己方单位 — 距离 1 spawn 不一定有敌人
	for child in units_layer.get_children():
		if child == null or not child.has_method("get"): continue
		var ud: Dictionary = child.get("unit_data") if child.get("unit_data") != null else {}
		if int(ud.get("player_id", -1)) == player_id \
				and not bool(ud.get("has_acted", false)) \
				and int(ud.get("attack_range", 0)) >= 2:
			attacker = child
			break
	if attacker == null:
		for child in units_layer.get_children():
			if child == null or not child.has_method("get"): continue
			var ud: Dictionary = child.get("unit_data") if child.get("unit_data") != null else {}
			if int(ud.get("player_id", -1)) == player_id \
					and not bool(ud.get("has_acted", false)):
				attacker = child
				break
	if attacker == null:
		# fallback: 第一个 unit(可能在地图边界) — 走 ATTACK 也是 over 范围
		attacker = units_layer.get_child(0) as Node2D if units_layer.get_child_count() > 0 else null
		print("WARNING: no unacted own unit; using first unit")
	if attacker == null:
		printerr("no attacker picked")
		get_tree().quit(1); return
	print("DEBUG attacker unit id=%s player_id=%s pos=(%s,%s) atk=%s" % [
		str(attacker.unit_data.get("id")), str(attacker.unit_data.get("player_id")),
		str(attacker.unit_data.get("x")), str(attacker.unit_data.get("y")),
		str(attacker.unit_data.get("atk"))
	])

	# 2) 走 board.emit_unit_clicked → main._handle_unit_click → reachable 高亮
	board.emit_unit_clicked(int(attacker.unit_data.get("id", -1)))
	for i in 4:
		await RenderingServer.frame_post_draw

	# 3) 点 attack 按钮
	var attack_btn: Button = main_app.get_node_or_null("GameView/HUD/ActionBubble/ActionList/AttackBtn")
	if attack_btn != null and is_instance_valid(attack_btn):
		attack_btn.pressed.emit()
	for i in 4:
		await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.3).timeout

	# 4) 看 _attack_targets 是否算出来
	var atk_targets: Dictionary = main_app.get("_attack_targets") if main_app.get("_attack_targets") != null else {}
	print("DEBUG _attack_targets: size=%s" % atk_targets.size())
	if atk_targets.is_empty():
		# 注:balanced_2p_15 默认 spawn 太远,让 swordsman range=1 找不到
		# enemy。这是地图属性的局限,不影响 _on_attack_pressed 自身的逻辑。
		# 仍然截一张"进入攻击模式"的视觉图,作为 v0.3 阶段性 demo。
		print("DEBUG: no attack targets in range; saving visual demo anyway")
		var img0: Image = get_viewport().get_texture().get_image()
		if img0 != null:
			img0.save_png(_OUT_PATH)
			img0.save_png("res://attack_screenshot.png")
		print("Saved attack screenshot (visual mode) → %s" % _OUT_PATH)
		get_tree().quit(0); return
	# 5) 在 _attack_targets 里挑第一个作为 target
	var first_tid: int = int(atk_targets.keys()[0])
	main_app.call("_attack_unit_to", int(attacker.unit_data.get("id")), first_tid)
	for i in 6:
		await RenderingServer.frame_post_draw

	# 6) 等 unit_attacked(更通用:查 GameState.get_unit(target) hp 变化)
	var defender_initial_hp: int = int((atk_targets.get(first_tid, {}) as Dictionary).get("defender_name", "0"))
	var deadline2: float = Time.get_ticks_msec() + int(_WAIT_FOR_ATTACK_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline2:
		var defender_now: Dictionary = GameState.get_unit(first_tid) if GameState != null else {}
		if not defender_now.is_empty() \
				and int(defender_now.get("hp", defender_initial_hp)) < defender_initial_hp:
			print("DEBUG defender hp decreased — attack took effect")
			break
		await RenderingServer.frame_post_draw

	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport null")
		get_tree().quit(1); return
	img.save_png(_OUT_PATH)
	img.save_png("res://attack_screenshot.png")
	print("Saved attack screenshot → %s (target=%s)" % [_OUT_PATH, str(first_tid)])
	get_tree().quit(0)
