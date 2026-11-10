extends SceneTree
## 替代旧2D源码字符串断言：在真正的正式棋盘上检查动画、归属与队伍。
var result: Dictionary = {}

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var gs := root.get_node("GameState")
	gs.players = [{"id":1,"color":"green","team":"team_a","units":[]}]
	var board: Node = load("res://scenes/board.tscn").instantiate()
	root.add_child(board)
	var u := {"id":1,"player_id":1,"x":1,"y":1,"unit_type":"swordsman","hp":30,"max_hp":30,"level":2,"status_effects":[{"type":"poison"}]}
	board.load_map({"size":{"width":4,"height":4},"layout":["CvPP","PPPP","PPPP","PPPP"],"initial_units":[u]})
	board.preview_unit_move(1,Vector2i(2,1),0.4)
	await create_timer(0.08).timeout
	var before: Vector3 = board._unit_nodes_by_id[1].position
	var old_tween: Tween = board._move_tweens[1]
	u.x = 2
	board._on_units_changed([u])
	var after: Vector3 = board._unit_nodes_by_id[1].position
	var retained: bool = before.distance_to(after)<0.001 and not old_tween.is_running()
	await create_timer(0.35).timeout
	result.movement = retained and board._unit_nodes_by_id[1].position.distance_to(board.model.surface(Vector2i(2,1)))<0.001
	var tiles := [{"x":0,"y":0,"terrain":"castle","owner_id":1},{"x":1,"y":0,"terrain":"village","owner_id":null}]
	gs.pending_claims = [{"tile_x":1,"tile_y":0,"target_player_id":1,"turns_remaining":2,"total_turns":3}]
	board.rebuild_flags(tiles)
	var castle_flag: Node = board.terrain.contents.features.get_child(0).get_node("OwnerFlag")
	var neutral_flag: Node = board.terrain.contents.features.get_child(1).get_node("OwnerFlag")
	result.claims = board.flag_layer.get_child_count()==1 and board.flag_layer.get_child(0).text=="占领 2/3" and board.model.cell(Vector2i(1,0)).faction=="neutral"
	result.flags = castle_flag.get_meta("color")==Color("66ba89") and neutral_flag.get_meta("color")==Color("e2ddd2")
	var anchor: Node3D = board._unit_nodes_by_id[1]
	var team: Label3D = anchor.get_node("TeamBadge")
	result.teams = team.text=="A" and team.modulate==Color("d75b5a") and anchor.unit_data.color=="green"
	result.status = anchor.get_node("UnitBadge").text.contains("毒")
	# 旧快照的null子类型与新高度均必须完整落到格顶。
	board.load_map({"width":2,"height":1,"layout":["PP"],"tiles":[{"x":0,"y":0,"terrain":"plain","subtype":null,"elevation":-5},{"x":1,"y":0,"terrain":"mountain","subtype":null,"elevation":5}]})
	result.heights = board.model.surface(Vector2i(0,0)).y==-2.5 and board.model.surface(Vector2i(1,0)).y==2.5
	print("CONTRACT_RESULT="+JSON.stringify(result))
	quit(0 if result.values().all(func(ok): return ok) else 1)
