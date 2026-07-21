extends Node
## chapter_06_trigger_test.gd
##
## 端到端触发 chapter_06_iron_reckoning 的关键事件并截图。
## 用法:
##   "<godot_exe>" --rendering-driver opengl3 --path godot-client res://tools/chapter_06_trigger_test.tscn
##
## 关键: ingest_snapshot 之前必须 board.load_map() 否则地图层为空。

const _OUT_DIR := "user://chapter_06_screenshots/"
const _MAP_TO_RENDER := "balanced_2p_15"  # 用现有地图占位

var _gs: Node = null
var _nc: Node = null
var _board: Board = null
var _main_node: Node = null


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_OUT_DIR))
	print("=== chapter_06 trigger test START ===")

	var game_state := get_node_or_null("/root/GameState")
	var network_client := get_node_or_null("/root/NetworkClient")
	if game_state == null or network_client == null:
		printerr("FAIL: missing autoload GameState/NetworkClient")
		get_tree().quit(2)
		return
	_gs = game_state
	_nc = network_client

	# 加载 main scene
	var main_scene: PackedScene = load("res://scenes/main.tscn")
	if main_scene == null:
		printerr("FAIL: cannot load res://scenes/main.tscn")
		get_tree().quit(2)
		return
	_main_node = main_scene.instantiate()
	get_tree().root.call_deferred("add_child", _main_node)
	for i in 5:
		await get_tree().process_frame
	# 等 main_node _ready 完
	await get_tree().process_frame
	print("OK main scene instantiated,", _main_node.get_child_count(), "children")

	# 切到 game view (默认是 mainline)
	if _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "game")
		for i in 3:
			await get_tree().process_frame
		print("OK switched to game view")

	# 找 Board
	_board = _find_board()
	if _board == null:
		printerr("FAIL: no Board in main scene")
		get_tree().quit(2)
		return
	print("OK found Board")

	# ⚠ 关键: 先 load_map, 再 ingest_snapshot
	# 否则 board 上没有 TileMapLayer, 即使有 units 也看不到
	var map_path := _map_path_for_id(_MAP_TO_RENDER)
	if map_path == "":
		printerr("FAIL: no map file for ", _MAP_TO_RENDER)
		get_tree().quit(2)
		return
	var f := FileAccess.open(map_path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	print("DEBUG parsed type=", typeof(parsed), " is Dict=", parsed is Dictionary)
	if not (parsed is Dictionary):
		printerr("FAIL: map JSON not a Dictionary, got type=", typeof(parsed))
		get_tree().quit(2)
		return
	_board.load_map(parsed)
	for i in 3:
		await RenderingServer.frame_post_draw
	print("OK board loaded map: ", _MAP_TO_RENDER)

	# === 5 张截图 ===
	# 关键: ingest 后等 6 帧 + frame_post_draw, 让 board 真正画上单位
	# Units spawn 是异步的: 收到 units_changed 信号后第 1 帧
	# 创建 UnitNode, 第 2-3 帧加载 sprite, 第 4 帧到位, 第 5+帧
	# 渲染稳定
	# 1. battle_01 初始 (7 玩家单位)
	_gs.ingest_snapshot(_make_battle_01_initial_snapshot())
	for i in 6:
		await get_tree().process_frame
	for i in 2:
		await RenderingServer.frame_post_draw
	print("OK injected battle_01 initial (7 ally + 2 enemy)")
	_save_screenshot(_OUT_DIR + "01_battle_01_initial.png")

	# 2. wave1 (turn 3, 加 1 个 knight)
	_gs.ingest_snapshot(_make_battle_01_wave1_snapshot())
	for i in 6:
		await get_tree().process_frame
	for i in 2:
		await RenderingServer.frame_post_draw
	print("OK injected wave1 (turn 3, 1 knight)")
	_save_screenshot(_OUT_DIR + "02_battle_01_wave1.png")

	# 3. wave2 (turn 7, 加 healer + archer)
	_gs.ingest_snapshot(_make_battle_01_wave2_snapshot())
	for i in 6:
		await get_tree().process_frame
	for i in 2:
		await RenderingServer.frame_post_draw
	print("OK injected wave2 (turn 7, healer+archer)")
	_save_screenshot(_OUT_DIR + "03_battle_01_wave2.png")

	# 4. battle_03 boss (kalde)
	_gs.ingest_snapshot(_make_battle_03_boss_snapshot())
	for i in 6:
		await get_tree().process_frame
	for i in 2:
		await RenderingServer.frame_post_draw
	print("OK injected battle_03 boss (kalde HP 80, level 20)")
	_save_screenshot(_OUT_DIR + "04_battle_03_boss.png")

	# 5. 切到 mainline 列表 view, 看章节卡片
	if _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "mainline")
		for i in 2:
			await RenderingServer.frame_post_draw
		if _main_node.has_method("_on_ml_list_response"):
			_main_node.call("_on_ml_list_response", [{
				"id": "chapter_06_iron_reckoning",
				"title": "铁之清算",
				"synopsis": "异族祭坛被毁后,卡尔德勾结残部卷土重来。",
				"battle_count": 3,
				"cover_art": null,
			}], 200)
			for i in 6:
				await get_tree().process_frame
			for i in 2:
				await RenderingServer.frame_post_draw
			print("OK chapter listing rendered")
			_save_screenshot(_OUT_DIR + "05_chapter_06_listing.png")

	print("=== chapter_06 trigger test DONE ===")
	get_tree().quit(0)


