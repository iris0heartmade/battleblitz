extends Node

const MAIN_SCENE := preload("res://scenes/main.tscn")
const MAP_PATH := "res://../game/maps/balanced_2p_15.json"

var _failed: int = 0
var _passed: int = 0


func _ready() -> void:
	print("=== BattleBlitz view position reset test ===")
	await get_tree().process_frame

	var main := MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame

	await _test_board_camera_resets_for_new_map(main)
	await _test_lobby_bottom_bar_restores_to_bottom_right(main)

	print("---")
	print("Passed: %d   Failed: %d" % [_passed, _failed])
	if _failed > 0:
		print("FAIL")
		get_tree().quit(1)
	else:
		print("PASS")
		get_tree().quit(0)


func _test_board_camera_resets_for_new_map(main: Node) -> void:
	var board: Node = main.get_node_or_null("GameView/Board")
	if board == null:
		_fail("GameView/Board missing")
		return

	var map_json := _load_map_json()
	if map_json.is_empty():
		_fail("test map missing or invalid")
		return

	board.call("load_map", map_json)
	await get_tree().process_frame

	var camera: Camera2D = board.get_node_or_null("BoardCamera") as Camera2D
	if camera == null:
		_fail("BoardCamera missing")
		return

	var fit_position := camera.position
	var fit_zoom := camera.zoom
	camera.position = fit_position + Vector2(240.0, -180.0)
	camera.zoom = fit_zoom * 1.45
	if camera.has_method("mark_user_positioned"):
		camera.call("mark_user_positioned")

	board.call("load_map", map_json)
	await get_tree().process_frame

	_assert_vec2_close(
		"BoardCamera new map position reset",
		camera.position,
		fit_position,
		0.01,
		"new map loads must not inherit the previous battle pan"
	)
	_assert_vec2_close(
		"BoardCamera new map zoom reset",
		camera.zoom,
		fit_zoom,
		0.001,
		"new map loads must not inherit the previous battle zoom"
	)


func _test_lobby_bottom_bar_restores_to_bottom_right(main: Node) -> void:
	var bottom_bar: Control = main.get_node_or_null("Lobby/LobbyFrame/BottomBar") as Control
	if bottom_bar == null:
		_fail("Lobby BottomBar missing")
		return

	main.call("_show_view", "lobby")
	await get_tree().process_frame
	main.call("_layout_lobby_in_room")
	await get_tree().process_frame
	main.call("_show_lobby_choose")
	await get_tree().process_frame

	_assert_eq("Lobby BottomBar anchor_left", bottom_bar.anchor_left, 1.0,
		"choose/create/join lobby pages should restore the bottom bar to right-bottom anchoring")
	_assert_eq("Lobby BottomBar anchor_right", bottom_bar.anchor_right, 1.0,
		"choose/create/join lobby pages should restore the bottom bar to right-bottom anchoring")
	_assert_eq("Lobby BottomBar anchor_top", bottom_bar.anchor_top, 1.0,
		"choose/create/join lobby pages should restore the bottom bar to right-bottom anchoring")
	_assert_eq("Lobby BottomBar anchor_bottom", bottom_bar.anchor_bottom, 1.0,
		"choose/create/join lobby pages should restore the bottom bar to right-bottom anchoring")


func _load_map_json() -> Dictionary:
	var candidates := [
		MAP_PATH,
		"res://../../game/maps/balanced_2p_15.json",
		"res://game/maps/balanced_2p_15.json",
	]
	for path in candidates:
		if not FileAccess.file_exists(path):
			continue
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			continue
		var parsed: Variant = JSON.parse_string(file.get_as_text())
		file.close()
		if parsed is Dictionary:
			return parsed
	return {}


func _assert_vec2_close(label: String, got: Vector2, expected: Vector2, tolerance: float, msg: String) -> void:
	if got.distance_to(expected) <= tolerance:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s - %s" % [label, str(got), str(expected), msg])


func _assert_eq(label: String, got, expected, msg: String) -> void:
	if got == expected:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s - %s" % [label, str(got), str(expected), msg])


func _fail(msg: String) -> void:
	_failed += 1
	print("  FAIL  %s" % msg)
