extends Node


func _ready() -> void:
	var failed := 0
	var terrain := {}
	var owners := {}
	for x in range(4):
		var cell := Vector2i(x, 0)
		terrain[cell] = "plain"
		owners[cell] = 0
	var start := Vector2i(0, 0)
	var ally := Vector2i(1, 0)
	var beyond_ally := Vector2i(2, 0)
	var blocked := {}
	var no_end := {ally: true}

	var reachable: Dictionary = MapLogic.compute_reachable(
		start, terrain, owners, 2, 1, blocked, no_end, 4
	)
	if reachable.has(ally):
		print("FAIL ally tile should not be endable")
		failed += 1
	if not reachable.has(beyond_ally):
		print("FAIL tile beyond ally should be reachable through ally")
		failed += 1

	var path: Array = MapLogic.pathfind(
		start, beyond_ally, terrain, owners, 2, 1, blocked, no_end, 4
	)
	if path != [start, ally, beyond_ally]:
		print("FAIL path should traverse ally: %s" % str(path))
		failed += 1

	var ally_goal: Array = MapLogic.pathfind(
		start, ally, terrain, owners, 2, 1, blocked, no_end, 4
	)
	if not ally_goal.is_empty():
		print("FAIL ally tile should not be a valid goal: %s" % str(ally_goal))
		failed += 1

	var enemy_blocked := {ally: true}
	var enemy_reachable: Dictionary = MapLogic.compute_reachable(
		start, terrain, owners, 2, 1, enemy_blocked, {}, 4
	)
	if enemy_reachable.has(ally) or enemy_reachable.has(beyond_ally):
		print("FAIL enemy tile should fully block movement")
		failed += 1

	if failed > 0:
		get_tree().quit(1)
	else:
		print("PASS map logic movement occupancy")
		get_tree().quit(0)