func _find_board() -> Board:
	if _main_node == null:
		return null
	var n: Node = _main_node.find_child("Board", true, false)
	while n != null and not (n is Board):
		n = n.get_parent()
	if n is Board:
		return n
	# 兜底: 遍历所有子节点
	for c in _main_node.get_children():
		if c is Board:
			return c
		for cc in c.get_children():
			if cc is Board:
				return cc
	return null


func _save_screenshot(path: String) -> void:
	# Use the board's viewport (main scene's viewport) — NOT get_viewport()
	# which returns our own viewport (Chapter06TriggerTest) and is empty.
	var vp: Viewport = null
	if _board != null:
		vp = _board.get_viewport()
	if vp == null:
		vp = get_viewport()
	var img: Image = vp.get_texture().get_image()
	if img == null:
		printerr("WARN: get_image() null for ", path)
		return
	var abs_path := ProjectSettings.globalize_path(path)
	var err := img.save_png(abs_path)
	if err == OK:
		print("  saved: ", abs_path, " (", _get_file_size(abs_path), " bytes)")
	else:
		printerr("  FAIL save: ", abs_path, " err=", err)


func _get_file_size(path: String) -> int:
	if not FileAccess.file_exists(path):
		return 0
	return FileAccess.open(path, FileAccess.READ).get_length()


