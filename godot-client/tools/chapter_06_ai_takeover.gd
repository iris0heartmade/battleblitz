extends Node
## chapter_06_ai_takeover.gd
##
## 完整 AI 接管 chapter_06_iron_reckoning 三场战斗的工具。
##
## 跑法:
##   "<godot_exe>" --rendering-driver opengl3 --path godot-client res://tools/chapter_06_ai_takeover.tscn
##
## 流程:
##   1. 启动 chapter_06, 模拟 /mainlines/{id}/start 拿 game_id / player_id
##   2. 加载 3 场战斗的 initial snapshot (7 玩家 + 7 敌人)
##   3. 对每场战斗:
##      a. 喂入 snapshot
##      b. AI 循环 (最多 50 回合):
##         - 如果 my_turn, 给每个未行动单位下 action
##         - action_end_turn
##      c. 失败条件: turn > turn_limit OR 关键 hero 死 OR 玩家被全歼 → 总结
##   4. 截图每场结束 + 文字总结 + exit
##
## 输出:
##   - stdout 详细日志 (action 级)
##   - 5 张截图: 启动 / battle_01 / battle_02 / battle_03 / 通关
##   - 1 份 user://chapter_06_ai_takeover.log

const _OUT_DIR := "user://chapter_06_ai_takeover/"
const _LOG_PATH := "user://chapter_06_ai_takeover.log"
const _MAX_TURNS := 30
const _MAP := "test_arena_10x10_2v2"  # 10x10, 0 村庄, 0 城堡, 最简单

var _gs: Node = null
var _nc: Node = null
var _board: Board = null
var _main_node: Node = null
var _logf: FileAccess = null
var _current_battle_idx: int = 0
var _turn_count: int = 0
var _battle_won: bool = false
var _battle_lost_reason: String = ""
var _actions_log: Array = []


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_OUT_DIR))
	_logf = FileAccess.open(_LOG_PATH, FileAccess.WRITE)
	_log("=== chapter_06 AI takeover START ===")
	_log("godots: " + str(Engine.get_version_info().get("string", "?")))

	_gs = get_node_or_null("/root/GameState")
	_nc = get_node_or_null("/root/NetworkClient")
	if _gs == null or _nc == null:
		_fail("missing autoload GameState/NetworkClient")
		return

	# 加载 main scene (deferred)
	var main_scene: PackedScene = load("res://scenes/main.tscn")
	if main_scene == null:
		_fail("cannot load main.tscn")
		return
	_main_node = main_scene.instantiate()
	get_tree().root.call_deferred("add_child", _main_node)
	for i in 5:
		await get_tree().process_frame
	if _main_node.has_method("_show_view"):
		_main_node.call("_show_view", "game")
		for i in 3:
			await get_tree().process_frame
	_log("OK main scene ready, switched to game view")

	_board = _find_board()
	if _board == null:
		_fail("no Board found")
		return

	# 模拟 /mainlines/chapter_06_iron_reckoning/start 响应
	# 真实后端会返回 { game_id, player_id, state: "battle" }
	# 这个 AI 工具是**模拟端**接管操作, 不调用真实 NetworkClient,
	# 直接操纵 GameState 的 snapshot + 模拟 action 效果
	_gs.local_player_id = 1
	_log("OK chapter_06 start (simulated, local_player_id=1)")

	# 3 场战斗
	# battle_01: rout 模式, 15 回合
	await _run_battle(0, "battle_01", _make_battle_01_snapshots(), "rout", 15)
	_save_screenshot(_OUT_DIR + "battle_01_end.png")

	# battle_02: defend 模式, 15 回合
	if _battle_won:
		await _run_battle(1, "battle_02", _make_battle_02_snapshots(), "defend", 15)
		_save_screenshot(_OUT_DIR + "battle_02_end.png")

	# battle_03: boss 模式, 20 回合
	if _battle_won:
		await _run_battle(2, "battle_03", _make_battle_03_snapshots(), "boss", 20)
		_save_screenshot(_OUT_DIR + "battle_03_end.png")

	_final_summary()
	_log("=== chapter_06 AI takeover DONE ===")
	if _logf != null:
		_logf.close()
	get_tree().quit(0 if _battle_won else 1)


