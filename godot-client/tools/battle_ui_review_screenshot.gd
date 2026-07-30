extends Node
## Deterministic battle HUD screenshot. It does not require the FastAPI server.

const OUT_DIR := "res://.refactor_shots/"


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))
	await _frames(6)
	var main := get_node("Main")
	main._game_id = 1
	main._player_id = 1
	main._show_view("game")
	var map_path := "res://../game/maps/balanced_2p_15.json"
	if not FileAccess.file_exists(map_path):
		printerr("[battle-ui-review] map not found: %s" % map_path)
		get_tree().quit(1)
		return
	var file := FileAccess.open(map_path, FileAccess.READ)
	var map_data: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	if not (map_data is Dictionary):
		printerr("[battle-ui-review] invalid map json")
		get_tree().quit(1)
		return
	main.board.load_map(map_data)
	var hero := {
		"id": 901, "hero_id": "yun", "name": "云", "unit_type": "warlock",
		"level": 1, "hp": 53, "max_hp": 53, "mp": 4, "max_mp": 8,
		"mov": 4, "atk": 20, "def_": 11, "matk": 29, "mdef": 13,
		"attack_range": 2, "min_attack_range": 0, "morale": 2,
		"x": 2, "y": 8, "player_id": 1, "color": "red",
		"skills": ["arcane_blast"], "has_acted": false, "has_moved": false,
	}
	var red_units: Array = [hero]
	var blue_units: Array = []
	var next_id := 902
	for placed_v in map_data.get("initial_units", []):
		var placed: Dictionary = placed_v
		if int(placed.get("x", -1)) == 2 and int(placed.get("y", -1)) == 8 and str(placed.get("color", "")) == "red":
			continue
		var mock_unit := {
			"id": next_id, "name": str(placed.get("type", "unit")),
			"unit_type": str(placed.get("type", "swordsman")),
			"level": int(placed.get("level", 1)), "hp": 45, "max_hp": 45,
			"mp": 5, "max_mp": 5, "mov": 5, "atk": 12, "def_": 8,
			"matk": 4, "mdef": 5, "attack_range": 1, "min_attack_range": 0,
			"morale": 0, "x": int(placed.get("x", 0)), "y": int(placed.get("y", 0)),
			"player_id": 1 if str(placed.get("color", "red")) == "red" else 2,
			"color": str(placed.get("color", "red")), "skills": [],
			"has_acted": false, "has_moved": false,
		}
		next_id += 1
		if mock_unit.color == "red":
			red_units.append(mock_unit)
		else:
			blue_units.append(mock_unit)
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
	main._handle_unit_click(901, Vector2.ZERO)
	await _frames(8)
	var image := get_viewport().get_texture().get_image()
	var size := image.get_size()
	var filename := "battle_ui_review_%dx%d.png" % [size.x, size.y]
	image.save_png(OUT_DIR + filename)
	print("[battle-ui-review] saved %s" % filename)
	get_tree().quit(0)


func _frames(count: int) -> void:
	for _i in count:
		await get_tree().process_frame
		RenderingServer.force_draw()
