extends Node

const MAIN_SCENE := preload("res://scenes/main.tscn")
const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")
const FEEDBACK_LIMIT_MS := 500

var _failed: int = 0
var _passed: int = 0


func _ready() -> void:
	print("=== BattleBlitz action latency test ===")
	await get_tree().process_frame

	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	_seed_game(main)
	await get_tree().process_frame

	await _test_move_feedback_is_immediate(main)
	await _test_path_preview_steps_through_cells(main)
	await _test_path_preview_expands_non_adjacent_points(main)
	await _test_move_feedback_consumes_path(main)
	await _test_unknown_hp_hides_health_bar()
	await _test_attack_feedback_is_immediate(main)

	print("---")
	print("Passed: %d   Failed: %d" % [_passed, _failed])
	if _failed > 0:
		print("FAIL")
		get_tree().quit(1)
	else:
		print("PASS")
		get_tree().quit(0)


func _seed_game(main: Node) -> void:
	var tiles: Array = []
	for y in range(5):
		for x in range(5):
			tiles.append({"x": x, "y": y, "terrain": "plain", "owner_id": null})
	var units := [
		{
			"id": 101,
			"player_id": 1,
			"unit_type": "swordsman",
			"name": "Tester",
			"x": 1,
			"y": 1,
			"hp": 30,
			"max_hp": 30,
			"mp": 5,
			"mov": 5,
			"attack_range": 1,
			"min_attack_range": 0,
			"skills": [],
			"has_acted": false,
			"has_moved": false,
		},
		{
			"id": 202,
			"player_id": 2,
			"unit_type": "swordsman",
			"name": "Target",
			"x": 2,
			"y": 1,
			"hp": 30,
			"max_hp": 30,
			"mp": 5,
			"mov": 5,
			"attack_range": 1,
			"min_attack_range": 0,
			"skills": [],
			"has_acted": false,
			"has_moved": false,
		},
	]
	GameState.local_player_id = 1
	GameState.ingest_snapshot({
		"game": {"id": 9001, "status": "playing", "phase": "player"},
		"current_player_id": 1,
		"tiles": tiles,
		"players": [
			{"id": 1, "color": "red", "team": "team_a", "gold": 500, "units": [units[0]]},
			{"id": 2, "color": "blue", "team": "team_b", "gold": 500, "units": [units[1]]},
		],
	})
	main.set("_game_id", 9001)
	main.set("_player_id", 1)
	main.call("_show_view", "game")
	var board: Node = main.get_node("GameView/Board")
	board.call("load_map", {
		"size": {"width": 5, "height": 5},
		"biome": "grass",
		"layout": [
			"PPPPP",
			"PPPPP",
			"PPPPP",
			"PPPPP",
			"PPPPP",
		],
		"initial_units": units,
	})


func _test_move_feedback_is_immediate(main: Node) -> void:
	var board: Node = main.get_node("GameView/Board")
	_assert_true("Board exposes preview_unit_move", board.has_method("preview_unit_move"),
		"Board must expose a local visual move preview")
	_assert_true("Main exposes immediate move feedback", main.has_method("_apply_immediate_move_feedback"),
		"main.gd must expose immediate movement feedback")
	if not board.has_method("preview_unit_move") or not main.has_method("_apply_immediate_move_feedback"):
		return
	var unit := _unit_node(board, 101)
	if unit == null:
		_fail("cannot find unit node #101")
		return
	var start_pos: Vector2 = unit.position
	var started_at := Time.get_ticks_msec()
	main.call("_apply_immediate_move_feedback", 101, Vector2i(3, 1))
	await get_tree().process_frame
	var elapsed := Time.get_ticks_msec() - started_at
	_assert_lte("Move feedback starts under 500ms", elapsed, FEEDBACK_LIMIT_MS,
		"move command should start visual feedback without waiting for server round-trip")
	_assert_true("Move preview changes unit position", unit.position != start_pos,
		"unit presenter should begin moving during the immediate feedback window")
	await get_tree().create_timer(0.35).timeout
	var metrics = board.get("metrics")
	var expected_pos: Vector2 = metrics.cell_to_local(Vector2i(3, 1)) if metrics != null else unit.position
	_assert_vec2_close("Move preview completes under 500ms", unit.position, expected_pos, 0.01,
		"unit presenter should arrive at the target cell before the 500ms hand-feel budget")


