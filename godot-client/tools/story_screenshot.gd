extends Node
## story_screenshot.gd — render story/result/tutorial panels one at a time.

const _OUT_PATH := "user://story_screenshot.png"
const _OUT_DIR := "res://.refactor_shots/"

var _main: Node = null


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_OUT_DIR))
	await _settle()
	_main = _resolve_main()
	_prepare_game_view()
	await _capture_story_state("01_battle_result_only.png", "battle_result")
	await _capture_story_state("02_dialog_only.png", "dialog")
	await _capture_story_state("03_tutorial_only.png", "tutorial")
	print("Saved story modal screenshots")
	get_tree().quit(0)


func _settle() -> void:
	for i in 3:
		await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.5).timeout


func _resolve_main() -> Node:
	var root: Node = get_tree().current_scene
	if root != null and root.name == "StoryScreenshot":
		return root.get_child(0) if root.get_child_count() > 0 else root
	return root


func _prepare_game_view() -> void:
	if _main == null:
		return
	if _main.has_method("_show_view"):
		_main.call("_show_view", "game")
	var game_view: Node = _main.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
	var menu: Node = _main.find_child("Menu", true, false)
	if menu != null:
		menu.visible = false
	var board: Board = _main.find_child("Board", true, false)
	if board != null:
		for mp in [
			"res://../../game/maps/balanced_2p_15.json",
			"res://../game/maps/balanced_2p_15.json",
			"res://game/maps/balanced_2p_15.json",
		]:
			if FileAccess.file_exists(mp):
				var f := FileAccess.open(mp, FileAccess.READ)
				var parsed: Variant = JSON.parse_string(f.get_as_text())
				f.close()
				if parsed is Dictionary:
					board.load_map(parsed)
				break


func _capture_story_state(filename: String, state: String) -> void:
	_hide_all_story_modals()
	if _main != null and _main.has_method("_prepare_modal_layer"):
		_main.call("_prepare_modal_layer", state)
	match state:
		"battle_result":
			var battle: Panel = _main.find_child("BattleResultPanel", true, false)
			if battle != null:
				battle.visible = true
		"dialog":
			var dialog: Panel = _main.find_child("DialogPanel", true, false)
			var overlay: ColorRect = _main.find_child("DialogOverlay", true, false)
			if overlay != null:
				overlay.visible = true
			if dialog != null:
				dialog.visible = true
		"tutorial":
			var tutorial: Panel = _main.find_child("TutorialBubble", true, false)
			if tutorial != null:
				tutorial.visible = true
	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_DIR + filename)
	if state == "battle_result":
		img.save_png(_OUT_PATH)
		img.save_png("res://story_screenshot.png")


func _hide_all_story_modals() -> void:
	for name in ["DialogOverlay", "DialogPanel", "TutorialBubble", "BattleResultPanel", "WarReportPanel", "SettingsPanel", "PausePanel"]:
		var node: CanvasItem = _main.find_child(name, true, false) if _main != null else null
		if node != null:
			node.visible = false
