class_name MapLogic
extends RefCounted
## MapLogic — client-side mirror of `game/app/utils.py` (BFS / pathfind
## / line-of-sight). Used purely for UI previews: move-range highlight,
## path preview, damage prediction. The server remains the authority;
## the client never rejects actions on these results.
##
## M2 implementation — mirrors utils.py semantics 1:1, including the
## ×2 integer encoding (road=1 = half-MP). All return types are
## GDScript idioms:
##   * coords  : Vector2i (server uses (x,y) tuples)
##   * cost    : int in half-MP units
##   * paths   : Array[Vector2i]
##   * owners  : Dictionary[Vector2i -> int]   (Tile.owner_id)


# ============================================================
# Geometry primitives
# ============================================================

static func in_bounds(x: int, y: int, size: int) -> bool:
	return x >= 0 and x < size and y >= 0 and y < size


static func manhattan(a: Vector2i, b: Vector2i) -> int:
	return abs(a.x - b.x) + abs(a.y - b.y)


## 4-neighbour orthogonal moves (Manhattan adjacency — no diagonals).
## Mirrors `utils.neighbors` exactly.
static func neighbors(pos: Vector2i) -> Array:
	return [
		Vector2i(pos.x - 1, pos.y),
		Vector2i(pos.x + 1, pos.y),
		Vector2i(pos.x, pos.y - 1),
		Vector2i(pos.x, pos.y + 1),
	]


# ============================================================
# Passability
# ============================================================

## Mirrors `utils.terrain_passable` (server `can_end_on_terrain`).
## Note the explicit blacklist of `castle_wall` / `gate` (impassable for
## everyone).
##
## M4.16+ fix:REMOVED the `castle` ownership check that used to prevent
## units from stepping on enemy HQ tiles. The server intentionally allows
## stepping onto enemy castles (comment in actions.py:222 — "Enemy HQs
## are valid movement targets. Claiming the HQ remains an explicit
## two-turn action after the unit arrives."). Without this fix the unit
## could never reach the enemy HQ to start a claim session, so the seize
## win condition was unreachable in the Godot client.
static func terrain_passable(terrain: String, owner_id: int, viewer_owner_id: int) -> bool:
	# `owner_id` / `viewer_owner_id` are intentionally unused — see comment
	# above. Server uses `DEFAULT_MOVEMENT_PROFILE` (no rules) so any
	# terrain with a finite move cost is endable.
	var _owner_unused: int = owner_id
	var _viewer_unused: int = viewer_owner_id
	if terrain == "castle_wall" or terrain == "gate":
		return false
	return Config.TERRAIN_MOVE_COST.has(terrain)


# ============================================================
# Line of sight
# ============================================================

## Mirrors `utils.has_line_of_sight`. `blocked` is a Dictionary keyed
## by Vector2i; truthy entries block LOS (mountain/forest/river).
## Castle tiles do NOT block (units in castles must stay targetable).
static func has_line_of_sight(a: Vector2i, b: Vector2i, blocked: Dictionary, size: int) -> bool:
	if a == b:
		return true
	# No diagonal shots in this engine (Fire-Emblem / Advance-Wars style).
	if a.x != b.x and a.y != b.y:
		return false
	var step_x: int = 0 if a.x == b.x else (1 if b.x > a.x else -1)
	var step_y: int = 0 if a.y == b.y else (1 if b.y > a.y else -1)
	var cx: int = a.x + step_x
	var cy: int = a.y + step_y
	while cx != b.x or cy != b.y:
		if not in_bounds(cx, cy, size):
			return false
		if blocked.has(Vector2i(cx, cy)) and blocked[Vector2i(cx, cy)]:
			return false
		cx += step_x
		cy += step_y
	return in_bounds(b.x, b.y, size)


# ============================================================
# BFS reachable set
# ============================================================

## Mirrors `utils.bfs_reachable` 1:1. Returns Dictionary[Vector2i -> int]
## of tiles reachable within `mov` MP, where each value is the *half-MP*
## cost consumed (road=1 → cost 1, plain=2 → cost 2, etc.). Callers that
## want MP-equivalent should divide by 2.
##
## `terrain` and `owners` are Dictionary[Vector2i -> String/int] built
## from the latest GameState snapshot.
## `blocked_units`: fully blocks traversal and ending, used for enemies.
## `no_end_units`: can be traversed but cannot be used as a destination,
## used for allies.
static func compute_reachable(
	start: Vector2i,
	terrain: Dictionary,
	owners: Dictionary,
	mov: int,
	viewer_owner_id: int,
	blocked_units: Dictionary = {},
	no_end_units: Dictionary = {},
	size: int = 0,
) -> Dictionary:
	if size <= 0:
		size = _infer_size(terrain)
	if not terrain.has(start):
		return {}
	var budget: int = mov * 2
	var dist: Dictionary = {start: 0}
	var reachable: Dictionary = {start: 0}
	var queue: Array = [start]
	var qi: int = 0
	while qi < queue.size():
		var cur_pos: Vector2i = queue[qi]
		qi += 1
		var cur_cost: int = dist[cur_pos]
		if cur_cost >= budget:
			continue
		for n in neighbors(cur_pos):
			if not in_bounds(n.x, n.y, size):
				continue
			if not terrain.has(n):
				continue
			var t: String = terrain[n]
			var owner: int = int(owners.get(n, -1))
			if not terrain_passable(t, owner, viewer_owner_id):
				continue
			if blocked_units.has(n) and not n == start:
				continue
			var step_cost: int = int(Config.TERRAIN_MOVE_COST.get(t, 9999))
			var new_cost: int = cur_cost + step_cost
			if new_cost > budget:
				continue
			if not dist.has(n) or new_cost < dist[n]:
				dist[n] = new_cost
				queue.append(n)
				if not no_end_units.has(n):
					reachable[n] = new_cost
	return reachable


