extends Node
## portrait_check_screenshot.gd — 直接测试 _load_portrait + _set_unit_info_portrait
## 加载完整 main.tscn(保证 @onready 全部就位),切到 game view,
## 调 portrait 函数 + 把 panel 显式 visible(避免被 game view 的 show/hide 影响)。

const _OUT_DIR := "res://.refactor_shots/"
const _MAIN_SCENE := "res://scenes/main.tscn"


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(_OUT_DIR)
	await _await_frames(6)
	var main_scene := load(_MAIN_SCENE) as PackedScene
	if main_scene == null:
		printerr("[portrait_check] failed to load main.tscn"); get_tree().quit(1); return
	var main := main_scene.instantiate()
	add_child(main)
	await _await_frames(6)
	print("[portrait_check] main added, _user_name=%s" % str(main._user_name))
	# 切到 game view
	main._game_id = 1
	main._player_id = 1
	main._show_view("game")
	await _await_frames(3)
	# Use the production path; never force visibility, otherwise this screenshot
	# hides regressions where unit selection no longer enables the portrait card.
	main._set_unit_info_portrait("yun")
	await _await_frames(3)
	if main.hero_portrait_panel == null or not main.hero_portrait_panel.visible:
		printerr("[portrait_check] production portrait panel stayed hidden")
		get_tree().quit(1)
		return
	if main._unit_info_portrait_tex == null or main._unit_info_portrait_tex.texture == null:
		printerr("[portrait_check] production portrait texture was not loaded")
		get_tree().quit(1)
		return
	if main.hero_portrait_panel != null:
		print("[portrait_check] panel.size=%s visible=%s pos=%s" % [
			str(main.hero_portrait_panel.size),
			str(main.hero_portrait_panel.visible),
			str(main.hero_portrait_panel.position),
		])
	if main._unit_info_portrait_tex != null:
		var tex = main._unit_info_portrait_tex.texture
		print("[portrait_check] tex.size=%s visible=%s pos=%s texture=%s" % [
			str(main._unit_info_portrait_tex.size),
			str(main._unit_info_portrait_tex.visible),
			str(main._unit_info_portrait_tex.position),
			"set" if tex != null else "NULL",
		])
		if tex != null:
			print("[portrait_check] texture.size=%s" % str(tex.get_size()))
	_save(main)
	get_tree().quit(0)


func _await_frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _save(main: Node) -> void:
	var img := get_viewport().get_texture().get_image()
	if img == null:
		print("WARN: viewport image null")
		return
	img.save_png(_OUT_DIR + "portrait_check.png")
	print("[portrait_check] saved: portrait_check.png (%dx%d)" % [img.get_width(), img.get_height()])
