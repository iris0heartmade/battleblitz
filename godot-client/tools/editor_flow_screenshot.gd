extends Node
## editor_flow_screenshot.gd — P2 重构验证:地图编辑器进出页面截图。
## 加载 main.tscn,模拟「主菜单 → 进编辑器 → 绘制 → 撤销 → 返回菜单 → 重入」,
## 每步截图,验证 editor_controller.gd 组件抽离后全链路(含 back_requested 信号解耦)正常。
## Prereq: 后端 127.0.0.1:8000 listening(open() 会拉取已保存地图列表)。

const _OUT_DIR := "res://.refactor_shots/"


func _await_frames(n: int) -> void:
	for i in n:
		await RenderingServer.frame_post_draw


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(_OUT_DIR)
	await _await_frames(6)
	var main_app: Node = get_tree().current_scene
	if main_app != null and main_app.name == "EditorFlowScreenshot" and main_app.get_child_count() > 0:
		main_app = main_app.get_child(0)
	await _await_frames(3)

	# 1) 主菜单
	_save("01_menu.png")
	_diag_cc(main_app, "01 首次 menu")
	print("[editor_flow] 1: main menu")

	# 2) 进入编辑器(main._on_editor_pressed → _show_view + editor_view.open())
	main_app.call("_on_editor_pressed")
	await get_tree().create_timer(1.2).timeout   # 等 open() 的 list_editor_maps 异步返回
	await _await_frames(5)
	var editor_view: Node = main_app.find_child("EditorView", true, false)
	if editor_view == null:
		printerr("[editor_flow] EditorView not found"); get_tree().quit(1); return
	_save("02_editor_open.png")
	print("[editor_flow] 2: editor opened, visible=%s" % str(editor_view.visible))

	# 3) 切地形笔刷为「山地M」(第3项)再绘制,让编辑效果在草原上明显可见
	var terrain_opt: Node = editor_view.get_node_or_null("EditorPanel/EditorTerrainOption")
	if terrain_opt != null:
		terrain_opt.select(2)  # _editor_terrain_chars=["P","F","M",...] → M 山地
	for t in [Vector2i(2, 2), Vector2i(3, 2), Vector2i(4, 2), Vector2i(5, 2), Vector2i(2, 3), Vector2i(3, 3), Vector2i(4, 3), Vector2i(5, 3), Vector2i(2, 4), Vector2i(3, 4)]:
		editor_view.call("_on_editor_tile_clicked", t)
	await _await_frames(5)
	_save("03_editor_painted.png")
	print("[editor_flow] 3: painted 10 mountain tiles")

	# 4) 撤销一步(request_undo → _on_editor_undo_pressed)
	editor_view.call("request_undo")
	await _await_frames(5)
	_save("04_editor_undo.png")
	print("[editor_flow] 4: undo applied")

	# 5) 返回主菜单(_on_editor_back_pressed → back_requested 信号 → main._show_view("menu"))
	editor_view.call("_on_editor_back_pressed")
	await _await_frames(5)
	var menu_node: Node = main_app.find_child("Menu", true, false)
	_save("05_back_to_menu.png")
	_diag_cc(main_app, "05 返回 menu")
	print("[editor_flow] 5: back to menu, menu.visible=%s editor.visible=%s" % [
		str(menu_node.visible) if menu_node else "?", str(editor_view.visible)])

	# 6) 重入编辑器(验证信号解耦后可重复打开)
	main_app.call("_on_editor_pressed")
	await get_tree().create_timer(0.8).timeout
	await _await_frames(5)
	_save("06_editor_reopen.png")
	print("[editor_flow] 6: editor reopened, visible=%s" % str(editor_view.visible))

	print("[editor_flow] done — 6 shots in %s" % _OUT_DIR)
	get_tree().quit(0)


func _save(name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("  WARN: %s viewport image null" % name)
		return
	img.save_png(_OUT_DIR + name)
	print("  saved: %s (%dx%d)" % [name, img.get_width(), img.get_height()])


func _diag_cc(main_app: Node, tag: String) -> void:
	var cc: Control = main_app.get_node_or_null("Menu/CenterContainer")
	var menu: Control = main_app.get_node_or_null("Menu")
	if cc == null:
		print("  [DIAG %s] CenterContainer NOT FOUND" % tag)
		return
	print("  [DIAG %s] Menu.size=%s | CC pos=%s size=%s gpos=%s anchors=(%s,%s,%s,%s)" % [
		tag, str(menu.size) if menu else "?",
		str(cc.position), str(cc.size), str(cc.global_position),
		cc.anchor_left, cc.anchor_top, cc.anchor_right, cc.anchor_bottom])
	print("  [DIAG %s] viewport.canvas_transform=%s" % [tag, str(get_viewport().canvas_transform)])
