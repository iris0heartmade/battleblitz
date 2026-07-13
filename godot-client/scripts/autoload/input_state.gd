extends Node
## InputState — autoload tracking the user's current interaction mode.
##
## Mirrors the transient `state.selectedUnit / actionMode / path / ...`
## from the JS frontend. Lives in an autoload so the InputState survives
## scene changes (board ↔ menu) without re-derivation.
##
## M1 leaves most fields at their defaults — the Board scene just
## displays the map. M2 wires `set_mode` to the click handlers.

signal mode_changed(new_mode: int)
signal selected_unit_changed(unit_id: Variant)
signal hover_tile_changed(tile: Vector2i)

# Interaction modes — see `app.js` `onCellClick` for the JS equivalents.
enum Mode {
	IDLE,        # nothing selected, hover shows info only
	UNIT_SELECTED,  # a friendly unit is selected; show reach + path on hover
	MOVE_MODE,      # user is choosing a destination tile
	ATTACK_MODE,    # user is choosing a target
	CLAIM_MODE,     # user is targeting a claimable tile
	RECRUIT_MODE,   # user is targeting an empty barracks
	SKILL_MODE,     # user is choosing a skill target
}

var mode: int = Mode.IDLE:
	set(value):
		if mode == value:
			return
		mode = value
		mode_changed.emit(value)

var selected_unit_id: Variant = null:           # int | null
	set(value):
		selected_unit_id = value
		selected_unit_changed.emit(value)

var hover_tile: Vector2i = Vector2i(-1, -1):
	set(value):
		hover_tile = value
		hover_tile_changed.emit(value)

# Cached reachable tiles + best path for the currently selected unit.
# M2 will populate these via MapLogic.compute_reachable + pathfind.
var reachable_tiles: Array = []                 # Array[Vector2i]
var current_path: Array = []                    # Array[Vector2i]