# ============================================================
# Dijkstra pathfind
# ============================================================

## Mirrors `utils.pathfind` — Dijkstra over integer costs. Returns
## the cheapest path (Array[Vector2i]) from start to goal, or `[]` if
## unreachable within `mov` MP. The path always includes both start
## and goal. Internal budget is `mov * 2` (half-MP) for the same
## reason `compute_reachable` uses one.
static func pathfind(
	start: Vector2i,
	goal: Vector2i,
	terrain: Dictionary,
	owners: Dictionary,
	mov: int,
	viewer_owner_id: int,
	blocked_units: Dictionary = {},
	no_end_units: Dictionary = {},
	size: int = 0,
) -> Array:
	if start == goal:
		return [start]
	if size <= 0:
		size = _infer_size(terrain)
	# Allow standing on own tile even if `blocked_units` includes it.
	var blocked := blocked_units.duplicate()
	blocked.erase(start)
	var no_end := no_end_units.duplicate()
	no_end.erase(start)
	var budget: int = mov * 2

	# A tiny binary-heap substitute (avoids pulling in stdlib heapq).
	# Each entry: [cost, tiebreak_counter, coord].
	# We hand-roll a sorted insert for clarity — grid is small (≤ 45² = 2025).
	var pq: Array = []  # of Array
	var counter: int = 0
	var came_from: Dictionary = {}
	var best: Dictionary = {start: 0}
	pq.append([0, counter, start])
	counter += 1

	while not pq.is_empty():
		# Pop the cheapest entry (linear scan — fine for small grids).
		var best_idx: int = 0
		for i in range(1, pq.size()):
			if pq[i][0] < pq[best_idx][0]:
				best_idx = i
		var entry: Array = pq[best_idx]
		pq.remove_at(best_idx)
		var cost: int = entry[0]
		var node: Vector2i = entry[2]
		if cost > best.get(node, 99999999):
			continue
		# Accept goal only if cost within budget (P2.5 fix: prevents
		# `pathfind` returning teleporting paths when cost > mov).
		if node == goal and cost <= budget and not no_end.has(node):
			var path: Array = [goal]
			while came_from.has(path[-1]):
				path.append(came_from[path[-1]])
			path.reverse()
			return path
		if cost >= budget:
			continue  # no MP left to expand
		for n in neighbors(node):
			if not in_bounds(n.x, n.y, size):
				continue
			if not terrain.has(n):
				continue
			var t: String = terrain[n]
			var owner: int = int(owners.get(n, -1))
			if not terrain_passable(t, owner, viewer_owner_id):
				continue
			if blocked.has(n):
				continue
			var step_cost: int = int(Config.TERRAIN_MOVE_COST.get(t, 9999))
			var new_cost: int = cost + step_cost
			if new_cost > budget:
				continue
			if new_cost < best.get(n, 99999999):
				best[n] = new_cost
				came_from[n] = node
				pq.append([new_cost, counter, n])
				counter += 1
	return []  # unreachable


# ============================================================
# Highlight helpers
# ============================================================

## Given a reachable-set from `compute_reachable`, filter down to the
## "highlight as move" tiles (everything except the unit's own start).
## Returns Array[Vector2i] for the Highlights layer to iterate.
static func reachable_for_highlight(reachable: Dictionary) -> Array:
	var out: Array = []
	for c in reachable.keys():
		if int(reachable[c]) > 0:
			out.append(c)
	return out


## Given an attacker's position, an attack range, and a min range,
## returns the set of tiles a unit can attack (in MANHATTAN distance).
## Range 0 = only own tile. Range 1 = orthogonal neighbours. Range 2
## includes Chebyshev-diagonal tiles 2 steps out (matches Fire-Emblem
## ranged attack: archer 2 = orthogonal 2 OR diagonal 2). The server
## uses Manhattan, so we keep Manhattan here for parity.
static func attack_range_tiles(attacker_pos: Vector2i, attack_range: int, min_range: int, size: int) -> Array:
	var out: Array = []
	for y in size:
		for x in size:
			var p := Vector2i(x, y)
			var d: int = manhattan(attacker_pos, p)
			if d > min_range and d <= attack_range:
				out.append(p)
	return out


# ============================================================
# Internal
# ============================================================

static func _infer_size(terrain: Dictionary) -> int:
	# Square grid assumed (matches BattleBlitz's spec). Walk a few
	# entries to find the max coord.
	var max_coord: int = 0
	for k in terrain.keys():
		if k is Vector2i:
			max_coord = max(max_coord, max(k.x, k.y))
	return max_coord + 1
