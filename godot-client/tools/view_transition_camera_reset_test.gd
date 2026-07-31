extends Node
## 回归测试:_show_view / 战报回主菜单 路径修复后,viewport.canvas_transform 必须为 IDENTITY,
## 所有 Camera2D 必须 disabled,zoom/position 必须回中性。
## 不依赖网络 / FastAPI — 完全本地 headless 跑。

const MAIN_SCENE := preload("res://scenes/main.tscn")

var _passed: int = 0
var _failed: int = 0


func _ready() -> void:
	print("=== BattleBlitz view-transition camera reset test ===")
	# headless 跑 — 在 main scene 实例化之前就把 NetworkClient 的 HTTP 队列锁死,
	# 否则 main._ready() 里的 _check_resume_session → list_games 会一直挂到超时。
	if DisplayServer.get_name() == "headless":
		_disable_network()
		_run_headless()


func _disable_network() -> void:
	var nc: Node = get_node_or_null("/root/NetworkClient")
	if nc == null:
		return
	# _req_busy 常驻 true → _drain_queue 看一眼就 return → request 入队但不真发。
	# autoload NetworkClient 的 `_req_busy` 是普通 var,可直接赋值。
	nc.set("_req_busy", true)


func _run_headless() -> void:
	var main: Node = MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	await get_tree().process_frame

	# 模拟"game → menu"切换来验证 reset 是否生效。
	main._show_view("menu")
	await get_tree().process_frame
	_assert_camera_reset(main, "After _show_view('menu') from initial state")

	# 模拟相机已经在 game view 下被应用了 zoom+position+smoothing,
	# 然后切到 menu,看 camera 是否真的被重置。
	var board: Node = main.get_node_or_null("GameView/Board")
	var camera: Camera2D = board.get_node_or_null("BoardCamera") as Camera2D
	if camera == null:
		_fail("BoardCamera missing")
		return
	camera.position = Vector2(240.0, -180.0)
	camera.zoom = Vector2(1.45, 1.45)
	camera.position_smoothing_enabled = true
	camera.enabled = true
	main._show_view("menu")
	await get_tree().process_frame
	await get_tree().process_frame
	_assert_camera_reset(main, "After stale-camera _show_view('menu')")

	# 验证 viewport.canvas_transform = IDENTITY(任何非单位都是 P2 修复未生效)
	var vp: Viewport = main.get_viewport()
	var ct: Transform2D = vp.canvas_transform
	_assert_transform_identity("viewport.canvas_transform", ct,
		"非 game/editor view 必须 canvas_transform = IDENTITY")

	# 测战报 → 主菜单的完整清理路径
	main._show_view("game")
	await get_tree().process_frame
	camera.position = Vector2(120.0, 60.0)
	camera.zoom = Vector2(1.7, 1.7)
	camera.enabled = true
	# 模拟玩家在主菜单点 BackMenuBtn
	main._on_battle_back_menu_pressed()
	await get_tree().process_frame
	await get_tree().process_frame
	_assert_camera_reset(main, "After _on_battle_back_menu_pressed")

	# 测 _post_frame_viewport_reset 帧末兜底是否生效:模拟 callback 把 camera 又设回去
	main._show_view("game")
	await get_tree().process_frame
	camera.position = Vector2(50.0, 50.0)
	camera.zoom = Vector2(2.0, 2.0)
	camera.enabled = true
	main._show_view("menu")
	# 同一帧内:模拟 state_updated callback / tween 把 camera 又设回去。
	# 必须在 await 之前,否则 deferred 已经跑过,不构成同帧竞争。
	camera.enabled = true
	camera.position = Vector2(99.0, 88.0)
	camera.zoom = Vector2(2.5, 2.5)
	camera.position_smoothing_enabled = true
	# 等帧末 call_deferred 兜底 reset 跑完(自愈 8 次兜底)
	for _i in range(8):
		await get_tree().process_frame
	_assert_camera_reset(main, "After _post_frame_viewport_reset deferred catch")

	print("---")
	print("Passed: %d   Failed: %d" % [_passed, _failed])
	if _failed > 0:
		print("FAIL")
		get_tree().quit(1)
	else:
		print("PASS")
		get_tree().quit(0)


func _assert_camera_reset(main: Node, label: String) -> void:
	var board: Node = main.get_node_or_null("GameView/Board")
	var cam: Camera2D = board.get_node_or_null("BoardCamera") as Camera2D
	_assert_eq("[%s] BoardCamera.enabled" % label, cam.enabled, false,
		"切到非 game/editor view 之后,BoardCamera 必须 disabled")
	_assert_eq("[%s] BoardCamera.zoom" % label, cam.zoom, Vector2(1.0, 1.0),
		"BoardCamera.zoom 必须被重置为 (1,1)")
	_assert_eq("[%s] BoardCamera.position" % label, cam.position, Vector2.ZERO,
		"BoardCamera.position 必须被重置为 (0,0)")
	_assert_eq("[%s] BoardCamera.position_smoothing_enabled" % label,
		cam.position_smoothing_enabled, false,
		"BoardCamera smoothing 必须被关闭")
	var vp: Viewport = main.get_viewport()
	_assert_transform_identity("[%s] viewport.canvas_transform" % label,
		vp.canvas_transform, "viewport.canvas_transform 必须 = IDENTITY")


func _assert_eq(label: String, got, expected, msg: String) -> void:
	if got == expected:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s - %s" % [label, str(got), str(expected), msg])


func _assert_transform_identity(label: String, got: Transform2D, msg: String) -> void:
	if got == Transform2D.IDENTITY:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected IDENTITY - %s" % [label, str(got), msg])


func _fail(msg: String) -> void:
	_failed += 1
	print("  FAIL  %s" % msg)