func _test_path_preview_steps_through_cells(main: Node) -> void:
	var board: Node = main.get_node("GameView/Board")
	_assert_true("Board exposes preview_unit_path", board.has_method("preview_unit_path"),
		"Board must expose path-based local visual move preview")
	if not board.has_method("preview_unit_path"):
		return
	var unit := _unit_node(board, 101)
	if unit == null:
		_fail("cannot find unit node #101 for path preview")
		return
	board.call("preview_unit_path", 101, [
		Vector2i(1, 1),
		Vector2i(1, 2),
		Vector2i(2, 2),
		Vector2i(3, 2),
	], 0.45)
	await get_tree().create_timer(0.16).timeout
	var metrics = board.get("metrics")
	var target_pos: Vector2 = metrics.cell_to_local(Vector2i(3, 2)) if metrics != null else unit.position
	_assert_true("Path preview does not jump directly to destination", unit.position.distance_to(target_pos) > 8.0,
		"path preview should visibly traverse intermediate cells before reaching the destination")
	await get_tree().create_timer(0.40).timeout
	_assert_vec2_close("Path preview finishes at destination", unit.position, target_pos, 1.0,
		"path preview should finish on the final cell")


func _test_path_preview_expands_non_adjacent_points(main: Node) -> void:
	var board: Node = main.get_node("GameView/Board")
	var unit := _unit_node(board, 101)
	if unit == null:
		_fail("cannot find unit node #101 for orthogonal path preview")
		return
	var metrics = board.get("metrics")
	unit.position = metrics.cell_to_local(Vector2i(1, 1))
	board.call("preview_unit_path", 101, [
		Vector2i(1, 1),
		Vector2i(3, 2),
	], 0.45)
	await get_tree().create_timer(0.12).timeout
	var first_orthogonal: Vector2 = metrics.cell_to_local(Vector2i(2, 1))
	var direct_midpoint: Vector2 = metrics.cell_to_local(Vector2i(1, 1)).lerp(metrics.cell_to_local(Vector2i(3, 2)), 0.5)
	_assert_true("Path preview expands non-adjacent points into grid steps",
		unit.position.distance_to(first_orthogonal) < unit.position.distance_to(direct_midpoint),
		"non-adjacent path input should be expanded into orthogonal tile centers, not tweened diagonally")
	await get_tree().create_timer(0.45).timeout
	_assert_vec2_close("Expanded path finishes at destination", unit.position, metrics.cell_to_local(Vector2i(3, 2)), 1.0,
		"expanded orthogonal path should finish on the final cell")


