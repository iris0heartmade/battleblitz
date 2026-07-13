extends Node
## main.gd — entry point. Wires up the Board scene, picks a default
## map JSON, and forwards click events into the InputState autoload.
##
## M1 just loads the first map it finds under `res://../game/maps/*.json`
## and renders it. M2 will add a "new game / join game" lobby before
## the board is instantiated.

@onready var board: Board = $Board
@onready var status_label: Label = $UI/StatusLabel

const DEFAULT_MAP_ID := "balanced_2p_15"

# Maps we expose for M1 testing — the menu lets the user cycle through
# them to verify biome + variant handling visually.
const DEMO_MAPS := [
	"balanced_2p_15",
	"balanced_3p_15",
	"balanced_4p_20",
	"realistic_grass_2p_20",
	"realistic_desert_2p_25",
	"realistic_snow_2p_20",
]


func _ready() -> void:
	# Resolve the map JSON from the Python repo (outside the Godot
	# project root). The path is absolute because the maps live in
	# `game/maps/*.json` and we don't want to duplicate them.
	var map_path := _map_path_for_id(DEFAULT_MAP_ID)
	if map_path == "":
		status_label.text = "Cannot find any demo map."
		return
	var result := board.load_map_json_file(map_path)
	if result.is_empty():
		status_label.text = "Failed to load %s" % map_path
		return
	_update_status(result)


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	if event.pressed:
		return  # ignore button-up
	var tile: Vector2i = board.viewport_to_tile(event.position)
	if tile.x < 0 or tile.y < 0:
		return
	InputState.hover_tile = tile
	if event.button_index == MOUSE_BUTTON_LEFT:
		board.highlights.show_hover(tile)
	elif event.button_index == MOUSE_BUTTON_RIGHT:
		# Right-click clears the hover indicator for now; M2 will
		# trigger a "cancel current action" signal.
		board.highlights.clear()


func _update_status(result: Dictionary) -> void:
	var w: int = int(result.get("width", 0))
	var h: int = int(result.get("height", 0))
	var biome: String = String(result.get("biome", "?"))
	var units: int = (result.get("initial_units", []) as Array).size()
	status_label.text = "Map: %dx%d  biome=%s  initial_units=%d  (right-click to clear)" % [w, h, biome, units]


# ============================================================
# Map discovery (outside the Godot project root)
# ============================================================

func _map_path_for_id(map_id: String) -> String:
	# `res://` only resolves to the project root. The map JSONs live
	# one level up in `game/maps/`. We try a few candidates so the
	# project works whether launched from the editor, from the
	# exported binary, or via headless test.
	var candidates := [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	# Fall back to absolute path computed from the executable.
	var exe_dir := OS.get_executable_path().get_base_dir()
	var guesses := [
		"%s/../../game/maps/%s.json" % [exe_dir, map_id],
		"%s/../../../game/maps/%s.json" % [exe_dir, map_id],
	]
	for g in guesses:
		if FileAccess.file_exists(g):
			return g
	push_warning("main.gd: no map file found for id '%s'" % map_id)
	return ""
