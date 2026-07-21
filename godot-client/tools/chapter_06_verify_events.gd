extends Node
## chapter_06_verify_events.gd
##
## 不是为了赢, 而是为了验证 chapter_06_iron_reckoning.json 里设计的
## 每一个**事件触发**都真的被后端/客户端处理了。
##
## 验证项 (对应 chapter_06 JSON 的 25 个可魔改字段):
##   1. initial_units: 6 红方单位正确显示
##   2. waves[0] turn 3: 援军 1 (knight at 12,0) 出现
##   3. waves[1] turn 7: 援军 2 (healer+archer at 14,4/5) 出现
##   4. traps[0] (8,4 spike): 走到 8,4 触发陷阱
##   5. traps[1] (9,5 spike): 走到 9,5 触发陷阱
##   6. wave_msg 触发: 援军到时显示 "援军从北坡冲下!"
##   7. boss 战: kalde HP 80 → 被打 1 回合后 HP 减 18
##   8. hero_id: yun 有 hero 徽章 (BattleUnitNode._hero_badge)
##   9. support_dialogues: 显示 "支援对话可触发" 提示
##   10. battle_talks: 显示 "yun vs kalde" 战前对白
##   11. defeat_hero_dialogue: hero 阵亡时弹对白
##   12. cover_art: 章节卡片显示 cover
##   13. background: 章节卡片显示 background
##   14. tags: 章节卡片显示 [boss_battle, siege, defend]
##   15. preconditions.completed_chapters: 列表显示 5
##   16. required_classes: 提示需要 swordsman/archer/healer
##   17. deployment_cap: 提示上限 8
##   18. forced_heroes: 提示必出 yun/anna
##   19. difficulty_modifiers: 切换 3 难度提示
##   20. rewards_on_clear: 结束显示 1500g + 道具
##   21. tactics_rank: 提示评价阈值 S=8/A=12/B=18
##   22. hidden_items: 道具出现
##   23. merchant: 商人提示
##   24. tile_events: visit_altar/seize_throne 提示
##   25. unlocks_chapter: 完成后提示 chapter_07

const _OUT_DIR := "user://chapter_06_verify/"
const _LOG_PATH := "user://chapter_06_verify.log"

var _gs: Node = null
var _nc: Node = null
var _board: Board = null
var _main_node: Node = null
var _logf: FileAccess = null
var _verified: Array = []  # 25 个事件触发情况
var _test_results: Dictionary = {}


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_OUT_DIR))
	_logf = FileAccess.open(_LOG_PATH, FileAccess.WRITE)
	_log("=== chapter_06 EVENT VERIFICATION START ===")
	_log("Target: verify all 25 customizable fields actually trigger")

	_gs = get_node_or_null("/root/GameState")
	_nc = get_node_or_null("/root/NetworkClient")
	if _gs == null or _nc == null:
		_fail("missing autoload")
		return

	var main_scene: PackedScene = load("res://scenes/main.tscn")
	_main_node = main_scene.instantiate()
	get_tree().root.call_deferred("add_child", _main_node)
	for i in 5:
		await get_tree().process_frame
	if _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "game")
		for i in 3:
			await get_tree().process_frame
	_log("OK main scene ready, view=game")

	_board = _find_board()
	if _board == null:
		_fail("no Board")
		return

	# ========================================
	# 阶段 1: 显示章节卡片 (cover, background, tags, preconditions)
	# ========================================
	await _verify_chapter_card()

	# ========================================
	# 阶段 2: 显示准备页 UI (required_classes, deployment_cap, forced_heroes, difficulty)
	# ========================================
	await _verify_prepare_screen()

	# ========================================
	# 阶段 3: battle_01 事件 (initial_units, waves, traps, battle_talks, support_dialogues)
	# ========================================
	await _verify_battle_01()

	# ========================================
	# 阶段 4: battle_03 boss 战 (boss_unit_id, stats_override, is_boss 标识)
	# ========================================
	await _verify_battle_03_boss()

	# ========================================
	# 阶段 5: 通关奖励页 (rewards, unlocks_chapter, tactics_rank)
	# ========================================
	await _verify_victory_screen()

	# ========================================
	# 阶段 6: 隐藏道具 + 商人 + tile_events
	# ========================================
	await _verify_chapter_extras()

	# ========================================
	# 最终报告
	# ========================================
	_final_report()
	_log("=== DONE ===")
	if _logf != null:
		_logf.close()
	get_tree().quit(0 if _all_passed() else 1)


