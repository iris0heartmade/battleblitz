extends Node
## ui_review_screenshot.gd — 原创美术接入验收的确定性截图工具(本地 mock,无后端)。
## 依次截图:主线存档 / 章节详情 / 英雄页 / 装备页 / 战斗默认态 / 单位选中 /
## 行动菜单 / 对话框 / 暂停界面 / 战斗结算。输出到 res://.refactor_shots/。
## 用法:godot --resolution 1280x720 --path godot-client res://tools/ui_review_screenshot.tscn

const MAP_PATH := "res://../game/maps/balanced_2p_15.json"


func _ready() -> void:
	# 关键:Godot 4 启动时 --resolution 已被消费,OS.get_cmdline_args() 只返回剩余参数。
	# 直接读 get_viewport().size — 它已经被 --resolution 设置过了。
	var res: Vector2i = get_viewport().size
	if res.x <= 0 or res.y <= 0:
		res = Vector2i(1280, 720)
	OS.set_environment("BB_REVIEW_RES", "%dx%d" % [res.x, res.y])
	_review_size = res
	print("[ui-review] res=", res, " viewport=", get_viewport().size)
	await _frames(6)
	var main := get_node("Main")
	main._game_id = 1
	main._player_id = 1

	# ── 主线:存档/章节/英雄/装备 ─────────────────────────────
	main._show_view("mainline")
	var mainline_view: Node = main.get_node("MainlineView")
	var campaign: Node = mainline_view.get_node("CampaignPanel")
	var prepare: Node = mainline_view.get_node("PreparePanel")
	campaign.visible = true
	prepare.visible = false
	await _frames(4)

	# 1) 主线存档(空槽 + 已有档混合)— record 字段喂 PreviewColumn 多行内容
	var slots: Array[Dictionary] = [
		{
			"title": "钢铁起义", "summary": "第 1 章 · 继续当前主线进度",
			"chapter": "第 1 章 · 边境风云",
			"progress": "进度: 32% (3/9 战)",
			"heroes_line": "队伍英雄: 云 / 安娜 / 卢克",
			"enemy_preview": "敌人预览: 边境守军 ×4 + 骑士 ×2",
			"next_mission": "下一战: 攻占北隘口",
			"recommend": "推荐等级: Lv.3~5",
			"save_time": "保存: 2026-07-31 22:14",
			"intel": "章节：钢铁起义\n进度：第 1 章\n选择继续以进入战前整备。",
		},
		{},
		{
			"title": "测试章节 2：双场残血战", "summary": "第 2 章 · 继续当前主线进度",
			"chapter": "第 2 章 · 双场残血",
			"progress": "进度: 78% (7/9 战)",
			"heroes_line": "队伍英雄: 云 / 安娜 / 卢克 + 雇佣 2",
			"enemy_preview": "敌人预览: 暗影骑士团 ×6 + 弓手 ×3",
			"next_mission": "下一战: 决战堡垒",
			"recommend": "推荐等级: Lv.7~9",
			"save_time": "保存: 2026-07-31 23:02",
			"intel": "章节：测试章节 2\n进度：第 2 章\n选择继续以进入战前整备。",
		},
	]
	campaign.set_slots(slots)
	campaign.select_slot(0)
	await _frames(4)
	_save("mainline_slots.png")

	# 2) 章节详情(选中已有档 → 预览信息)
	campaign.select_slot(2)
	await _frames(4)
	_save("mainline_chapter_detail.png")

	# 3) 英雄页(战前整备英雄摘要)
	campaign.visible = false
	prepare.visible = true
	var heroes: Array[Dictionary] = [
		{"hero_id": "yun", "name": "云", "level": 3, "hp": "53", "equipment_summary": "橡木法杖"},
		{"hero_id": "anna", "name": "安娜", "level": 2, "hp": "47", "equipment_summary": "守卫圆盾"},
		{"hero_id": "luke", "name": "卢克", "level": 1, "hp": "55", "equipment_summary": "未装备"},
	]
	prepare.set_heroes(heroes)
	prepare.set_active_tab("heroes")
	prepare.set_mission("钢铁起义 · 战役情报", "当前战役：第 1/2 战\n胜利条件：击败敌军或夺取敌方据点。\n推荐：先确认英雄装备与可部署部队。\n奖励：完成战斗后获得金币与成长经验。\n可部署部队：4")
	prepare.show_content("云 · 术士", "等级 3 · 经验 45\n生命 53  攻击 20  防御 11\n速度 14  魔攻 29  魔防 13\n技能：奥术爆裂")
	prepare.set_choices("", [])
	await _frames(4)
	_save("mainline_heroes.png")

	# 4) 装备页(装备清单 + 物品/数值预览)
	prepare.set_active_tab("equipment")
	prepare.set_choices("equipment", ["橡木法杖 · 2 件", "守卫圆盾 · 1 件", "红宝石戒指 · 1 件"], 0,
		"选择仓库物品，再使用「整备操作」确认装备。")
	prepare.show_content("装备整备 · 云", "当前武器：橡木法杖\n当前防具：守卫圆盾\n当前饰品：红宝石戒指\n\n仓库选中：橡木法杖（2 件）\n选择装备后可使用旧整备操作确认。")
	await _frames(4)
	_save("mainline_equipment.png")

	# ── 战斗 HUD ─────────────────────────────────────────────
	main._show_view("game")
	var hero := {
		"id": 901, "hero_id": "yun", "name": "云", "unit_type": "warlock",
		"level": 1, "hp": 53, "max_hp": 53, "mp": 4, "max_mp": 8,
		"mov": 4, "atk": 20, "def_": 11, "matk": 29, "mdef": 13,
		"attack_range": 2, "min_attack_range": 0, "morale": 2,
		"x": 2, "y": 8, "player_id": 1, "color": "red",
		"skills": ["arcane_blast"], "has_acted": false, "has_moved": false,
	}
	if not FileAccess.file_exists(MAP_PATH):
		printerr("[ui-review] map not found: %s" % MAP_PATH)
		get_tree().quit(1)
		return
	var map_data: Variant = JSON.parse_string(FileAccess.open(MAP_PATH, FileAccess.READ).get_as_text())
	if not (map_data is Dictionary):
		printerr("[ui-review] invalid map json")
		get_tree().quit(1)
		return
	main.board.load_map(map_data)
	var red_units: Array = [hero]
	var blue_units: Array = []
	var next_id := 902
	for placed_v in map_data.get("initial_units", []):
		var placed: Dictionary = placed_v
		if int(placed.get("x", -1)) == 2 and int(placed.get("y", -1)) == 8 and str(placed.get("color", "")) == "red":
			continue
		red_units.append({
			"id": next_id, "name": str(placed.get("type", "unit")),
			"unit_type": str(placed.get("type", "swordsman")),
			"level": 1, "hp": 45, "max_hp": 45, "mp": 5, "max_mp": 5, "mov": 5,
			"atk": 12, "def_": 8, "matk": 4, "mdef": 5, "attack_range": 1,
			"min_attack_range": 0, "morale": 0, "x": int(placed.get("x", 0)),
			"y": int(placed.get("y", 0)),
			"player_id": 1 if str(placed.get("color", "red")) == "red" else 2,
			"color": str(placed.get("color", "red")), "skills": [],
			"has_acted": false, "has_moved": false,
		})
		next_id += 1
	for placed_v in map_data.get("initial_units", []):
		var placed2: Dictionary = placed_v
		if str(placed2.get("color", "red")) != "blue":
			continue
		blue_units.append({
			"id": next_id, "name": str(placed2.get("type", "unit")),
			"unit_type": str(placed2.get("type", "swordsman")),
			"level": 1, "hp": 45, "max_hp": 45, "mp": 5, "max_mp": 5, "mov": 5,
			"atk": 12, "def_": 8, "matk": 4, "mdef": 5, "attack_range": 1,
			"min_attack_range": 0, "morale": 0, "x": int(placed2.get("x", 0)),
			"y": int(placed2.get("y", 0)), "player_id": 2, "color": "blue",
			"skills": [], "has_acted": false, "has_moved": false,
		})
		next_id += 1
	GameState.players = [
		{"id": 1, "color": "red", "user_name": "云", "gold": 1000, "units": red_units},
		{"id": 2, "color": "blue", "user_name": "边境守军", "gold": 800, "units": blue_units},
	]
	GameState.current_player_id = 1
	GameState.local_player_id = 1
	GameState.co_states = [
		{"player_id": 1, "color": "red", "commander_id": "yun", "meter": 8, "threshold": 20},
		{"player_id": 2, "color": "blue", "commander_id": null, "meter": 0, "threshold": 20},
	]
	main._refresh_co_roster()
	main._refresh_commander_section()
	main.turn_badge_label.text = "回合 1"
	main.phase_badge_label.text = "● 我方阶段"
	main.current_player_label.text = "→ 云"
	main.gold_label.text = "金币 1000"
	main.end_turn_button.disabled = false
	# 显式触发一次响应式断点,让窗口宽度(由 --resolution 覆盖)被正确读取。
	main.call("_update_hud_layout_for_viewport")
	await _frames(8)

	# 5) 战斗默认态(无选中)
	_save("battle_default.png")

	# 6) 单位选中(InfoPanel 显示指挥官 + 单位详情)
	main._handle_unit_click(901, Vector2.ZERO)
	await _frames(4)
	main._hide_action_bubble()
	await _frames(2)
	_save("battle_unit_selected.png")

	# 7) 行动菜单(ActionBubble 弹出 5 按钮)
	main._handle_unit_click(901, Vector2.ZERO)
	await _frames(4)
	_save("battle_action_menu.png")

	# 8) 对话框(DialogManager 全屏阻断遮罩)
	main._hide_action_bubble()
	DialogManager.show_dialog({
		"speaker": "云", "text": "「这片土地饱受战火蹂躏,我们必须夺回城堡!」",
	})
	await _frames(6)
	_save("battle_dialogue.png")
	DialogManager.hide_dialog()
	await _frames(2)

	# 9) 暂停界面(全屏半透遮罩 + 中央面板)
	main.get_node("GameView/HUD/PauseOverlay").visible = true
	main.get_node("GameView/HUD/PausePanel").visible = true
	await _frames(4)
	_save("battle_pause.png")
	main.get_node("GameView/HUD/PauseOverlay").visible = false
	main.get_node("GameView/HUD/PausePanel").visible = false
	await _frames(2)

	# 10) 战斗结算(章节结果标题板 + 胜利统计)— 走真实路径 show_battle_result,
	# 否则遮罩不会触发,评审看到的是裸 panel 而不是压暗棋盘。
	main.call("show_battle_result", "云", "red", {
		"kills": 4, "deaths": 1, "captures": 1, "co_peak": 18, "turns": 6, "skills": 2,
		"reason": "占领敌方据点", "detail_lines": ["云 击杀了 敌方骑士", "云 占领了 城堡"],
	})
	await _frames(6)
	_save("battle_result.png")
	main.call("hide_battle_result")

	print("[ui-review] done")
	get_tree().quit(0)


var _review_size: Vector2i = Vector2i(1280, 720)


func _save(name: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		print("  WARN: %s viewport image null" % name)
		return
	# 输出 dir 用 _review_size(从 BB_REVIEW_RES / --resolution 解析)而非 image 实际像素:
	# Godot 4 canvas_items stretch 下 headless 不会缩放到 --resolution,image 永远是 1920,
	# 但用户期望按"启动分辨率"分组文件。
	var size_str := "%dx%d" % [_review_size.x, _review_size.y]
	var dir := "res://.refactor_shots/ui_%s/" % size_str
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var err := img.save_png(dir + name)
	print("  saved: %s (%s) err=%d" % [name, size_str, err])


func _frames(count: int) -> void:
	for _i in count:
		await get_tree().process_frame
		RenderingServer.force_draw()
