extends Node
## 正式正交3D相机：旋转、俯角、缩放界限、平移与菜单隔离。
var passed := 0
var failed := 0

func _ready() -> void:
	var board: Node = load("res://scenes/board.tscn").instantiate()
	add_child(board)
	var rows: Array[String] = []
	for _y in 15:
		rows.append("P".repeat(15))
	board.load_map({"size":{"width":15,"height":15},"layout":rows})
	var cam: Camera3D = board.board_camera
	check(cam.projection==Camera3D.PROJECTION_ORTHOGONAL,"正式相机正交投影")
	var start: float = cam.yaw
	for _i in 9:
		cam.turn(45)
	await get_tree().create_timer(1).timeout
	check(is_equal_approx(cam.yaw,start+405),"连续转向跨越360度")
	cam.orbit_drag(Vector2(1,10000))
	check(cam.pitch==60.0,"俯角上限")
	cam.orbit_drag(Vector2(1,-10000))
	check(cam.pitch==20.0,"俯角下限")
	cam.zoom(0.00001)
	check(cam.size==float(cam.defaults.camera_min_size),"近景缩放界限")
	cam.zoom(100000)
	check(cam.size==float(cam.defaults.camera_max_size),"远景缩放界限")
	var focus: Vector3 = cam.focus
	cam.pan(Vector2(100,50))
	check(cam.focus!=focus and cam.target_focus==cam.focus,"拖动平移无回弹")
	check(get_viewport().canvas_transform==Transform2D.IDENTITY,"不改变2D菜单坐标")
	cam.reset_view()
	check(cam.yaw==45.0 and cam.pitch==30.0,"重置朝向")
	print("[orbit-camera] passed=%d failed=%d"%[passed,failed])
	get_tree().quit(1 if failed else 0)

func check(ok: bool,label: String) -> void:
	if ok:
		passed += 1
	else:
		failed += 1
		push_error(label)