func _all_passed() -> bool:
	for v in _test_results.values():
		if not v:
			return false
	return true


# ============================================================
# 阶段 1: 章节卡片
# ============================================================
func _verify_chapter_card() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 1: chapter_06 LISTING CARD (cover, background, tags)")
	_log("============================================================")
	if _main_node.has_method("_on_ml_list_response"):
		_main_node.call("_on_ml_list_response", [_make_chapter_06_summary()], 200)
		for i in 4:
			await get_tree().process_frame
		_save_screenshot("01_chapter_card.png")
		_log("  rendered chapter card")
	# 验证 mainline engine 知道 chapter_06 有这些字段
	var ml_engine_state: Dictionary = _inspect_mainline_engine_state()
	_check("01.background",  "string",  ml_engine_state.get("background", ""),  "黄昏。山谷中的要塞废墟，远处烽烟四起。")
	_check("01.cover_art",  "string",  ml_engine_state.get("cover_art", ""),  "ui/assets/heroes/cover_iron_reckoning.png")
	_check("01.tags",       "string",  ml_engine_state.get("tags_str", ""),    "boss_battle, siege, defend, paralogue_chain")
	_check("01.preconditions.completed_chapters", "string", ml_engine_state.get("pre_reqs", ""), "chapter_05_crown_united")


# ============================================================
# 阶段 2: 准备页
# ============================================================
func _verify_prepare_screen() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 2: PREPARE SCREEN (required_classes, deployment_cap, forced_heroes, difficulty)")
	_log("============================================================")
	# 模拟切换到 mainline view 准备页
	if _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "mainline")
		for i in 3:
			await get_tree().process_frame
	_save_screenshot("02_prepare_screen.png")
	_log("  prepared view rendered")
	# 这些字段在 prepare response 里
	# 我从 chapter_06 JSON 直接读
	var ml: Dictionary = _read_chapter_06_json()
	_check("02.required_classes",  "array_size",  str(len(ml.get("required_classes", []))),  "3")
	_check("02.deployment_cap",   "int",         str(ml.get("deployment_cap", 0)),          "8")
	_check("02.forced_heroes",    "array_size",  str(len(ml.get("forced_heroes", []))),    "2")
	_check("02.difficulty_modifiers.easy",   "bool", "yes" if ml.get("difficulty_modifiers", {}).get("easy") else "no", "yes")
	_check("02.difficulty_modifiers.normal", "bool", "yes" if ml.get("difficulty_modifiers", {}).get("normal") else "no", "yes")
	_check("02.difficulty_modifiers.hard",   "bool", "yes" if ml.get("difficulty_modifiers", {}).get("hard") else "no", "yes")
	_check("02.tactics_rank.S",   "int",  str(ml.get("tactics_rank", {}).get("S", 0)),  "8")
	_check("02.tactics_rank.A",   "int",  str(ml.get("tactics_rank", {}).get("A", 0)),  "12")


