extends Node
## mainline_flow_screenshot.gd — P2 重构验证:主线视图进出 + 组件行为截图。
## 加载 main.tscn,模拟「主菜单 → 进主线 → 等 list_mainlines/saves/commanders →
## 等 commander 状态就绪 → 返回菜单 → 重入」,每步截图 + 打印关键状态,
## 验证 mainline_controller.gd 组件抽离后(Batch A):
##   1) MainlineView 渲染正常(章节列表 + 存档格 + 指挥官 选项)
##   2) 返回菜单无右偏(复用上次 camera 修复)
##   3) 组件可重复打开 + _main 注入持久
## Prereq: 后端 127.0.0.1:8000 listening(open() 拉取 3 路 API);
##         若无后端,3 路异步返回空 body → UI 走空态分支,仍可截图。

const _OUT_DIR := "res://.refactor_shots/"


func _await_frames(n: int) -> void:
	# Headless 下 RenderingServer.frame_post_draw 不触发,用 process_frame 替代
	for i in n:
		await get_tree().process_frame


func _ready() -> void:
	NetworkClient.api_error.connect(func(method: String, path: String, error: String, code: int):
		print("[mainline_flow] API_ERROR %s %s code=%d error=%s" % [method, path, code, error])
	)
	DirAccess.make_dir_recursive_absolute(_OUT_DIR)
	await _await_frames(6)
	var main_app: Node = get_tree().current_scene
	if main_app != null and main_app.name == "MainlineFlowScreenshot" and main_app.get_child_count() > 0:
		main_app = main_app.get_child(0)
	await _await_frames(3)

	# 1) 主菜单
	_save("01_ml_menu.png")
	_diag_cc(main_app, "01 首次 menu")
	print("[mainline_flow] 1: main menu")

	# 2) 进入主线页(main._on_mainline_pressed → mainline_view.open())
	main_app.call("_on_mainline_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var mainline_view: Node = main_app.find_child("MainlineView", true, false)
	if mainline_view == null:
		printerr("[mainline_flow] MainlineView not found"); get_tree().quit(1); return
	if not mainline_view.has_method("open"):
		printerr("[mainline_flow] mainline_view missing open() (component not wired)"); get_tree().quit(1); return
	_save("02_ml_open.png")
	print("[mainline_flow] 2: mainline opened, visible=%s _main=%s" % [
		str(mainline_view.visible),
		str(mainline_view._main.name if mainline_view._main else "null")
	])

	# 3) 等 3 路 list_* 异步响应
	await get_tree().create_timer(1.5).timeout
	await _await_frames(5)
	var ml_title: Label = mainline_view.get_node_or_null("MLFrame/MLTitle")
	var ml_list_container: VBoxContainer = mainline_view.get_node_or_null("MLFrame/MLListContainer")
	var ml_commander_status: Label = mainline_view.get_node_or_null("MLFrame/CommanderStatus")
	if ml_title == null or ml_title.text != "主线存档":
		printerr("[mainline_flow] live /saves response did not complete: %s" % (ml_title.text if ml_title else "missing title"))
		get_tree().quit(1)
		return
	if ml_list_container == null or ml_list_container.get_child_count() != 3:
		printerr("[mainline_flow] live mainline entry did not render three slots")
		get_tree().quit(1)
		return
	if ml_commander_status != null and ml_commander_status.is_visible_in_tree():
		printerr("[mainline_flow] commander controls must stay hidden on save-slot entry")
		get_tree().quit(1)
		return
	_save("03_ml_loaded.png")
	# #16 — MLSlotsContainer 删了(三槽 UI 合并到 saves_view);null 防御
	print("[mainline_flow] 3: after list_*, title=%s ml_list_children=%d commander_status=%s" % [
		str(ml_title.text) if ml_title else "?",
		ml_list_container.get_child_count() if ml_list_container else 0,
		str(ml_commander_status.text) if ml_commander_status else "?",
	])

	# 4) 返回主菜单(目前 batch B 的 _on_ml_back_pressed 还在 main.gd — thin wrapper)
	# 因为 batch A 没搬 ml_back_btn 的 connects,我们用 _show_view("menu") 模拟
	main_app.call("_show_view", "menu")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var menu_node: Node = main_app.find_child("Menu", true, false)
	_save("04_ml_back.png")
	_diag_cc(main_app, "04 返回 menu")
	print("[mainline_flow] 4: back to menu, menu.visible=%s mainline_view.visible=%s" % [
		str(menu_node.visible) if menu_node else "?",
		str(mainline_view.visible)
	])

	# 5) 重入主线页(验证组件可重复打开 + _main 注入持久)
	main_app.call("_on_mainline_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	_save("05_ml_reopen.png")
	print("[mainline_flow] 5: mainline reopened, visible=%s" % str(mainline_view.visible))

	print("[mainline_flow] done — 5 shots in %s" % _OUT_DIR)
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