func _test_move_feedback_consumes_path(main: Node) -> void:
	_assert_true("Immediate move feedback accepts path argument",
		_method_arg_count(main, "_apply_immediate_move_feedback") >= 3,
		"main.gd move feedback should accept an optional path array")
	if _method_arg_count(main, "_apply_immediate_move_feedback") < 3:
		return
	var board: Node = main.get_node("GameView/Board")
	var unit := _unit_node(board, 101)
	if unit == null:
		_fail("cannot find unit node #101 for move feedback path")
		return
	main.call("_apply_immediate_move_feedback", 101, Vector2i(4, 2), [
		Vector2i(3, 2),
		Vector2i(3, 3),
		Vector2i(4, 3),
		Vector2i(4, 2),
	])
	await get_tree().create_timer(0.16).timeout
	var optimistic_unit: Dictionary = GameState.get_unit(101)
	_assert_true("Immediate move updates local unit position",
		int(optimistic_unit.get("x", -1)) == 4 and int(optimistic_unit.get("y", -1)) == 2,
		"client should allow the next command UI to reason from the predicted destination before server confirmation")
	_assert_true("Immediate move marks unit moved locally",
		bool(optimistic_unit.get("has_moved", false)),
		"client should mark the unit moved locally so the action bubble switches to post-move commands")
	var bubble: Control = main.get_node("GameView/HUD/ActionBubble")
	_assert_true("Immediate move shows post-move action bubble", bubble.visible,
		"post-move commands should be available immediately instead of waiting for the move event")
	var metrics = board.get("metrics")
	var target_pos: Vector2 = metrics.cell_to_local(Vector2i(4, 2)) if metrics != null else unit.position
	_assert_true("Immediate move feedback consumes path", unit.position.distance_to(target_pos) > 8.0,
		"move feedback should use the supplied path instead of tweening directly to the destination")
	await get_tree().create_timer(0.40).timeout
	_assert_vec2_close("Immediate path feedback finishes at destination", unit.position, target_pos, 1.0,
		"move feedback path should finish on the final cell")


func _test_unknown_hp_hides_health_bar() -> void:
	var unit = UNIT_NODE_SCRIPT.new()
	add_child(unit)
	unit.setup({
		"id": 303,
		"player_id": 1,
		"unit_type": "swordsman",
		"x": 0,
		"y": 0,
		"hp": -1,
		"max_hp": -1,
	}, Color(1, 0, 0), null)
	await get_tree().process_frame
	_assert_true("Unknown HP hides health bar", not _has_visible_health_bar(unit),
		"temporary or partial unit data should not render an empty health bar ghost")
	unit.queue_free()


func _test_attack_feedback_is_immediate(main: Node) -> void:
	_assert_true("Main exposes immediate attack feedback", main.has_method("_apply_immediate_attack_feedback"),
		"main.gd must expose immediate attack feedback")
	if not main.has_method("_apply_immediate_attack_feedback"):
		return
	var board: Node = main.get_node("GameView/Board")
	var effects: Node = board.get_node("EffectsLayer")
	var before_count := effects.get_child_count()
	var started_at := Time.get_ticks_msec()
	main.call("_apply_immediate_attack_feedback", 101, 202)
	await get_tree().process_frame
	var elapsed := Time.get_ticks_msec() - started_at
	_assert_lte("Attack feedback starts under 500ms", elapsed, FEEDBACK_LIMIT_MS,
		"attack command should show local feedback without waiting for damage resolution")
	_assert_true("Attack preview spawns feedback", effects.get_child_count() > before_count,
		"attack feedback should create an immediate visual marker on the board")


func _unit_node(board: Node, unit_id: int) -> Node2D:
	var units_layer: Node = board.get_node("UnitLayer")
	for child in units_layer.get_children():
		var data: Dictionary = child.get("unit_data") if child != null else {}
		if int(data.get("id", -1)) == unit_id:
			return child as Node2D
	return null


func _method_arg_count(obj: Object, method_name: String) -> int:
	for method in obj.get_method_list():
		if str(method.get("name", "")) == method_name:
			return (method.get("args", []) as Array).size()
	return -1


func _has_visible_health_bar(unit: Node) -> bool:
	for child in unit.get_children():
		if child is ColorRect and child.visible:
			var rect := child as ColorRect
			if rect.position.y >= 24.0 and rect.size.y <= 5.0:
				return true
	return false


func _assert_true(label: String, cond: bool, msg: String) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: %s" % [label, msg])


func _assert_lte(label: String, got: int, maximum: int, msg: String) -> void:
	if got <= maximum:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %d > %d - %s" % [label, got, maximum, msg])


func _assert_vec2_close(label: String, got: Vector2, expected: Vector2, tolerance: float, msg: String) -> void:
	if got.distance_to(expected) <= tolerance:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s - %s" % [label, str(got), str(expected), msg])


func _fail(msg: String) -> void:
	_failed += 1
	print("  FAIL  %s" % msg)
