extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var panel = load("res://scenes/ui/mainline_prepare_panel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	var received: Array = []
	panel.choice_requested.connect(func(kind, index): received.append([kind, index]))
	panel.set_active_tab("equipment")
	panel.set_choices("equipment", ["物品甲", "物品乙"], 0)
	var list = panel.get_node("%ChoiceList")
	list.item_selected.emit(1)
	assert(panel.get_node("%ChoiceSelect").selected == 1)
	assert(received == [["equipment", 1]])
	panel.get_node("%MissionToggle").pressed.emit()
	assert(panel.get_node("%MissionPanel").visible)
	panel.get_node("%MissionToggle").pressed.emit()
	assert(not panel.get_node("%MissionPanel").visible)
	panel.set_choices("shop", [])
	assert(not list.visible)
	var archive = load("res://scenes/ui/mainline_campaign_panel.tscn").instantiate()
	root.add_child(archive)
	await process_frame
	var records: Array[Dictionary] = [{"title":"测试旅程", "progress":"32%", "heroes_line":"云 / 安娜"}, {}]
	archive.set_slots(records)
	archive.select_slot(1)
	assert(archive.get_node("%PrimaryAction").text.contains("新战役"))
	archive.select_slot(0)
	assert(archive.get_node("%PreviewTitle").text == "测试旅程")
	var main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	var settings = main.get_node("GameView/HUD/SettingsPanel")
	var navigation = settings.get_node("CategoryNav")
	navigation.get_child(1).pressed.emit()
	assert(settings.get_node("SettingsList/FontRow").visible)
	assert(not settings.get_node("SettingsList/NameRow").visible)
	navigation.get_child(2).pressed.emit()
	assert(settings.get_node("SettingsList/AudioRow").visible)
	assert(not settings.get_node("SettingsList/FontRow").visible)
	print("MENU_REDESIGN PASS: settings categories, choice signal, selection, empty list, mission toggle, archive selection")
	quit(0)