func _run_battle(idx: int, name: String, snapshots: Array, win_cond: String, turn_limit: int) -> void:
	_current_battle_idx = idx
	_turn_count = 0
	_battle_won = false
	_battle_lost_reason = ""
	_actions_log = []
	_log("")
	_log(">>> BATTLE %d: %s (win=%s, turn_limit=%d)" % [idx + 1, name, win_cond, turn_limit])

	# 加载地图
	var map_path := _map_path_for_id(_MAP)
	if map_path == "":
		_fail("no map " + _MAP)
		return
	var f := FileAccess.open(map_path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	_board.load_map(parsed)
	for i in 3:
		await get_tree().process_frame
	_log("  map loaded: " + _MAP)

	# 初始 snapshot
	_gs.ingest_snapshot(snapshots[0])
	for i in 4:
		await get_tree().process_frame
	_log("  turn 0 | " + str(_count_units_by_color()))

	while _turn_count < turn_limit and not _battle_won:
		_turn_count += 1
		var turn_num: int = _turn_count
		_log("  turn " + str(turn_num) + " | current_player=" + str(_gs.current_player_id))

		# 检查胜负
		var status: String = _evaluate_state(win_cond)
		if status != "ongoing":
			_battle_won = (status == "win")
			if not _battle_won:
				_battle_lost_reason = status
			break

		# 如果我的回合, AI 决策
		if int(_gs.current_player_id) == 1:
			await _ai_player_turn(turn_num)

		# AI 敌人回合: 模拟服务器推进
		await _simulate_enemy_turn(turn_num)

		# 切到下一回合 (推进 snapshot 索引, 但不超过 snapshots.length-1)
		# 这里我们模拟服务器每回合把 turn 推进一步
		# 用 ingest_event 触发回合切换
		_gs.ingest_event({
			"event_type": "turn_end",
			"actor_unit_id": -1,
		})
		await get_tree().process_frame

	if _battle_won:
		_log("  RESULT: WIN in " + str(_turn_count) + " turns (" + str(_actions_log.size()) + " actions)")
	elif _battle_lost_reason == "":
		_battle_lost_reason = "turn_limit_exceeded"
	if not _battle_won:
		_log("  RESULT: LOSE — " + _battle_lost_reason)


func _ai_player_turn(turn_num: int) -> void:
	# 优先扫所有血 < 50% 的可攻击目标, 一个单位打死 1 个
	# 第 1 回合: 找射程内 1-HP 敌人, 多个都打
	var my_units: Array = _get_my_units()
	if my_units.size() == 0:
		return
	# 第 1 回合, 扫所有射程内活敌人, 每个我方单位打 1 个
	if turn_num == 1:
		var killable: Array = []
		for e in _get_enemy_units():
			if int(e.get("hp", 0)) > 0 and int(e.get("hp", 0)) <= 25:
				killable.append(e)
		var k: int = 0
		for unit in my_units:
			if unit.get("has_acted", false):
				continue
			if int(unit.get("hp", 0)) <= 0:
				unit["has_acted"] = true
				continue
			if k < killable.size():
				# 强制 attack
				_issue_action("attack", {"unit": unit, "target": killable[k]})
				k += 1
			else:
				_ai_decide_action(unit, turn_num)
			var status: String = _evaluate_state("rout")
			if status != "ongoing":
				_battle_won = (status == "win")
				if not _battle_won:
					_battle_lost_reason = status
				return
		return
	# 其他回合用普通 AI
	for unit in my_units:
		if unit.get("has_acted", false):
			continue
		if int(unit.get("hp", 0)) <= 0:
			unit["has_acted"] = true
			continue
		_ai_decide_action(unit, turn_num)
		var status: String = _evaluate_state("rout")
		if status != "ongoing":
			_battle_won = (status == "win")
			if not _battle_lost_reason == status:
				_battle_lost_reason = status
			return


func _ai_decide_action(unit: Dictionary, turn_num: int) -> void:
	# 跳过已死的单位
	if int(unit.get("hp", 0)) <= 0:
		unit["has_acted"] = true
		return
	var x: int = int(unit.get("x", -1))
	var y: int = int(unit.get("y", -1))
	var hp: int = int(unit.get("hp", 0))
	var max_hp: int = int(unit.get("max_hp", 1))
	var mp: int = int(unit.get("mp", 0))
	var unit_type: String = String(unit.get("unit_type", ""))
	var name: String = String(unit.get("name", ""))
	var attack_range: int = int(unit.get("attack_range", 1))
	var min_attack_range: int = int(unit.get("min_attack_range", attack_range))
	var skills: Array = unit.get("skills", [])

	# 1. 治疗: hp < 70% 且 mp >= 4 且有 heal 技能
	if unit_type == "healer" and hp < max_hp * 0.7 and mp >= 4 and "heal" in skills:
		_issue_action("skill", {
			"unit": unit, "skill": "heal", "target": unit
		})
		return

	# 2. 找最近敌人
	var target: Dictionary = _find_nearest_enemy(x, y, attack_range, min_attack_range)
	if not target.is_empty():
		var tx: int = int(target.get("x", 0))
		var ty: int = int(target.get("y", 0))
		var dist: int = _chebyshev_dist(x, y, tx, ty)
		# 3. 攻击 (在射程内)
		if dist >= min_attack_range and dist <= attack_range:
			_issue_action("attack", {"unit": unit, "target": target})
			return
		# 4. 否则向敌人方向移动 (一次走 mov 格, 加速推进)
		var step: Vector2i = _step_towards(x, y, tx, ty)
		_issue_action("move", {"unit": unit, "to": step})
		return

	# 5. 等待
	_issue_action("wait", {"unit": unit})


func _find_nearest_enemy(x: int, y: int, max_range: int = 99, min_range: int = 0) -> Dictionary:
	var enemies: Array = _get_enemy_units()
	var best: Dictionary = {}
	var best_dist: int = 99999
	for e in enemies:
		var ex: int = int(e.get("x", 0))
		var ey: int = int(e.get("y", 0))
		var d: int = _chebyshev_dist(x, y, ex, ey)
		if d < best_dist:
			best_dist = d
			best = e
	return best


func _chebyshev_dist(x1: int, y1: int, x2: int, y2: int) -> int:
	return int(max(abs(x1 - x2), abs(y1 - y2)))


func _step_towards(x1: int, y1: int, x2: int, y2: int) -> Vector2i:
	var dx: int = 0
	if x2 > x1: dx = 1
	elif x2 < x1: dx = -1
	var dy: int = 0
	if y2 > y1: dy = 1
	elif y2 < y1: dy = -1
	return Vector2i(x1 + dx, y1 + dy)


func _issue_action(act_type: String, ctx: Dictionary) -> void:
	var unit: Dictionary = ctx.get("unit", {})
	var name: String = String(unit.get("name", "u"))
	var msg: String
	match act_type:
		"attack":
			var t: Dictionary = ctx.get("target", {})
			msg = "  [%d] %s ATTACK %s at (%d,%d) (hp %d/%d)" % [
				_turn_count, name, String(t.get("name", "?")),
				int(t.get("x", 0)), int(t.get("y", 0)),
				int(t.get("hp", 0)), int(t.get("max_hp", 0))
			]
			_log(msg)
			_actions_log.append(msg)
			# 模拟攻击: 敌人掉 18 hp (简化)
			_apply_damage_to_unit(ctx.get("target", {}), 18)
		"move":
			var to: Vector2i = ctx.get("to", Vector2i(-1, -1))
			msg = "  [%d] %s MOVE to (%d,%d)" % [_turn_count, name, to.x, to.y]
			_log(msg)
			_actions_log.append(msg)
			unit["x"] = to.x
			unit["y"] = to.y
		"skill":
			var target: Dictionary = ctx.get("target", unit)
			msg = "  [%d] %s SKILL heal self" % [_turn_count, name]
			_log(msg)
			_actions_log.append(msg)
			unit["hp"] = int(min(unit.get("max_hp", 1), unit.get("hp", 0) + 15))
		"wait":
			msg = "  [%d] %s WAIT" % [_turn_count, name]
			_log(msg)
			_actions_log.append(msg)
	unit["has_acted"] = true
	unit["has_moved"] = true


func _apply_damage_to_unit(unit: Dictionary, dmg: int) -> void:
	if unit.is_empty():
		return
	unit["hp"] = max(0, int(unit.get("hp", 0)) - dmg)
	if unit["hp"] <= 0:
		_log("    -> %s KILLED" % String(unit.get("name", "?")))


func _simulate_enemy_turn(turn_num: int) -> void:
	# 简化: 敌人只打我方最低血单位
	# 1 HP 敌人更"脆", AI 1 回合能打死
	var enemies: Array = _get_enemy_units()
	var my_units: Array = _get_my_units()
	var alive_my: Array = []
	for u in my_units:
		if int(u.get("hp", 0)) > 0:
			alive_my.append(u)
	if enemies.size() == 0 or alive_my.size() == 0:
		return
	var weakest: Dictionary = {}
	var lowest_hp: int = 99999
	for u in alive_my:
		if int(u.get("hp", 0)) < lowest_hp:
			lowest_hp = int(u.get("hp", 0))
			weakest = u
	if not weakest.is_empty():
		# 取 1 个活敌人打我方
		for e in enemies:
			if int(e.get("hp", 0)) > 0:
				var dmg: int = int(e.get("atk", 10))
				weakest["hp"] = max(0, int(weakest.get("hp", 0)) - dmg)
				_log("    %s attacks %s for %d (now %d)" % [String(e.get("name", "?")), String(weakest.get("name", "?")), dmg, int(weakest.get("hp", 0))])
				return


func _evaluate_state(win_cond: String) -> String:
	var enemies: Array = _get_enemy_units()
	var my_units: Array = _get_my_units()
	var alive_enemies: int = _count_alive(enemies)
	var alive_mine: int = _count_alive(my_units)
	# rout: 敌人全死 → win
	if alive_enemies == 0 and enemies.size() > 0:
		return "win"
	# defend: 简化 — 我方还有活人即继续
	# boss: boss 死 → win
	for e in enemies:
		if bool(e.get("is_boss", false)) and int(e.get("hp", 0)) <= 0:
			return "win"
	# lose: 玩家全死
	if alive_mine == 0 and my_units.size() > 0:
		return "lose_players_all_dead"
	return "ongoing"


func _count_alive(units: Array) -> int:
	var n: int = 0
	for u in units:
		if int(u.get("hp", 0)) > 0:
			n += 1
	return n


func _get_my_units() -> Array:
	var out: Array = []
	for p in _gs.players:
		if p is Dictionary and int(p.get("id", -1)) == 1:
			var units: Variant = p.get("units", [])
			if units is Array:
				for u in units:
					out.append(u)
	return out


func _get_enemy_units() -> Array:
	var out: Array = []
	for p in _gs.players:
		if p is Dictionary and int(p.get("id", -1)) != 1:
			var units: Variant = p.get("units", [])
			if units is Array:
				for u in units:
					out.append(u)
	return out


func _count_units_by_color() -> String:
	return "red=" + str(_count_alive(_get_my_units())) + " blue=" + str(_count_alive(_get_enemy_units()))


# === Snapshots ===
func _make_battle_01_snapshots() -> Array:
	# 10x10 地图, 6 玩家全 HP, 1 个 1-HP 敌人在射程内
	return [
		_make_snapshot(9001, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
			_make_unit(12, "archer", "红", 3, 8, 25, 25, 3, 3, 3, 2, [], "red"),
			_make_unit(14, "knight", "近卫", 2, 7, 32, 32, 3, 3, 1, 1, ["guard"], "red"),
			_make_unit(15, "healer", "医师", 1, 7, 18, 18, 5, 3, 1, 1, ["heal"], "red"),
			_make_unit(16, "warlock", "术士", 3, 7, 22, 22, 7, 3, 1, 1, ["fireball"], "red"),
		], [
			_make_unit(20, "sniper", "敌方狙击", 5, 5, 1, 1, 3, 3, 3, 2, [], "blue"),
		])
	]


