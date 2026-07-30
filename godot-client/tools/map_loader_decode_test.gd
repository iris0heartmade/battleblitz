extends Node


func _ready() -> void:
	var failed := 0
	var board := preload("res://scenes/board.tscn").instantiate()
	add_child(board)
	board.load_map({
		"size": {"width": 3, "height": 2},
		"biome": "grass",
		"layout": [
			"PbP",
			"PPP",
		],
		"initial_units": [],
	})
	var decoded: Dictionary = board.tile_lookup.get(Vector2i(1, 0), {})
	if String(decoded.get("terrain", "")) != "barracks":
		print("FAIL b should decode as barracks, got %s" % str(decoded))
		failed += 1
	if failed > 0:
		get_tree().quit(1)
	else:
		print("PASS map loader decodes barracks")
		get_tree().quit(0)
