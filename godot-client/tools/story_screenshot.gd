extends Node
## story_screenshot.gd — render dialog/tutorial/battle-result panels for review.

const _OUT_PATH := "user://story_screenshot.png"


func _ready() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	# Main performs asynchronous startup work and may restore its default view
	# after this wrapper's first frames. Let that settle before forcing the
	# battle/story state used by this visual regression capture.
	await get_tree().create_timer(0.5).timeout
	var root: Node = get_tree().current_scene
	var main: Node = root
	if root.name == "StoryScreenshot":
		main = root.get_child(0) if root.get_child_count() > 0 else root
	# Show game view.
	if main.has_method("_show_view"):
		main.call("_show_view", "game")
	var game_view: Node = main.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main.find_child("Menu", true, false)
		if menu != null:
			menu.visible = false
	# Load map.
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
	# HUD pills
	var turn_panel: Node = main.find_child("TurnBadge", true, false)
	if turn_panel != null:
		var lbl: Label = turn_panel.find_child("Label", true, false)
		if lbl != null:
			lbl.text = "回合 18"
	var phase_panel: Node = main.find_child("PhaseBadge", true, false)
	if phase_panel != null:
		var lbl: Label = phase_panel.find_child("Label", true, false)
		if lbl != null:
			lbl.text = "🏆 战斗结束"
	# Show all 3 V2 round-7 panels.
	var dialog: Panel = main.find_child("DialogPanel", true, false)
	if dialog != null:
		dialog.visible = true
	var tutorial: Panel = main.find_child("TutorialBubble", true, false)
	if tutorial != null:
		tutorial.visible = true
	var battle: Panel = main.find_child("BattleResultPanel", true, false)
	if battle != null:
		battle.visible = true
	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://story_screenshot.png")
	print("Saved story screenshot → %s" % _OUT_PATH)
	get_tree().quit(0)