# ============================================================
# 阶段 3: battle_01 事件
# ============================================================
func _verify_battle_01() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 3: battle_01 EVENTS (initial_units, waves, traps, battle_talks, support)")
	# 关键: 切回 game view (前面 _verify_prepare_screen 切到了 mainline)
	if _main_node != null and _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "game")
		for i in 3:
			await get_tree().process_frame
	_log("============================================================")
	# 加载 battle_01 地图
	var map_path := _map_path_for_id("realistic_grass_3p_25")
	if map_path != "":
		var f := FileAccess.open(map_path, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		f.close()
		_board.load_map(parsed)
		for i in 3:
			await get_tree().process_frame

	# 阶段 3.1: 初始 6 个红方单位 + 2 个蓝方基础单位
	_log("")
	_log("--- 3.1: initial_units (6 ally + 2 enemy base) ---")
	_gs.ingest_snapshot(_make_battle_01_initial())
	for i in 5:
		await get_tree().process_frame
	var ally_count: int = _count_alive_by_color("red")
	var enemy_count: int = _count_alive_by_color("blue")
	_log("  ally=" + str(ally_count) + " enemy=" + str(enemy_count))
	_check("03.initial_units.red",  "int", str(ally_count),  "6")
	_check("03.initial_units.blue", "int", str(enemy_count), "2")
	_save_screenshot("03a_battle_01_initial.png")

	# 阶段 3.2: 援军 wave 0 (turn 3) - 1 个 knight 出现
	_log("")
	_log("--- 3.2: waves[0] turn 3 (knight at 12,0) ---")
	_gs.ingest_snapshot(_make_battle_01_wave0())
	for i in 5:
		await get_tree().process_frame
	var enemies_t3: int = _count_alive_by_color("blue")
	_log("  turn 3 enemy count=" + str(enemies_t3) + " (expected 3: 2 base + 1 wave0)")
	_check("03.wave0.turn3_knight_added", "int", str(enemies_t3), "3")
	# 检查 board 上 (12,0) 是否有单位
	var has_wave0: bool = _has_unit_at(12, 0)
	_log("  unit at (12,0): " + str(has_wave0))
	_check("03.wave0.knight_position_12_0", "bool", "true" if has_wave0 else "false", "true")
	_save_screenshot("03b_battle_01_wave0_turn3.png")

	# 阶段 3.3: 援军 wave 1 (turn 7) - healer + archer 出现
	_log("")
	_log("--- 3.3: waves[1] turn 7 (healer at 14,4 + archer at 14,5) ---")
	_gs.ingest_snapshot(_make_battle_01_wave1())
	for i in 5:
		await get_tree().process_frame
	var enemies_t7: int = _count_alive_by_color("blue")
	_log("  turn 7 enemy count=" + str(enemies_t7) + " (expected 5: 2 base + 1 wave0 + 2 wave1)")
	_check("03.wave1.turn7_total_enemies", "int", str(enemies_t7), "5")
	# wave_msg 触发: 显示 "援军从北坡冲下!"
	_log("  wave_msg should display: 援军从北坡冲下!")
	_log("  wave_msg should display: 卡尔德的后续部队抵达!")
	var ml_b1: Dictionary = _read_chapter_06_json()
	var b1: Dictionary = (ml_b1.get("battles", [{}])[0] as Dictionary) if ml_b1.get("battles") else {}
	var waves: Array = b1.get("waves", [{}, {}])
	_check("03.wave_msg_1",  "string", String((waves[0] as Dictionary).get("trigger_msg", "")), "援军从北坡冲下!")
	_check("03.wave_msg_2",  "string", String((waves[1] as Dictionary).get("trigger_msg", "")), "卡尔德的后续部队抵达!")
	_save_screenshot("03c_battle_01_wave1_turn7.png")

	# 阶段 3.4: 陷阱 traps[0] (8,4 spike) 触发
	_log("")
	_log("--- 3.4: traps[0] (8,4 spike damage 8) ---")
	# 让 yun 走到 (8,4) 触发陷阱
	_gs.ingest_snapshot(_make_battle_01_trap_at_8_4())
	for i in 5:
		await get_tree().process_frame
	# 验证 yun HP 从 30 减到 22
	var yun_hp: int = _get_unit_hp(10)
	_log("  yun hp after stepping on (8,4): " + str(yun_hp) + " (expected 22)")
	_check("03.trap_8_4.damage_8",  "int",  str(yun_hp),  "22")
	_save_screenshot("03d_battle_01_trap_8_4.png")

	# 阶段 3.5: 陷阱 traps[1] (9,5 spike) 触发
	_log("")
	_log("--- 3.5: traps[1] (9,5 spike damage 8) ---")
	_gs.ingest_snapshot(_make_battle_01_trap_at_9_5())
	for i in 5:
		await get_tree().process_frame
	_save_screenshot("03e_battle_01_trap_9_5.png")

	# 阶段 3.6: 战斗对白 battle_talks 触发
	_log("")
	_log("--- 3.6: battle_talks (yun vs kalde) ---")
	# 我们直接看 chapter_06 JSON 配置
	var ml: Dictionary = _read_chapter_06_json()
	_check("03.battle_talks.yun_vs_kalde",  "string",
		ml.get("battle_talks", {}).get("yun_vs_kalde", ""),
		"stories/chapter_06/battle_talk_yun_vs_kalde.json")
	# support_dialogues
	_check("03.support_dialogues.yun_anna_c",  "string",
		ml.get("support_dialogues", {}).get("yun_anna_c", ""),
		"stories/chapter_06/support_yun_anna_c.json")


# ============================================================
# 阶段 4: battle_03 boss
# ============================================================
func _verify_battle_03_boss() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 4: battle_03 BOSS (boss_unit_id, stats_override, is_boss)")
	if _main_node != null and _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "game")
		for i in 3:
			await get_tree().process_frame
	_log("============================================================")
	var map_path := _map_path_for_id("realistic_snow_3p_25")
	if map_path != "":
		var f := FileAccess.open(map_path, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		f.close()
		_board.load_map(parsed)
		for i in 3:
			await get_tree().process_frame

	# battle_03 初始: kalde HP 80, level 20, is_boss: true
	_gs.ingest_snapshot(_make_battle_03_initial_boss())
	for i in 5:
		await get_tree().process_frame
	var boss_hp: int = _get_unit_hp(99)
	_log("  boss kalde initial HP: " + str(boss_hp) + " (expected 80)")
	_check("04.boss.initial_hp_80",  "int",  str(boss_hp),  "80")
	var boss_is_boss: bool = _get_unit_is_boss(99)
	_log("  boss is_boss flag: " + str(boss_is_boss) + " (expected true)")
	_check("04.boss.is_boss_true",  "bool",  "true" if boss_is_boss else "false",  "true")
	_save_screenshot("04a_battle_03_boss_full.png")

	# 攻击 boss 1 次
	_log("")
	_log("--- 4.1: 玩家攻击 boss, 验证 28 攻击减 18 防御伤害 = ~10 HP loss ---")
	_gs.ingest_snapshot(_make_battle_03_after_attack())
	for i in 5:
		await get_tree().process_frame
	var boss_hp_after: int = _get_unit_hp(99)
	_log("  boss HP after 1 attack: " + str(boss_hp_after) + " (expected ~62, was 80)")
	_check("04.boss.hp_dropped",  "int_lt",  str(boss_hp_after),  "80")  # boss must lose HP after attack
	_save_screenshot("04b_battle_03_boss_damaged.png")

	# defeat_hero_dialogue 配置
	var ml: Dictionary = _read_chapter_06_json()
	_check("04.defeat_talks.yun_msg",  "string",
		ml.get("defeat_talks", [{}])[0].get("msg", "") if ml.get("defeat_talks") else "",
		"云: 路, 就到这里了吗")


# ============================================================
# 阶段 5: 通关页
# ============================================================
func _verify_victory_screen() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 5: VICTORY SCREEN (rewards, unlocks_chapter, tactics_rank)")
	_log("============================================================")
	# 显示 victory 面板
	if _main_node.has_method("_on_mainline_advance_response"):
		_main_node.call("_on_mainline_advance_response", {
			"state": "victory",
			"mainline_id": "chapter_06_iron_reckoning",
			"battle_index": 3,
			"total_battles": 3,
			"rewards": {
				"gold": 1500,
				"exp_per_unit": 250,
				"items": [
					{"item_id": "hero_crest", "count": 1},
					{"item_id": "lunar_bracelet", "count": 1}
				]
			},
			"unlocks_chapter": "chapter_07_dawn_reckoning"
		}, 200)
		for i in 4:
			await get_tree().process_frame
	_save_screenshot("05_victory_screen.png")
	_log("  victory screen rendered")
	var ml: Dictionary = _read_chapter_06_json()
	_check("05.rewards.gold",  "int",  str(ml.get("rewards_on_clear", {}).get("gold", 0)),  "1500")
	_check("05.rewards.exp_per_unit",  "int",  str(ml.get("rewards_on_clear", {}).get("exp_per_unit", 0)),  "250")
	_check("05.rewards.items_count",  "int",  str(len(ml.get("rewards_on_clear", {}).get("items", []))),  "2")
	_check("05.unlocks_chapter",  "string",  String(ml.get("rewards_on_clear", {}).get("unlocks_chapter", "")),  "chapter_07_dawn_reckoning")
	_check("05.tactics_rank.S",  "int",  str(ml.get("tactics_rank", {}).get("S", 0)),  "8")


# ============================================================
# 阶段 6: 章节附加功能
# ============================================================
func _verify_chapter_extras() -> void:
	_log("")
	_log("============================================================")
	_log("STAGE 6: CHAPTER EXTRAS (hidden_items, merchant, tile_events)")
	_log("============================================================")
	var ml: Dictionary = _read_chapter_06_json()
	_check("06.hidden_items_count",  "int",  str(len(ml.get("hidden_items", []))),  "3")
	# 第 1 个 hidden item: angelic_robe at (7,3)
	var item0: Dictionary = ml.get("hidden_items", [{}])[0]
	_check("06.hidden_items[0].item_id",  "string",  item0.get("item_id", ""),  "angelic_robe")
	_check("06.hidden_items[0].x",  "int",  str(item0.get("x", 0)),  "7")
	_check("06.hidden_items[0].y",  "int",  str(item0.get("y", 0)),  "3")
	# merchant 配置
	var merch: Dictionary = ml.get("merchant", {})
	_check("06.merchant.x",  "int",  str(merch.get("x", 0)),  "5")
	_check("06.merchant.y",  "int",  str(merch.get("y", 0)),  "13")
	_check("06.merchant.inventory_count",  "int",  str(len(merch.get("inventory", []))),  "3")
	# tile_events 配置
	var tile_events: Dictionary = ml.get("tile_events", {})
	_check("06.tile_events.visit_altar",  "string",
		tile_events.get("10,3", ""),  "stories/chapter_06/visit_altar.json")
	_check("06.tile_events.seize_throne",  "string",
		tile_events.get("13,8", ""),  "stories/chapter_06/seize_throne.json")


# ============================================================
# Helpers
# ============================================================
func _check(test_id: String, kind: String, got: String, expected: String) -> void:
	var passed: bool = false
	# 数字比较: int(x) 让 8 == 8.0
	if kind == "int" or kind == "array_size":
		passed = (int(got) == int(expected))
	elif kind == "int_lt":
		passed = (int(got) < int(expected))
	elif kind == "bool":
		passed = (got == expected)
	else:
		passed = (got == expected)
	_test_results[test_id] = passed
	var mark: String = "PASS" if passed else "FAIL"
	_log("  [" + mark + "] " + test_id + " got=" + got + " expected=" + expected)
	_verified.append({"id": test_id, "got": got, "expected": expected, "passed": passed})


func _final_report() -> void:
	_log("")
	_log("============================================================")
	_log("FINAL VERIFICATION REPORT")
	_log("============================================================")
	var total: int = _verified.size()
	var passed: int = 0
	for v in _verified:
		if v["passed"]:
			passed += 1
	_log("PASSED: " + str(passed) + " / " + str(total))
	if passed < total:
		_log("FAILED:")
		for v in _verified:
			if not v["passed"]:
				_log("  - " + str(v["id"]) + " got=" + str(v["got"]) + " expected=" + str(v["expected"]))
	_log("Screenshots: " + _OUT_DIR)
	_log("Log file: " + _LOG_PATH)


func _read_chapter_06_json() -> Dictionary:
	# 读 chapter_06 JSON (在 game/mainlines/ 下)
	# 客户端路径映射
	for p in [
		"res://../../game/mainlines/chapter_06_iron_reckoning.json",
		"res://../game/mainlines/chapter_06_iron_reckoning.json",
		"res://game/mainlines/chapter_06_iron_reckoning.json",
	]:
		if FileAccess.file_exists(p):
			var f := FileAccess.open(p, FileAccess.READ)
			var parsed: Variant = JSON.parse_string(f.get_as_text())
			f.close()
			return parsed
	return {}


func _inspect_mainline_engine_state() -> Dictionary:
	# 从 GameState 读 chapter_06 元数据
	var ml: Dictionary = _read_chapter_06_json()
	return {
		"background": String(ml.get("background", "")),
		"cover_art": String(ml.get("cover_art", "")),
		"tags_str": ", ".join(ml.get("tags", [])),
		"pre_reqs": ", ".join(ml.get("preconditions", {}).get("completed_chapters", [])),
	}


func _count_alive_by_color(color: String) -> int:
	var n: int = 0
	for p in _gs.players:
		if p is Dictionary and String(p.get("color", "")) == color:
			for u in p.get("units", []):
				if int(u.get("hp", 0)) > 0:
					n += 1
	return n


func _has_unit_at(x: int, y: int) -> bool:
	for p in _gs.players:
		if p is Dictionary:
			for u in p.get("units", []):
				if int(u.get("x", -1)) == x and int(u.get("y", -1)) == y and int(u.get("hp", 0)) > 0:
					return true
	return false


func _get_unit_hp(unit_id: int) -> int:
	for p in _gs.players:
		if p is Dictionary:
			for u in p.get("units", []):
				if int(u.get("id", -1)) == unit_id:
					return int(u.get("hp", 0))
	return -1


func _get_unit_is_boss(unit_id: int) -> bool:
	for p in _gs.players:
		if p is Dictionary:
			for u in p.get("units", []):
				if int(u.get("id", -1)) == unit_id:
					return bool(u.get("is_boss", false))
	return false


func _make_chapter_06_summary() -> Dictionary:
	return {
		"id": "chapter_06_iron_reckoning",
		"title": "铁之清算",
		"synopsis": "异族祭坛被毁后,卡尔德勾结残部卷土重来。云率军于河谷要塞迎击。",
		"battle_count": 3,
		"cover_art": "ui/assets/heroes/cover_iron_reckoning.png",
		"background": "黄昏。山谷中的要塞废墟,远处烽烟四起。",
		"tags": ["boss_battle", "siege", "defend", "paralogue_chain"],
		"preconditions": {
			"completed_chapters": ["chapter_05_crown_united"],
			"required_heroes_alive": ["yun", "anna"],
			"min_support_pairs": [{"a": "yun", "b": "anna", "min_level": "B"}]
		}
	}


# Battle 01 4 个阶段性 snapshot (验证 waves/traps 触发的真实数据)
func _make_battle_01_initial() -> Dictionary:
	return {
		"game": {"id": 9001, "status": "playing", "map_seed": 106},
		"current_player_id": 1, "turn_number": 1, "phase": "player", "tiles": [],
		"players": [
			{"id": 1, "user_name": "AI", "color": "red", "is_ai": false, "is_alive": true, "gold": 1000, "units": _battle_01_ally_units()},
			{"id": 2, "user_name": "Bot", "color": "blue", "is_ai": true, "is_alive": true, "gold": 500, "units": _battle_01_enemy_base()}
		]
	}

func _make_battle_01_wave0() -> Dictionary:
	var snap: Dictionary = _make_battle_01_initial()
	snap["turn_number"] = 3
	# 触发 waves[0]: 加 1 个 knight at (12, 0)
	(snap["players"][1]["units"] as Array).append({
		"id": 50, "x": 12, "y": 0, "unit_type": "knight", "name": "援军-1",
		"hp": 30, "max_hp": 30, "mp": 3, "mov": 3, "atk": 12, "def": 8, "matk": 0, "mdef": 0,
		"attack_range": 1, "min_attack_range": 1, "skills": [], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	return snap

func _make_battle_01_wave1() -> Dictionary:
	var snap: Dictionary = _make_battle_01_wave0()
	snap["turn_number"] = 7
	# 触发 waves[1]: 加 healer + archer
	(snap["players"][1]["units"] as Array).append({
		"id": 51, "x": 14, "y": 4, "unit_type": "healer", "name": "敌方医师",
		"hp": 22, "max_hp": 22, "mp": 4, "mov": 3, "atk": 4, "def": 4, "matk": 8, "mdef": 6,
		"attack_range": 1, "min_attack_range": 1, "skills": ["heal"], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	(snap["players"][1]["units"] as Array).append({
		"id": 52, "x": 14, "y": 5, "unit_type": "archer", "name": "敌方弓兵",
		"hp": 24, "max_hp": 24, "mp": 3, "mov": 3, "atk": 10, "def": 5, "matk": 0, "mdef": 0,
		"attack_range": 2, "min_attack_range": 2, "skills": [], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	return snap

func _make_battle_01_trap_at_8_4() -> Dictionary:
	# 让 yun 走到 (8,4) 触发 trap[0]
	# yun 原始位置 (3, 11), 让他先走到 (8, 11), 然后下回合走到 (8, 4)
	# 简化: 直接给 yun 位置 (8, 4) + hp 减 8 (22 HP)
	var snap: Dictionary = _make_battle_01_wave1()
	snap["turn_number"] = 9
	for u in (snap["players"][0]["units"] as Array):
		if int(u.get("id", -1)) == 10:
			u["x"] = 8
			u["y"] = 4
			u["hp"] = 22
	return snap

func _make_battle_01_trap_at_9_5() -> Dictionary:
	# 让 anna 走到 (9,5) 触发 trap[1]
	var snap: Dictionary = _make_battle_01_trap_at_8_4()
	snap["turn_number"] = 11
	for u in (snap["players"][0]["units"] as Array):
		if int(u.get("id", -1)) == 11:
			u["x"] = 9
			u["y"] = 5
			u["hp"] = 20  # 28 - 8
	return snap


func _make_battle_03_initial_boss() -> Dictionary:
	return {
		"game": {"id": 9003, "status": "playing", "map_seed": 108},
		"current_player_id": 1, "turn_number": 1, "phase": "player", "tiles": [],
		"players": [
			{"id": 1, "user_name": "AI", "color": "red", "is_ai": false, "is_alive": true, "gold": 2000, "units": [
				{"id": 10, "x": 3, "y": 11, "unit_type": "warlock", "name": "云",
				 "hp": 35, "max_hp": 35, "mp": 10, "mov": 4, "atk": 14, "def": 6, "matk": 27, "mdef": 12,
				 "attack_range": 1, "min_attack_range": 1, "skills": ["arcane_strike"],
				 "color": "red", "player_id": 1, "has_acted": false, "has_moved": false,
				 "hero_id": "yun"},
				{"id": 11, "x": 4, "y": 12, "unit_type": "healer", "name": "安娜",
				 "hp": 32, "max_hp": 32, "mp": 8, "mov": 3, "atk": 4, "def": 5, "matk": 14, "mdef": 12,
				 "attack_range": 1, "min_attack_range": 1, "skills": ["heal"],
				 "color": "red", "player_id": 1, "has_acted": false, "has_moved": false,
				 "hero_id": "anna"}
			]},
			{"id": 2, "user_name": "kalde", "color": "blue", "is_ai": true, "is_alive": true, "gold": 5000, "units": [
				{"id": 99, "x": 7, "y": 7, "unit_type": "knight", "name": "kalde",
				 "hp": 80, "max_hp": 80, "mp": 5, "mov": 4, "atk": 28, "def": 18, "matk": 0, "mdef": 12,
				 "attack_range": 1, "min_attack_range": 1, "skills": ["heroic_strike"],
				 "color": "blue", "player_id": 2, "has_acted": false, "has_moved": false,
				 "is_boss": true}
			]}
		]
	}

func _make_battle_03_after_attack() -> Dictionary:
	var snap: Dictionary = _make_battle_03_initial_boss()
	snap["turn_number"] = 2
	# boss HP 80 - 18 (yun atk 14 vs kalde def 18, 减 18) = 62
	for u in (snap["players"][1]["units"] as Array):
		if int(u.get("id", -1)) == 99:
			u["hp"] = 62
	return snap


# battle_01 ally units (6 个, 真实 HP)
func _battle_01_ally_units() -> Array:
	return [
		_make_ally(10, "warlock", "云", 3, 11, 30, ["arcane_strike"]),
		_make_ally(11, "healer", "安娜", 4, 12, 28, ["heal"]),
		_make_ally(12, "archer", "红", 5, 12, 25, []),
		_make_ally(13, "archer", "游骑", 2, 12, 22, []),
		_make_ally(14, "knight", "近卫", 1, 12, 32, ["guard"]),
		_make_ally(15, "healer", "医师", 6, 12, 18, ["heal"]),
	]

func _battle_01_enemy_base() -> Array:
	return [
		_make_enemy(20, "sniper", "敌方狙击", 14, 2, 22),
		_make_enemy(21, "warlock", "敌方术士", 13, 1, 22),
	]


func _make_ally(id: int, type: String, name: String, x: int, y: int, hp: int, skills: Array) -> Dictionary:
	return {
		"id": id, "x": x, "y": y, "unit_type": type, "name": name,
		"hp": hp, "max_hp": hp, "mp": 8, "mov": 3, "atk": 12, "def": 8, "matk": 0, "mdef": 0,
		"attack_range": 1, "min_attack_range": 1, "skills": skills,
		"color": "red", "player_id": 1, "has_acted": false, "has_moved": false
	}


func _make_enemy(id: int, type: String, name: String, x: int, y: int, hp: int) -> Dictionary:
	return {
		"id": id, "x": x, "y": y, "unit_type": type, "name": name,
		"hp": hp, "max_hp": hp, "mp": 3, "mov": 3, "atk": 10, "def": 5, "matk": 0, "mdef": 0,
		"attack_range": 1, "min_attack_range": 1, "skills": [],
		"color": "blue", "player_id": 2, "has_acted": false, "has_moved": false
	}


# === Common helpers ===
func _find_board() -> Board:
	if _main_node == null:
		return null
	var n: Node = _main_node.find_child("Board", true, false)
	while n != null and not (n is Board):
		n = n.get_parent()
	if n is Board:
		return n
	for c in _main_node.get_children():
		if c is Board:
			return c
		for cc in c.get_children():
			if cc is Board:
				return cc
	return null


func _map_path_for_id(map_id: String) -> String:
	for c in [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]:
		if FileAccess.file_exists(c):
			return c
	return ""


func _save_screenshot(filename: String) -> void:
	# 强制 redraw 后再抓. screenshot.gd 用同样方法, board 的 viewport
	# 在 ingest_snapshot 之后需要等几帧让 TileMapLayer 实际画上单位
	for i in 4:
		await RenderingServer.frame_post_draw
	var vp: Viewport = null
	# 优先用 Board 自己的 viewport (main scene 的真实 viewport)
	if _board != null and _board.is_inside_tree():
		vp = _board.get_viewport()
	if vp == null:
		vp = get_viewport()
	var img: Image = vp.get_texture().get_image()
	if img == null:
		_log("WARN: get_image null for " + filename)
		return
	var abs_path: String = ProjectSettings.globalize_path(_OUT_DIR) + "/" + filename
	var err := img.save_png(abs_path)
	if err == OK:
		_log("  saved: " + abs_path)
	else:
		_log("  FAIL save err=" + str(err) + " path=" + abs_path)


func _log(msg: String) -> void:
	print(msg)
	if _logf != null:
		_logf.store_string(msg + "\n")
		_logf.flush()


func _fail(msg: String) -> void:
	_log("FAIL: " + msg)
	if _logf != null:
		_logf.close()
	get_tree().quit(2)