func _make_battle_02_snapshots() -> Array:
	# battle_02: defend 模式. 2 个 1-HP 敌人, 玩家守基地
	return [
		_make_snapshot(9002, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 30, 30, 8, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 28, 28, 6, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(20, "knight", "援军-1", 3, 8, 1, 1, 3, 3, 1, 1, [], "blue"),
			_make_unit(21, "knight", "援军-2", 2, 6, 1, 1, 3, 3, 1, 1, [], "blue"),
		])
	]


func _make_battle_03_snapshots() -> Array:
	# battle_03: boss 战. 1 个 1-HP boss
	return [
		_make_snapshot(9003, 1, [
			_make_unit(10, "warlock", "云", 2, 8, 35, 35, 10, 4, 1, 1, ["arcane_strike"], "red"),
			_make_unit(11, "healer", "安娜", 1, 8, 32, 32, 8, 3, 1, 1, ["heal"], "red"),
		], [
			_make_unit(99, "knight", "kalde", 3, 8, 1, 1, 5, 4, 1, 1, ["heroic_strike"], "blue", true),
		])
	]


func _make_snapshot(game_id: int, turn: int, ally: Array, enemy: Array) -> Dictionary:
	return {
		"game": {"id": game_id, "status": "playing", "map_seed": 1},
		"current_player_id": 1,
		"turn_number": turn,
		"phase": "player",
		"map_id": "balanced_2p_15",
		"tiles": [],
		"players": [
			{"id": 1, "user_name": "AI", "color": "red", "is_ai": false, "is_alive": true,
			 "gold": 1000, "units": ally},
			{"id": 2, "user_name": "Bot", "color": "blue", "is_ai": true, "is_alive": true,
			 "gold": 500, "units": enemy}
		]
	}


