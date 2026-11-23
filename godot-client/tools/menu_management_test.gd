extends Node

func _ready() -> void:
	var main = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await get_tree().process_frame
	await get_tree().process_frame
	main._show_settings_panel()
	var panel: Control = main.settings_panel
	var rows := panel.get_node("SettingsList")
	assert(panel.size.x >= 1020, "分类设置必须容纳右侧内容")
	assert(rows.get_node("NameRow").visible)
	var nav := panel.get_node("CategoryNav")
	nav.get_child(1).pressed.emit()
	assert(not rows.get_node("NameRow").visible)
	assert(rows.get_node("FontRow").visible and rows.get_node("ThemeRow").visible)
	nav.get_child(2).pressed.emit()
	assert(rows.get_node("AudioRow").visible and not rows.get_node("FontRow").visible)
	nav.get_child(0).pressed.emit()
	assert(rows.get_node("ColorRow").visible)
	assert(rows.get_node("ButtonRow/CancelBtn").visible)
	rows.get_node("ButtonRow/CancelBtn").pressed.emit()
	assert(not panel.visible, "取消保持原关闭行为")
	print("MENU_MANAGEMENT PASS: categories, geometry, cancel")
	get_tree().quit(0)
