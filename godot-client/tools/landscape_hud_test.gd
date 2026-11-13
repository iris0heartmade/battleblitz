extends Node

func _ready() -> void:
	get_tree().create_timer(20.0).timeout.connect(func(): get_tree().quit(1))
	var main = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await get_tree().process_frame
	await get_tree().process_frame
	var hud = main.landscape_hud
	assert(hud != null, "正式主界面必须创建底栏")
	assert(hud.mouse_filter == Control.MOUSE_FILTER_STOP, "底栏必须阻挡点击穿透")
	hud.set_process(false)
	main._show_view("game")
	await get_tree().process_frame
	await get_tree().process_frame
	hud._process(0.0)
	assert(not main.left_hud_wing.visible and not main.info_panel.visible, "默认不得显示旧左右巨框")
	assert(main.board.board_camera.bottom_inset == hud.HEIGHT, "相机必须保留底栏安全区")
	assert(main.board.board_camera.left_inset == 24.0, "相机不得继续预留旧左栏")
	hud.drawer = true
	hud._process(0.0)
	assert(main.info_panel.visible, "详情入口必须可展开")
	hud.drawer = false
	hud._process(0.0)
	var captured: Array = []
	hud.gui_input.connect(func(event): captured.append(event))
	var point: Vector2 = hud.global_position + Vector2(400, 140)
	var click := InputEventMouseButton.new()
	click.position = point
	click.global_position = point
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	get_viewport().push_input(click, true)
	await get_tree().process_frame
	assert(not captured.is_empty(), "文字区域点击必须由底栏接收")
	assert(main.board.controls.pointer == 0, "底栏点击不得开始棋盘拖动/选取")
	click.pressed = false
	get_viewport().push_input(click, true)
	for child in hud.get_children():
		if child is Button:
			child.pressed.emit()
			assert(hud.drawer, "底栏阻挡不得阻止详情按钮")
			hud.drawer = false

	assert(hud._art_kind("gate") == "settlement")
	assert(hud._art_kind("snow_peak") == "rocky")
	assert(hud._art_kind("unknown") == "grassland")
	var unit := {"id": 1, "unit_type": "infantry", "hp": 17, "max_hp": 20, "mp": 2.5, "mov": 5, "atk": 10, "def_": 6, "matk": 0, "mdef": 2, "min_attack_range": 0, "attack_range": 1}
	GameState.players = [{"id": 1, "units": [unit]}]
	main._selected_unit_id = 1
	main._move_mode_unit_id = 1
	main._hide_action_bubble()
	assert(hud._active_unit_id() == 1, "气泡关闭后移动模式必须保持单位")
	main._move_mode_unit_id = -1
	main._attack_mode_unit_id = 1
	assert(hud._active_unit_id() == 1, "攻击模式必须保持攻击者")
	main._attack_mode_unit_id = -1
	main._skill_mode_unit_id = 1
	assert(hud._active_unit_id() == 1, "技能模式必须保持施放者")
	main._on_board_tile_clicked(Vector2i(-1,-1))
	assert(hud._active_unit_id() == -1, "无关格取消后不能显示旧单位")
	main._pending_attack_attacker_id = 1
	main.attack_confirm_panel.visible = true
	assert(hud._active_unit_id() == 1, "确认预测必须保持攻击者")
	main._hide_attack_confirm()
	assert(hud._active_unit_id() == -1)
	hud.show_forecast({"damage":12,"target_hp_after":33,"counter_damage":5,"attacker_hp_after":40,"target_def_bonus":0,"height_delta":1,"height_attack_bonus":1,"range_bonus":0}, unit, unit)
	hud.show_state(unit, {"terrain":"forest"}, Vector2i.ONE, false, hud.compact_forecast, true)
	await get_tree().process_frame
	assert(hud.prediction.get_content_height() <= hud.prediction.size.y, "四行预测必须完整可读")
	assert(not main.attack_confirm_panel.get_node("Body").visible, "禁止重复中央预测正文")
	hud.compact_forecast = ""

	hud.show_state(unit, {"terrain": "plain", "defense_bonus": 1, "movement_cost_x2": 2}, Vector2i.ZERO, false, "", false)
	assert(hud.vitality.text.contains("2.5"), "半点移动力不可截断")
	assert(hud.ground.text.contains("地形防御 1"), "地形防御需独立显示")
	assert(not hud.ground.text.contains("高地攻击"), "无目标不能常驻高差攻击收益")
	hud.show_state(unit, {"terrain": "forest"}, Vector2i.ONE, true, "正在计算战斗预测...", true)
	assert(hud.prediction.visible and not hud.stats.visible, "预测须替换普通属性")
	assert(hud.prediction.text.contains("正在计算"), "加载阶段不得保留旧预测")
	hud.show_state(unit, {"terrain": "plain"}, Vector2i.ZERO, false, "", false)
	assert(not hud.prediction.visible and hud.stats.visible, "取消后恢复单位属性")
	hud.show_state({}, {}, Vector2i(-1,-1), false, "", false)
	assert(not hud.health.visible and not hud.portrait.visible, "清理后不能保留HP与头像")
	assert(hud.ground.text.contains("—"), "未知数值不可伪造")
	print("LANDSCAPE_HUD PASS: main integration, half movement, terrain defense, loading, cancel, clear, unknown")
	main.queue_free()
	await get_tree().process_frame
	get_tree().quit()
