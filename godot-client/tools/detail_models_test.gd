extends SceneTree
## 在正式棋盘上检查实体细节和相机环绕，保存真实GPU截图。
var board: Node
var checks: Dictionary = {}

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	board = load("res://scenes/board.tscn").instantiate()
	board.preview_mode = true
	root.add_child(board)
	board.load_map({"size":{"width":8,"height":8},"layout":["PPPPPPPP","PPPPPPPP","PPPPPPPP","PPPPPPPP","PPPPPPPP","PPPPPPPP","PPPPPPPP","PPPPPPPP"]})
	for y in 8:
		for x in 8:
			var p := Vector2i(x,y)
			board.model.cell(p).terrain = ["grass","rock","sand","water"][int(x/4)+int(y/4)*2]
	board.model.cell(Vector2i(2,2)).feature = "village"
	board.model.cell(Vector2i(1,2)).feature = "forest"
	board.terrain.rebuild()
	await process_frame
	await physics_frame
	var layer: Node3D = board.terrain.contents.details
	checks.no_billboards = layer.find_children("*","Sprite3D",true,false).is_empty()
	checks.no_collision = layer.find_children("*","CollisionObject3D",true,false).is_empty()
	checks.buildings_clear = true
	var kinds: Dictionary = {}
	var snapshot: Array = []
	for child in layer.get_children():
		var p: Vector2i = child.get_meta("cell")
		kinds[board.model.cell(p).terrain] = true
		checks.buildings_clear = checks.buildings_clear and String(board.model.cell(p).feature).is_empty()
		snapshot.append([child.position,child.get_child_count()])
	checks.four_terrains = kinds.size()==4
	checks.real_meshes = layer.find_children("*","MeshInstance3D",true,false).size()>50
	var original_count := layer.get_child_count()
	board.terrain.rebuild()
	var rebuilt: Array = []
	for child in layer.get_children():
		rebuilt.append([child.position,child.get_child_count()])
	checks.stable_rebuild = snapshot==rebuilt and layer.get_child_count()==original_count
	board.board_camera.size = 7.5
	board.board_camera.focus_on(Vector3(3.5,0,3.5))
	for angle in [45,135,225,315]:
		board.board_camera.turn(float(angle)-board.board_camera.yaw,false)
		await process_frame
		await physics_frame
		if DisplayServer.get_name()!="headless":
			RenderingServer.force_draw(true)
			var target := OS.get_environment("BB_DETAIL_SCREENSHOT")
			if not target.is_empty():
				checks["capture_"+str(angle)] = root.get_texture().get_image().save_png(target+"-"+str(angle)+".png")==OK
	print("DETAIL_MODEL_RESULT="+JSON.stringify(checks))
	board.queue_free()
	await process_frame
	quit(0 if checks.values().all(func(ok): return ok) else 1)

