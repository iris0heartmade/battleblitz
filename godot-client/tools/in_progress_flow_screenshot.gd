extends Node
## in_progress_flow_screenshot.gd — #16 in_progress 视图截图验证。
## 加载 main.tscn,模拟「主菜单 → 进 in_progress 视图 → mock 拉 /saves + /games →
## 渲染 → 返回菜单 → 重入」,验证 in_progress_controller.gd 组件:
##   1) InProgressView 渲染正常(空态 / 有数据 两态)
##   2) 组件可重复打开 + _main 注入持久
##   3) 返回菜单无右偏(复用 camera 修复)
## Prereq: 后端 127.0.0.1:8000 listening(open() 拉 2 路 API);
##         若无后端,2 路异步返回空 body → UI 走空态分支,仍可截图。

const _OUT_DIR := "res://.refactor_shots/"


func _await_frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(_OUT_DIR)
	await _await_frames(6)
	var main_app: Node = get_tree().current_scene
	if main_app != null and main_app.name == "InProgressFlowScreenshot" and main_app.get_child_count() > 0:
		main_app = main_app.get_child(0)
	await _await_frames(3)

	# 1) 主菜单
	_save("01_ip_menu.png")
	_diag_cc(main_app, "01 首次 menu")
	print("[ip_flow] 1: main menu")

	# 2) 进入 in_progress 视图
	main_app.call("_on_in_progress_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var ip_view: Node = main_app.find_child("InProgressView", true, false)
	if ip_view == null:
		printerr("[ip_flow] InProgressView not found"); get_tree().quit(1); return
	if not ip_view.has_method("open"):
		printerr("[ip_flow] InProgressView missing open() (component not wired)"); get_tree().quit(1); return
	_save("02_ip_empty.png")
	print("[ip_flow] 2: in_progress opened, visible=%s _main=%s" % [
		str(ip_view.visible), str(ip_view._main.name if ip_view._main else "null")
	])

	# 3) 注入 mock 数据(模拟后端响应:1 suspend + 2 games + 2 mainline saves)
	ip_view.call("_on_saves_response", {
		"manual_slots": [
			{"id": 1, "kind": "manual", "slot_index": 0, "label": "第 3 章 - 手动", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 2},
			{"id": 2, "kind": "manual", "slot_index": 2, "label": "第 1 章 - 手动", "mainline_id": "chapter_02_eirika", "chapter_index": 0},
		],
		"auto_slot": {"id": 50, "kind": "auto", "slot_index": 0, "label": "chapter_01_steel_rebellion-结束", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 3},
		"suspend": {"user_name": "Player", "game_id": 77, "mainline_id": "chapter_01_steel_rebellion", "battle_id": "battle_02", "suspend_point": "manual"},
	}, 200)
	ip_view.call("_on_games_response", [
		{"id": 100, "status": "playing", "name": "mainline:chapter_01_steel_rebellion:battle_01"},
		{"id": 88, "status": "playing", "name": "Free Battle"},
		{"id": 99, "status": "waiting", "name": "test_lobby"},
	], 200)
	await get_tree().create_timer(0.2).timeout
	await _await_frames(3)
	_save("03_ip_loaded.png")
	var ip_list: VBoxContainer = ip_view.get_node_or_null("IPFrame/IPScroll/IPList")
	var status_lbl: Label = ip_view.get_node_or_null("IPFrame/IPStatus")
	print("[ip_flow] 3: after mock data, status=%s list_children=%d suspend=%s games=%d mainline_saves=%d" % [
		str(status_lbl.text) if status_lbl else "?",
		ip_list.get_child_count() if ip_list else 0,
		not ip_view._suspend_record.is_empty(),
		ip_view._active_games.size(),
		ip_view._mainline_save_records.size(),
	])

	# 4) 返回主菜单
	ip_view.call("_on_back_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	var menu_node: Node = main_app.find_child("Menu", true, false)
	_save("04_ip_back.png")
	_diag_cc(main_app, "04 返回 menu")
	print("[ip_flow] 4: back to menu, menu.visible=%s ip_view.visible=%s" % [
		str(menu_node.visible) if menu_node else "?",
		str(ip_view.visible)
	])

	# 5) 重入 in_progress
	main_app.call("_on_in_progress_pressed")
	await get_tree().create_timer(0.3).timeout
	await _await_frames(5)
	_save("05_ip_reopen.png")
	print("[ip_flow] 5: in_progress reopened, visible=%s" % str(ip_view.visible))

	print("[ip_flow] done — 5 shots in %s" % _OUT_DIR)
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
