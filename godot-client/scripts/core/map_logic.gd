class_name MapLogic
extends RefCounted
## MapLogic — client-side mirror of `game/app/utils.py` (BFS / pathfind
## / line-of-sight). Used purely for UI previews: move-range highlight,
## path preview, damage prediction. The server remains the authority;
## the client never rejects actions on these results.
##
## M0/M1 ships the data shape + a passable-tile check. M2 will add
## `compute_reachable`, `pathfind`, `has_line_of_sight`, and a damage
## preview helper.

# BFS result struct (GDScript Dictionary, since we don't have
## packed structs in 4.x without `class_name`d RefCounted).
##   {
##     "reachable": Array[Vector2i],   # all tiles the unit can reach
##     "parents":   Dictionary,        # Vector2i -> Vector2i parent
##   }
## The MapLoader / Board calls `find_path(parents, from, to)` to
## extract a single shortest path for the cursor preview.

## Pure passability check, no side effects. Mirrors the cost < 9999
## test in `utils.py` plus the explicit castle_wall / gate blacklist.
static func is_passable(terrain: String) -> bool:
	return Config.is_passable(terrain)

## Movement cost between two adjacent tiles in ×2 integer encoding.
## Diagonal moves are not supported by the server (orthogonal grid).
static func move_cost(terrain: String) -> int:
	return int(Config.TERRAIN_MOVE_COST.get(terrain, 9999))

## Returns true iff `from -> to` is a legal cardinal neighbour step.
static func is_neighbor(from_pos: Vector2i, to_pos: Vector2i) -> bool:
	var d: Vector2i = to_pos - from_pos
	return (abs(d.x) + abs(d.y)) == 1

## Stub: full BFS reachable-set computation. M2 will implement.
## Kept as a placeholder so the Board can already request a no-op.
static func compute_reachable(grid: Dictionary, start: Vector2i, mov_budget_cost: int) -> Dictionary:
	return {"reachable": [start], "parents": {}}

## Stub: greedy best-first path extraction. M2 will use AStarGrid2D
## (or a hand-rolled BFS parent walk) once reachable is implemented.
static func find_path(parents: Dictionary, from_pos: Vector2i, to_pos: Vector2i) -> Array:
	if from_pos == to_pos:
		return [from_pos]
	return [from_pos, to_pos]

## Stub: line-of-sight. M2 will mirror `utils.has_line_of_sight` and
## honour the terrain block list (forest/mountain/river/castle_wall).
static func has_line_of_sight(grid: Dictionary, from_pos: Vector2i, to_pos: Vector2i) -> bool:
	return true
