extends Node
## saves_flow_screenshot.gd — P2 重构验证:存档视图进出页面截图。
## 加载 main.tscn,模拟「主菜单 → 进存档页 → 等 list_saves 响应 → 返回菜单 → 重入」,
## 每步截图 + 打印关键几何信息,验证 saves_controller.gd 组件抽离后:
##   1) SavesView 渲染正常(list_saves 后状态正确)
##   2) 返回菜单无右偏(复用上次 camera 修复)
##   3) 组件可重复打开
## Prereq: 后端 127.0.0.1:8000 listening(open() 会拉取存档列表;
##         若无后端,list_saves 异步返回空 body → UI 走空态分支,仍可截图)。

const _OUT_DIR := "res://.refactor_shots/"


func _await_frames(n: int) -> void:
	# Headless 下 RenderingServer.frame_post_draw 不触发,用 process_frame 替代
	for i in n:
		await get_tree().process_frame


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(_OUT_DIR)
	await _await_frames(6)
	var main_app: Node = get_tree().current_scene
	if main_app != null and main_app.name == "SavesFlowScreenshot" and main_app.get_child_count() > 0:
		main_app = main_app.get_child(0)
	await _await_frames(3)

	# 1) 主菜单
	_save("01_saves_menu.png")
	_diag_cc(main_app, "01 首次 menu")
	print("[saves_flow] 1: main menu")

	# 2) 进入存档页(main._on_saves_pressed → _show_view + saves_view.open())
	main_app.call("_on_saves_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var saves_view: Node = main_app.find_child("SavesView", true, false)
	if saves_view == null:
		printerr("[saves_flow] SavesView not found"); get_tree().quit(1); return
	# P2:验证组件 _main 注入存在
	if not saves_view.has_method("_refresh_saves"):
		printerr("[saves_flow] saves_view missing _refresh_saves (component not wired)"); get_tree().quit(1); return
	_save("02_saves_open.png")
	print("[saves_flow] 2: saves opened, visible=%s _main=%s" % [str(saves_view.visible), str(saves_view._main.name if saves_view._main else "null")])

	# 3) 等 list_saves 响应(saves_view._refresh_saves 调 NetworkClient.list_saves)
	await get_tree().create_timer(1.5).timeout
	await _await_frames(5)
	var save_status: Label = saves_view.get_node_or_null("SaveFrame/SaveStatus")
	var save_open_list: RichTextLabel = saves_view.get_node_or_null("SaveFrame/SaveOpenList")
	var save_ml_list: RichTextLabel = saves_view.get_node_or_null("SaveFrame/SaveMainlineList")
	var save_select: OptionButton = saves_view.get_node_or_null("SaveFrame/SaveSelectOption")
	_save("03_saves_loaded.png")
	print("[saves_flow] 3: after list_saves, status=%s open_rows=%d ml_rows=%d select_items=%d _save_records=%d" % [
		str(save_status.text) if save_status else "?",
		save_open_list.text.split("\n").size() if save_open_list else 0,
		save_ml_list.text.split("\n").size() if save_ml_list else 0,
		save_select.item_count if save_select else 0,
		(len(saves_view._save_records) if saves_view else 0)
	])

	# 4) 返回主菜单(组件 _on_save_back_pressed → _main._show_view("menu"))
	saves_view.call("_on_save_back_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var menu_node: Node = main_app.find_child("Menu", true, false)
	_save("04_saves_back.png")
	_diag_cc(main_app, "04 返回 menu")
	print("[saves_flow] 4: back to menu, menu.visible=%s saves_view.visible=%s" % [
		str(menu_node.visible) if menu_node else "?",
		str(saves_view.visible)
	])

	# 5) 重入存档页(验证组件可重复打开 + _main 注入持久)
	main_app.call("_on_saves_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	_save("05_saves_reopen.png")
	print("[saves_flow] 5: saves reopened, visible=%s" % str(saves_view.visible))

	print("[saves_flow] done — 5 shots in %s" % _OUT_DIR)
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