func _map_path_for_id(map_id: String) -> String:
	var candidates := [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	return ""


# === Battle 01 初始 (7 红方, 2 蓝方基础) ===
func _make_battle_01_initial_snapshot() -> Dictionary:
	return {
		"game": {"id": 9001, "status": "playing", "map_seed": 106},
		"current_player_id": 1,
		"turn_number": 1,
		"phase": "player",
		"tiles": [],
		"players": [
			{"id": 1, "user_name": "Alice", "color": "red", "is_ai": false, "is_alive": true,
			 "gold": 1000, "units": _make_ally_units()},
			{"id": 2, "user_name": "Bot", "color": "blue", "is_ai": true, "is_alive": true,
			 "gold": 500, "units": _make_enemy_base_units()}
		]
	}


func _make_battle_01_wave1_snapshot() -> Dictionary:
	var s: Dictionary = _make_battle_01_initial_snapshot()
	s["turn_number"] = 3
	var p2: Dictionary = s["players"][1]
	p2["units"] = (p2["units"] as Array).duplicate()
	(p2["units"] as Array).append({
		"id": 50, "x": 12, "y": 0, "unit_type": "knight", "name": "援军-1",
		"hp": 30, "max_hp": 30, "mp": 3, "mov": 3, "atk": 12, "def": 8, "matk": 0, "mdef": 0,
		"attack_range": 1, "skills": [], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	return s


func _make_battle_01_wave2_snapshot() -> Dictionary:
	var s: Dictionary = _make_battle_01_wave1_snapshot()
	s["turn_number"] = 7
	var p2: Dictionary = s["players"][1]
	p2["units"] = (p2["units"] as Array).duplicate()
	(p2["units"] as Array).append({
		"id": 51, "x": 14, "y": 4, "unit_type": "healer", "name": "敌方医师",
		"hp": 22, "max_hp": 22, "mp": 4, "mov": 3, "atk": 4, "def": 4, "matk": 8, "mdef": 6,
		"attack_range": 1, "skills": ["heal"], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	(p2["units"] as Array).append({
		"id": 52, "x": 14, "y": 5, "unit_type": "archer", "name": "敌方弓兵",
		"hp": 24, "max_hp": 24, "mp": 3, "mov": 3, "atk": 10, "def": 5, "matk": 0, "mdef": 0,
		"attack_range": 2, "min_attack_range": 2, "skills": [], "color": "blue", "player_id": 2,
		"has_acted": false, "has_moved": false
	})
	return s


func _make_battle_03_boss_snapshot() -> Dictionary:
	return {
		"game": {"id": 9003, "status": "playing", "map_seed": 108},
		"current_player_id": 1,
		"turn_number": 1,
		"phase": "player",
		"tiles": [],
		"players": [
			{"id": 1, "user_name": "Alice", "color": "red", "is_ai": false, "is_alive": true,
			 "gold": 2000, "units": [
				{"id": 10, "x": 3, "y": 11, "unit_type": "warlock", "name": "云",
				 "hp": 35, "max_hp": 35, "mp": 10, "mov": 4, "atk": 14, "def": 6, "matk": 27, "mdef": 12,
				 "attack_range": 1, "min_attack_range": 1, "skills": ["arcane_strike"], "color": "red", "player_id": 1,
				 "has_acted": false, "has_moved": false, "hero_id": "yun"},
				{"id": 11, "x": 4, "y": 12, "unit_type": "healer", "name": "安娜",
				 "hp": 32, "max_hp": 32, "mp": 8, "mov": 3, "atk": 4, "def": 5, "matk": 14, "mdef": 12,
				 "attack_range": 1, "min_attack_range": 1, "skills": ["heal"], "color": "red", "player_id": 1,
				 "has_acted": false, "has_moved": false, "hero_id": "anna"}
			]},
			{"id": 2, "user_name": "kalde", "color": "blue", "is_ai": true, "is_alive": true,
			 "gold": 5000, "units": [
				{"id": 99, "x": 7, "y": 7, "unit_type": "knight", "name": "kalde",
				 "hp": 80, "max_hp": 80, "mp": 5, "mov": 4, "atk": 28, "def": 18, "matk": 0, "mdef": 12,
				 "attack_range": 1, "skills": ["heroic_strike"], "color": "blue", "player_id": 2,
				 "has_acted": false, "has_moved": false, "is_boss": true}
			]}
		]
	}


func _make_ally_units() -> Array:
	return [
		{"id": 10, "x": 3, "y": 11, "unit_type": "warlock", "name": "云",
		 "hp": 30, "max_hp": 30, "mp": 8, "mov": 4, "atk": 12, "def": 5, "matk": 22, "mdef": 12,
		 "attack_range": 1, "min_attack_range": 1, "skills": ["arcane_strike"], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 11, "x": 4, "y": 12, "unit_type": "healer", "name": "安娜",
		 "hp": 28, "max_hp": 28, "mp": 6, "mov": 3, "atk": 4, "def": 4, "matk": 12, "mdef": 10,
		 "attack_range": 1, "min_attack_range": 1, "skills": ["heal"], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 12, "x": 5, "y": 12, "unit_type": "archer", "name": "红",
		 "hp": 25, "max_hp": 25, "mp": 3, "mov": 3, "atk": 11, "def": 5, "matk": 0, "mdef": 0,
		 "attack_range": 2, "min_attack_range": 2, "skills": [], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 13, "x": 2, "y": 12, "unit_type": "archer", "name": "游骑",
		 "hp": 22, "max_hp": 22, "mp": 3, "mov": 3, "atk": 10, "def": 4, "matk": 0, "mdef": 0,
		 "attack_range": 2, "min_attack_range": 2, "skills": [], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 14, "x": 1, "y": 12, "unit_type": "knight", "name": "近卫",
		 "hp": 32, "max_hp": 32, "mp": 3, "mov": 3, "atk": 14, "def": 12, "matk": 0, "mdef": 0,
		 "attack_range": 1, "min_attack_range": 1, "skills": ["guard"], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 15, "x": 6, "y": 12, "unit_type": "healer", "name": "医师",
		 "hp": 18, "max_hp": 18, "mp": 5, "mov": 3, "atk": 3, "def": 3, "matk": 8, "mdef": 6,
		 "attack_range": 1, "min_attack_range": 1, "skills": ["heal"], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false},
		{"id": 16, "x": 7, "y": 12, "unit_type": "warlock", "name": "术士",
		 "hp": 22, "max_hp": 22, "mp": 7, "mov": 3, "atk": 8, "def": 4, "matk": 18, "mdef": 10,
		 "attack_range": 1, "min_attack_range": 1, "skills": ["fireball"], "color": "red", "player_id": 1,
		 "has_acted": false, "has_moved": false}
	]


func _make_enemy_base_units() -> Array:
	return [
		{"id": 20, "x": 14, "y": 2, "unit_type": "sniper", "name": "敌方狙击",
		 "hp": 22, "max_hp": 22, "mp": 3, "mov": 3, "atk": 12, "def": 5, "matk": 0, "mdef": 0,
		 "attack_range": 3, "min_attack_range": 2, "skills": [], "color": "blue", "player_id": 2,
		 "has_acted": false, "has_moved": false},
		{"id": 21, "x": 13, "y": 1, "unit_type": "warlock", "name": "敌方术士",
		 "hp": 22, "max_hp": 22, "mp": 6, "mov": 3, "atk": 6, "def": 4, "matk": 18, "mdef": 10,
		 "attack_range": 1, "min_attack_range": 1, "skills": [], "color": "blue", "player_id": 2,
		 "has_acted": false, "has_moved": false}
	]
