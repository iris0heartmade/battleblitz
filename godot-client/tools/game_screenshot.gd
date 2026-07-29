extends Node
## game_screenshot.gd — render the game view with HUD for visual review.

const _OUT_PATH := "user://game_screenshot.png"


func _ready() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	# Wait for Main's asynchronous startup view selection to finish before
	# applying the deterministic battle layout used by this screenshot.
	await get_tree().create_timer(0.5).timeout
	var root: Node = get_tree().current_scene
	var main: Node = root
	if root.name == "GameScreenshot":
		main = root.get_child(0) if root.get_child_count() > 0 else root
	# Force the game view visible, hide menu/connecting.
	if main.has_method("_show_view"):
		main.call("_show_view", "game")
	var game_view: Node = main.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main.find_child("Menu", true, false)
		if menu != null:
			menu.visible = false
		var connecting: Node = main.find_child("Connecting", true, false)
		if connecting != null:
			connecting.visible = false
	# Try to load a real map so the board has tiles to show.
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
	# Inject fake HUD content so we can see all 4 corner pills.
	var turn_panel: Node = main.find_child("TurnBadge", true, false)
	if turn_panel != null:
		var lbl: Label = turn_panel.find_child("Label", true, false)
		if lbl != null:
			lbl.text = "回合 3"
	var phase_panel: Node = main.find_child("PhaseBadge", true, false)
	if phase_panel != null:
		var lbl: Label = phase_panel.find_child("Label", true, false)
		if lbl != null:
			lbl.text = "🟢 玩家阶段"
	var cur_player_panel: Node = main.find_child("CurrentPlayerBadge", true, false)
	if cur_player_panel != null:
		var lbl: Label = cur_player_panel.find_child("Label", true, false)
		if lbl != null:
			lbl.text = "→ 学长"
	var gold_label: Label = main.find_child("GoldLabel", true, false)
	if gold_label != null:
		gold_label.text = "💰 500"
	var co_bar: ProgressBar = main.find_child("COBar", true, false)
	if co_bar != null:
		co_bar.value = 35.0
		co_bar.tooltip_text = "CO 能量: 35 / 100"
	var end_btn: Button = main.find_child("EndTurnButton", true, false)
	if end_btn != null:
		end_btn.disabled = false
	var ai_panel: Node = main.find_child("AIThinking", true, false)
	if ai_panel != null:
		ai_panel.visible = true
	# V2 第 3 轮:InfoPanel 假内容(选中单位 + 玩家列表)
	var unit_info_node: RichTextLabel = main.find_child("UnitInfo", true, false)
	if unit_info_node != null:
		var u: RichTextLabel = unit_info_node
		u.bbcode_enabled = true
		# Avoid nested [color] — Godot BBCode doesn't support it.
		# Use single-span tags per word group.
		u.text = "[color=#c9a14a][b]Lv.3 剑士 (Swordsman)[/b][/color]\n" \
			+ "[color=#5fa8e8]阵营:蓝方  ·  AI 友军[/color]\n\n" \
			+ "[color=#f4e8c1]HP[/color]  [color=#c63a3a]25 / 30[/color]\n" \
			+ "[color=#f4e8c1]MP[/color]  [color=#c9a14a]████████[/color][color=#5a4426]░░[/color]  [color=#f4e8c1]6/8[/color]\n" \
			+ "[color=#f4e8c1]ATK[/color] [color=#f0c75e]12[/color]    [color=#f4e8c1]DEF[/color] [color=#f0c75e]8[/color]\n" \
			+ "[color=#f4e8c1]MOV[/color] [color=#f0c75e]5[/color]     [color=#f4e8c1]RNG[/color] [color=#f0c75e]1[/color]\n\n" \
			+ "[color=#a89878]技能: 冲刺(攻击后移动 2 格)\n" \
			+ "状态: 正常\n" \
			+ "位置: (3, 5)[/color]"
	var players_node: RichTextLabel = main.find_child("PlayersList", true, false)
	if players_node != null:
		var p: RichTextLabel = players_node
		p.text = "[color=#e85a6a]🔴 学长[/color] — 3 单位 · 💰 500 · 🟢 行动中\n" \
			+ "[color=#5fa8e8]🔵 AI 蓝方[/color] — 3 单位 · 💰 450 · ⏳ 已结束回合\n" \
			+ "[color=#7ec97e]🟢 AI 绿方[/color] — 2 单位 · 💰 380 · 💀 已淘汰"
	# V2 第 3 轮补丁:Commander section 假数据(当前指挥官)
	var commander_name_node: RichTextLabel = main.find_child("CommanderName", true, false)
	if commander_name_node != null:
		commander_name_node.bbcode_enabled = true
		commander_name_node.text = "🔴 [color=#e85a6a][b]学长[/b][/color]  ·  3 单位 · 💰 500"
	var commander_co_node: ProgressBar = main.find_child("CommanderCOBar", true, false)
	if commander_co_node != null:
		commander_co_node.value = 35.0
		commander_co_node.tooltip_text = "CO 能量: 35 / 100"
	# V2 第 4 轮:ActionBubble 假可见(浮在棋盘中央右侧,模拟选中单位)
	var bubble: Panel = main.find_child("ActionBubble", true, false)
	if bubble != null:
		bubble.visible = true
		bubble.position = Vector2(550, 280)
	# V2 第 5 轮:WarReportPanel 假可见(屏幕中央,带战报日志)
	var war_panel: Panel = main.find_child("WarReportPanel", true, false)
	if war_panel != null:
		war_panel.visible = true
		var log: RichTextLabel = war_panel.find_child("ActionLog", true, false)
		if log != null:
			log.bbcode_enabled = true
			log.text = "[color=#f0c75e]═══ 第 3 回合 ═══[/color]\n\n" \
				+ "[color=#e85a6a]⚔ #12 → #8: 14 dmg (暴击!)[/color]\n" \
				+ "[color=#f4e8c1]🚶 #5 从 (3,4) 移动到 (5,6), 消耗 3 MP[/color]\n" \
				+ "[color=#c63a3a]💀 #8 被击杀[/color]\n" \
				+ "[color=#f4e8c1]👑 #3 占领 城堡 → 红方 +50g[/color]\n" \
				+ "[color=#a89878]🔮 玩家 #7 释放 治疗术, #3 HP +12[/color]\n" \
				+ "[color=#f0c75e]⚔ #11 → #9: 9 dmg[/color]\n" \
				+ "[color=#f4e8c1]💤 #1 进入待命状态[/color]\n" \
				+ "[color=#a89878]⚡ 红方 CO 能量 +8 → 43/100[/color]\n"
	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://game_screenshot.png")
	print("Saved game screenshot → %s" % _OUT_PATH)
	get_tree().quit(0)
