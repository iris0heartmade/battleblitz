extends Node2D

const UNIT_NODE_SCRIPT := preload("res://scripts/board/unit_node.gd")
const OUT_PATH := "res://screenshots/yuanying_board_sprite_check.png"


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://screenshots"))
	_setup_canvas()
	await _await_draws(4)
	var img := get_viewport().get_texture().get_image()
	if img == null:
		printerr("[yuanying_sprite] viewport image unavailable")
		get_tree().quit(1)
		return
	var err := img.save_png(OUT_PATH)
	if err != OK:
		printerr("[yuanying_sprite] save failed: %s" % error_string(err))
		get_tree().quit(1)
		return
	print("[yuanying_sprite] saved: %s (%dx%d)" % [OUT_PATH, img.get_width(), img.get_height()])
	get_tree().quit(0)


func _setup_canvas() -> void:
	var bg := ColorRect.new()
	bg.size = Vector2(360, 150)
	bg.color = Color(0.09, 0.11, 0.13)
	add_child(bg)

	_add_sample(Vector2(74, 70), {
		"id": 101,
		"unit_type": "warlock",
		"hp": 35,
		"max_hp": 45,
		"mp": 5,
		"max_mp": 5,
		"morale": 2,
		"has_acted": false,
	})
	_add_sample(Vector2(178, 70), {
		"id": 102,
		"unit_type": "warlock",
		"hero_id": "yuanying",
		"hp": 48,
		"max_hp": 48,
		"mp": 5,
		"max_mp": 5,
		"morale": 3,
		"has_acted": false,
	})
	_add_sample(Vector2(282, 70), {
		"id": 103,
		"unit_type": "warlock",
		"hero_id": "yuanying",
		"hp": 21,
		"max_hp": 48,
		"mp": 3,
		"max_mp": 5,
		"morale": 1,
		"has_acted": true,
		"status_effects": [
			{"type": "silence", "remaining_turns": 1, "glyph": "S"},
			{"type": "poison", "remaining_turns": 2, "glyph": "P"},
		],
	})


func _add_sample(center: Vector2, data: Dictionary) -> void:
	var tile := ColorRect.new()
	tile.size = Vector2(48, 48)
	tile.position = center - tile.size * 0.5
	tile.color = Color(0.25, 0.32, 0.29)
	add_child(tile)

	var unit = UNIT_NODE_SCRIPT.new()
	unit.position = center
	unit.setup(data, Color(0.88, 0.19, 0.18), "team_a")
	add_child(unit)


func _await_draws(count: int) -> void:
	for i in count:
		await get_tree().process_frame
