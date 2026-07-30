extends Node
## saves_flow_screenshot.gd — P2 + #16 重构验证:存档视图进出页面截图。
## 加载 main.tscn,模拟「主菜单 → 进存档页 → 等 list_saves 响应 → 返回菜单 → 重入」,
## 每步截图 + 打印关键几何信息,验证 saves_controller.gd 组件抽离后:
##   1) SavesView 渲染正常(3 槽卡片 + 自动 + 中断)
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
	NetworkClient.api_error.connect(func(method: String, path: String, error: String, code: int):
		print("[saves_flow] API_ERROR %s %s code=%d error=%s" % [method, path, code, error])
	)
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

	# 3) 等 list_saves 响应 → 验证 3 槽卡片渲染
	await get_tree().create_timer(1.5).timeout
	await _await_frames(5)
	var save_status: Label = saves_view.get_node_or_null("SaveFrame/SaveStatus")
	var save_slots_container: VBoxContainer = saves_view.get_node_or_null("SaveFrame/SaveSlotsContainer")
	var save_auto_row: PanelContainer = saves_view.get_node_or_null("SaveFrame/SaveAutoRow")
	var save_suspend_row: PanelContainer = saves_view.get_node_or_null("SaveFrame/SaveSuspendRow")
	# Verify the live backend response before the richer mock data below replaces
	# it. This catches the exact regression where the screen stayed loading.
	if save_status == null or save_status.text != "三存档槽":
		printerr("[saves_flow] live /saves response did not complete: %s" % (save_status.text if save_status else "missing status"))
		get_tree().quit(1)
		return
	if save_slots_container == null or save_slots_container.get_child_count() != 3:
		printerr("[saves_flow] live /saves did not render three manual slots")
		get_tree().quit(1)
		return
	print("[saves_flow] live backend response rendered 3 manual slots")
	# 注入 mock 数据(模拟后端响应,确保 3 槽 + auto + suspend 都能渲染)
	saves_view.call("_on_saves_response", {
		"manual_slots": [
			{"id": 1, "kind": "manual", "slot_index": 0, "label": "第 3 章 - 手动", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 2},
			{"id": 2, "kind": "manual", "slot_index": 2, "label": "自由战 #42 - 手动", "mainline_id": "", "chapter_index": 0},
		],
		"auto_slot": {"id": 50, "kind": "auto", "slot_index": 0, "label": "chapter_01_steel_rebellion-结束", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 3},
		"suspend": {"user_name": "Player", "game_id": 77, "mainline_id": "chapter_01_steel_rebellion", "battle_id": "battle_02", "suspend_point": "manual"},
	}, 200)
	await get_tree().create_timer(0.2).timeout
	await _await_frames(3)
	_save("03_saves_loaded.png")
	# #16 验证:3 槽 + auto + suspend 渲染
	var manual_rows: int = save_slots_container.get_child_count() if save_slots_container else 0
	var auto_children: int = save_auto_row.get_child_count() if save_auto_row else 0
	var suspend_children: int = save_suspend_row.get_child_count() if save_suspend_row else 0
	print("[saves_flow] 3: after list_saves (mock), status=%s manual_rows=%d auto_children=%d suspend_children=%d filled=%d" % [
		str(save_status.text) if save_status else "?",
		manual_rows,
		auto_children,
		suspend_children,
		(int(saves_view._manual_slot_records[0] != {})) + (int(saves_view._manual_slot_records[1] != {})) + (int(saves_view._manual_slot_records[2] != {})),
	])
	# 验证每槽内容
	if save_slots_container:
		for i in range(min(3, save_slots_container.get_child_count())):
			var row: PanelContainer = save_slots_container.get_child(i)
			var row_text := ""
			for child in row.get_children():
				if child is HBoxContainer:
					for grandchild in child.get_children():
						if grandchild is RichTextLabel:
							row_text = grandchild.text
							break
			print("  slot %d text=%s" % [i + 1, row_text.replace("\n", " | ")])

	# 4) 返回主菜单
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
