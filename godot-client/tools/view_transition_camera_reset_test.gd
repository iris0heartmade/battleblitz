extends Node
## 高差地图切换视图回归：独立3D视口不应污染菜单或继续后台绘制。
var passed := 0
var failed := 0

func _ready() -> void:
	NetworkClient._req_busy = true
	var main: Node = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await get_tree().process_frame
	for view in ["game","menu","editor","lobby","saves","mainline"]:
		main._show_view(view)
		await get_tree().process_frame
		var board: Node = main.board
		board.board_camera.pan(Vector2(120,50))
		board.board_camera.zoom(0.8)
		board.board_camera.turn(45)
		check(get_viewport().canvas_transform==Transform2D.IDENTITY,view+"：相机不改变2D画布")
		check(board.surface.is_visible_in_tree()==(view=="game"),view+"：战场显隐一致")
		check((board.stage.render_target_update_mode==SubViewport.UPDATE_ALWAYS)==(view=="game"),view+"：隐藏战场停止渲染")
	main._show_view("game")
	main._on_battle_back_menu_pressed()
	await get_tree().process_frame
	check(not main.board.surface.is_visible_in_tree(),"结算返回菜单隐藏3D舞台")
	print("[view-transition] passed=%d failed=%d"%[passed,failed])
	get_tree().quit(1 if failed else 0)

func check(ok: bool,label: String) -> void:
	if ok:
		passed += 1
	else:
		failed += 1
		push_error(label)