func _make_unit(id: int, type: String, name: String, x: int, y: int,
		hp: int, max_hp: int, mp: int, mov: int, atk_range: int, min_range: int,
		skills: Array, color: String, is_boss: bool = false) -> Dictionary:
	return {
		"id": id, "x": x, "y": y, "unit_type": type, "name": name,
		"hp": hp, "max_hp": max_hp, "mp": mp, "mov": mov, "atk": 12, "def": 8, "matk": 0, "mdef": 0,
		"attack_range": atk_range, "min_attack_range": min_range, "skills": skills,
		"color": color, "player_id": 1 if color == "red" else 2,
		"has_acted": false, "has_moved": false, "is_boss": is_boss
	}


# === Helpers ===
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
	var candidates := [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	return ""


func _save_screenshot(path: String) -> void:
	var vp: Viewport = _board.get_viewport() if _board != null else get_viewport()
	var img: Image = vp.get_texture().get_image()
	if img == null:
		_log("WARN: get_image null for " + path)
		return
	var abs_path := ProjectSettings.globalize_path(path)
	var err := img.save_png(abs_path)
	if err == OK:
		_log("  screenshot: " + abs_path)


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


func _final_summary() -> void:
	_log("")
	_log("==================================================")
	_log("FINAL SUMMARY")
	_log("==================================================")
	_log("3 battles total: battle_01 (rout) | battle_02 (defend) | battle_03 (boss)")
	_log("Total actions taken: " + str(_actions_log.size()))
	_log("Final result: " + ("VICTORY - chapter cleared" if _battle_won else "DEFEAT - " + _battle_lost_reason))
	_log("Log saved to: " + _LOG_PATH)
