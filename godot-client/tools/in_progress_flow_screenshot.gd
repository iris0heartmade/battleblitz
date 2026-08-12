extends Node
## in_progress_flow_screenshot.gd — capture the in-progress submenu flow.
## The script is intentionally self-contained and has a watchdog so screenshot
## checks fail with an exit code instead of leaving a hidden Godot process alive.

const _OUT_DIR := "res://.refactor_shots/"
const _WATCHDOG_SEC := 20.0


func _ready() -> void:
	var watchdog := get_tree().create_timer(_WATCHDOG_SEC)
	watchdog.timeout.connect(func() -> void:
		printerr("[ip_flow] watchdog timeout after %.1fs" % _WATCHDOG_SEC)
		get_tree().quit(2)
	)

	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_OUT_DIR))
	await _settle(8)

	var main_app := _main_scene()
	if main_app == null:
		printerr("[ip_flow] Main scene not found")
		get_tree().quit(1)
		return

	_save("01_ip_menu.png")
	_diag_cc(main_app, "01 menu")
	print("[ip_flow] 1: main menu")

	main_app.call("_on_in_progress_pressed")
	await _settle(8)

	var ip_view: Node = main_app.get_node_or_null("InProgressView")
	if ip_view == null:
		printerr("[ip_flow] InProgressView not found")
		get_tree().quit(1)
		return
	if not ip_view.has_method("open"):
		printerr("[ip_flow] InProgressView missing open()")
		get_tree().quit(1)
		return

	_save("02_ip_empty.png")
	print("[ip_flow] 2: in_progress opened, visible=%s" % str(ip_view.visible))

	ip_view.call("_on_saves_response", {
		"manual_slots": [
			{"id": 1, "kind": "manual", "slot_index": 0, "label": "第 3 章 - 手动", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 2},
			{"id": 2, "kind": "manual", "slot_index": 2, "label": "第 1 章 - 手动", "mainline_id": "chapter_02_eirika", "chapter_index": 0},
		],
		"auto_slot": {"id": 50, "kind": "auto", "slot_index": 0, "label": "chapter_01_steel_rebellion-结束", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 3},
		"suspend": {"user_name": "Player", "game_id": 77, "mainline_id": "chapter_01_steel_rebellion", "battle_id": "battle_02", "suspend_point": "manual"},
	}, 200)
	await _settle(6)

	_save("03_ip_loaded.png")
	var ip_list: VBoxContainer = ip_view.get_node_or_null("IPFrame/IPScroll/IPList")
	var status_lbl: Label = ip_view.get_node_or_null("IPFrame/IPStatus")
	print("[ip_flow] 3: after mock data, status=%s list_children=%d" % [
		str(status_lbl.text) if status_lbl else "?",
		ip_list.get_child_count() if ip_list else 0,
	])

	ip_view.call("_on_back_pressed")
	await _settle(8)
	_save("04_ip_back.png")
	_diag_cc(main_app, "04 back menu")
	print("[ip_flow] 4: back to menu, ip_view.visible=%s" % str(ip_view.visible))

	main_app.call("_on_in_progress_pressed")
	await _settle(8)
	_save("05_ip_reopen.png")
	print("[ip_flow] 5: in_progress reopened, visible=%s" % str(ip_view.visible))

	print("[ip_flow] done — 5 shots in %s" % _OUT_DIR)
	get_tree().quit(0)


func _main_scene() -> Node:
	var current := get_tree().current_scene
	if current == null:
		return null
	if current.name == "Main":
		return current
	var child := current.get_node_or_null("Main")
	if child != null:
		return child
	var packed: PackedScene = load("res://scenes/main.tscn")
	if packed == null:
		return null
	var main := packed.instantiate()
	add_child(main)
	return main


func _settle(frames: int) -> void:
	for i in frames:
		await get_tree().process_frame
	await get_tree().create_timer(0.1).timeout


func _save(name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("[ip_flow] WARN: %s viewport image null" % name)
		return
	img.save_png(_OUT_DIR + name)
	print("  saved: %s (%dx%d)" % [name, img.get_width(), img.get_height()])


func _diag_cc(main_app: Node, tag: String) -> void:
	var cc: Control = main_app.get_node_or_null("Menu/CenterContainer")
	var menu: Control = main_app.get_node_or_null("Menu")
	if cc == null:
		print("  [DIAG %s] CenterContainer NOT FOUND" % tag)
		return
	print("  [DIAG %s] Menu.size=%s | CC pos=%s size=%s gpos=%s" % [
		tag,
		str(menu.size) if menu else "?",
		str(cc.position),
		str(cc.size),
		str(cc.global_position),
	])
