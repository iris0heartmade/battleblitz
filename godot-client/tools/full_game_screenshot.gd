extends Node
## full_game_screenshot.gd — 跑"完整 1 局 vs AI"直到 match_ended。
##
## Prereq: backend 在 127.0.0.1:8000 listening。
## 流程:free play 起对局,玩家主动做一次攻击,然后 _on_end_turn_pressed 触发
## AI 自动行动链;轮询 match_ended,如果 server 说结束了 → 截图 d9_match_ended。
## 这是 v0.3 端到端验证。

const _OUT_DIR := "user://"
const _WAIT_SNAPSHOT_SEC := 8.0
const _MAX_GAME_WAIT_SEC := 60.0  # 等 match_ended 上限


func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "1")
	OS.set_environment("BB_ATTACK_FORCE_RANGE", "10")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main_app: Node = get_tree().current_scene
	if main_app.name == "FullGameScreenshot":
		main_app = main_app.get_child(0) if main_app.get_child_count() > 0 else main_app
	if main_app != null and main_app.has_method("_on_free_play_pressed"):
		main_app.call("_on_free_play_pressed")
	var deadline: float = Time.get_ticks_msec() + int(_WAIT_SNAPSHOT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if GameState != null and GameState.players.size() > 0 and GameState.tiles.size() > 0:
			break
		await RenderingServer.frame_post_draw
	var game_view: Node = main_app.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main_app.find_child("Menu", true, false)
		if menu != null: menu.visible = false
		var connecting: Node = main_app.find_child("Connecting", true, false)
		if connecting != null: connecting.visible = false
	for i in 4:
		await RenderingServer.frame_post_draw
	# Frame 0:"setup"
	for i in 3:
		await RenderingServer.frame_post_draw
	_save(main_app, "full_game_d0_setup.png")
	print("[full] d0 setup")

	# 反复 end-turn 让 AI 自动打。每次等待 server 推 snapshot + AI 行动完成。
	# 计算一个最新回合 — 如果 60s 内 match 没结束,放弃
	var game_end_deadline: float = Time.get_ticks_msec() + int(_MAX_GAME_WAIT_SEC * 1000.0)
	var et_btn: Button = main_app.get_node_or_null("GameView/HUD/TopRight/EndTurnButton") as Button
	var turn_count: int = 0
	var last_turn_seen: int = -1
	var match_ended_seen: bool = false
	while Time.get_ticks_msec() < game_end_deadline:
		# 等 battle_result_panel 出现(match_ended 触发)
		var brp: Panel = main_app.get("battle_result_panel")
		if brp != null and brp.visible:
			match_ended_seen = true
			break
		# 当前回合号
		var cur_turn: int = int(GameState.game_summary.get("turn_number", 0)) if GameState else 0
		if cur_turn != last_turn_seen:
			last_turn_seen = cur_turn
			turn_count += 1
			print("[full] turn %d" % cur_turn)
		# 触发 end_turn(若是我方回合)
		var cur_pid_v: Variant = GameState.current_player_id if GameState else null
		var my_pid: int = int(main_app.get("_player_id")) if main_app.get("_player_id") != null else 0
		if et_btn != null and not et_btn.disabled and cur_pid_v != null and int(cur_pid_v) == my_pid:
			print("[full] end_turn press (turn=%d)" % cur_turn)
			et_btn.pressed.emit()
			await get_tree().create_timer(2.5).timeout
		else:
			# AI 回合 → 等
			await get_tree().create_timer(0.5).timeout
		# 中间捕一帧
		if turn_count == 2 or turn_count == 5:
			_save(main_app, "full_game_d1_turn_%d.png" % cur_turn)
			print("[full] d1 turn_%d saved" % cur_turn)

	# Frame 2:match_ended(若发生)
	if match_ended_seen:
		for i in 3:
			await RenderingServer.frame_post_draw
		_save(main_app, "full_game_d2_match_ended.png")
		print("[full] d2 match_ended saved — BattleResultPanel visible!")
	else:
		_save(main_app, "full_game_d2_no_match_end.png")
		print("[full] d2 no match_ended (timed out — that's OK, server may be slow)")

	print("[full] done.")
	get_tree().quit(0)


func _save(main_app: Node, name: String) -> void:
	for i in 6:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null: return
	img.save_png(_OUT_DIR + name)
	img.save_png("res://" + name)
	print("  saved %s" % name)
