extends Node
## game_screenshot.gd — render the game view with HUD for visual review.

const _OUT_PATH := "user://game_screenshot.png"


func _ready() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	var root: Node = get_tree().current_scene
	var main: Node = root
	if root.name == "GameScreenshot":
		main = root.get_child(0) if root.get_child_count() > 0 else root
	# Force the game view visible, hide menu/connecting.
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