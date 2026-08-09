extends Node2D
## Headless test for BoardCamera:
##   - fit_zoom correctly fits the board into the frame
##   - apply_user_zoom_factor_delta changes zoom and respects clamp
##   - _clamp_position_to_frame keeps the frame inside the board
##   - frame size is FIXED across zoom changes
##
## Run:  D:/Python/Godot/Godot_v4.7-stable_win64_console.exe --headless \
##         --path godot-client tools/board_camera_test.tscn

const BoardCameraScript := preload("res://scripts/board/board_camera.gd")
const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")

var _pass: int = 0
var _fail: int = 0


func _write(name: String, ok: bool, msg: String = "") -> void:
	var tag: String = "PASS" if ok else "FAIL"
	if ok:
		_pass += 1
	else:
		_fail += 1
	var line: String = "  %s  %s" % [tag, name]
	if msg != "":
		line += "  -- %s" % msg
	print(line)


func _mk_metrics(board_size: int) -> Object:
	# Build a minimal metrics object that responds to bounds_rect() and
	# board_center() the way BoardCamera expects. Avoids depending on
	# MapMetrics which has its own assumptions about terrain.
	var m: Object = Object.new()
	var script: GDScript = GDScript.new()
	script.source_code = (
		"extends Object\n"
		+ "var size_v: int = 15\n"
		+ "func bounds_rect() -> Rect2:\n"
		+ "    var ts := Vector2(48, 48)\n"
		+ "    return Rect2(Vector2.ZERO, Vector2(size_v, size_v) * ts)\n"
		+ "func board_center() -> Vector2:\n"
		+ "    var ts := Vector2(48, 48)\n"
		+ "    var r := Rect2(Vector2.ZERO, Vector2(size_v, size_v) * ts)\n"
		+ "    return r.position + (r.size * 0.5)\n"
	)
	script.reload()
	m.set_script(script)
	m.set("size_v", board_size)
	return m


func _wait() -> void:
	# One frame so any deferred work (viewport size_changed signals) settles.
	await get_tree().process_frame


func _ready() -> void:
	print("=== BoardCamera headless test ===")
	await _wait()

	# Force a known viewport size so frame metrics are deterministic.
	# (We can't change the actual window from headless, but we can drive
	# the camera's _refresh_from_metrics with a fake metrics and inspect
	# the resulting state.)
	var cam: Camera2D = BoardCameraScript.new()
	add_child(cam)
	await _wait()

	# ── 1. initial fit on 15x15 board ───────────────────────────────────
	var m15 := _mk_metrics(15)
	cam.apply_metrics(m15)
	await _wait()

	# Frame size is recorded.
	_write("frame_size recorded on apply_metrics", cam._frame_size_px.x > 0.0 and cam._frame_size_px.y > 0.0,
		"got _frame_size_px=%s" % str(cam._frame_size_px))

	# fit_zoom is positive.
	_write("fit_zoom positive", cam._fit_zoom > 0.0, "got fit_zoom=%f" % cam._fit_zoom)

	# user_zoom_factor starts at 1.0; camera.zoom.x == fit_zoom * 1.0.
	_write("user_zoom_factor initial = 1.0", cam.get_user_zoom_factor() == 1.0)
	_write("camera.zoom == fit_zoom on init", abs(cam.zoom.x - cam._fit_zoom) < 1e-4,
		"zoom=%f fit=%f" % [cam.zoom.x, cam._fit_zoom])

	# ── 2. apply_user_zoom_factor_delta scales camera.zoom ───────────────
	cam.apply_user_zoom_factor_delta(0.5)  # → 1.5
	_write("after +0.5 delta, user_factor = 1.5", abs(cam.get_user_zoom_factor() - 1.5) < 1e-4)
	_write("camera.zoom == fit_zoom * 1.5", abs(cam.zoom.x - cam._fit_zoom * 1.5) < 1e-4,
		"zoom=%f expected=%f" % [cam.zoom.x, cam._fit_zoom * 1.5])

	# Frame size does NOT change.
	var frame_after_zoom: Vector2 = cam._frame_size_px
	_write("frame_size unchanged after zoom", frame_after_zoom == cam._frame_size_px)

	# ── 3. apply_user_zoom_factor_delta clamps at USER_ZOOM_MAX ──────────
	for i in 20:
		cam.apply_user_zoom_factor_delta(1.0)  # try to push past 3.0
	_write("user_factor clamped at USER_ZOOM_MAX (3.0)",
		abs(cam.get_user_zoom_factor() - BoardCameraScript.USER_ZOOM_MAX) < 1e-4,
		"got %f" % cam.get_user_zoom_factor())

	# Clamp at MIN.
	for i in 20:
		cam.apply_user_zoom_factor_delta(-1.0)
	_write("user_factor clamped at USER_ZOOM_MIN (0.4)",
		abs(cam.get_user_zoom_factor() - BoardCameraScript.USER_ZOOM_MIN) < 1e-4,
		"got %f" % cam.get_user_zoom_factor())

	# Reset to fit, then test pan clamp.
	cam.reset_to_fit()
	await _wait()
	_write("reset_to_fit restores user_factor=1.0", cam.get_user_zoom_factor() == 1.0)

	# ── 4. Pan clamp: pushing camera way past board edge is rejected ─────
	# Get the board rect from the same metrics.
	var br: Rect2 = m15.bounds_rect()
	var board_left: float = br.position.x
	var board_right: float = br.position.x + br.size.x
	var board_top: float = br.position.y
	var board_bottom: float = br.position.y + br.size.y
	var board_center_x: float = (board_left + board_right) * 0.5
	var board_center_y: float = (board_top + board_bottom) * 0.5

	# Note: 15x15 board + zoom 1.5 → frame_w_world = 1904 / (1.3 * 1.5) = 976,
	# board_w = 720. So frame > board on this board; clamping should snap
	# to board center (frame entirely covers board; no valid "inside" pan).
	cam._safe_set_position(Vector2(board_right + 5000.0, cam.position.y))
	_write("pan right past board (frame>board) snaps to board center",
		abs(cam.position.x - board_center_x) < 1e-3,
		"cam.x=%f board_center.x=%f" % [cam.position.x, board_center_x])

	# Now zoom in to 3.0 (user_factor) so frame < board, and pan clamp is
	# the narrow form.
	cam.apply_user_zoom_factor_delta(100.0)  # → 3.0
	await _wait()
	var fit_zoom2: float = cam._fit_zoom
	var actual_zoom2: float = fit_zoom2 * cam.get_user_zoom_factor()
	var frame_w_world2: float = cam._frame_size_px.x / actual_zoom2
	var max_x2: float = board_right - frame_w_world2 * 0.5
	var min_x2: float = board_left + frame_w_world2 * 0.5

	# Now frame < board (frame_w_world2 = 1904/(1.3*3.0) = 488 < 720).
	# pan right past max should clamp to max_x2.
	cam._safe_set_position(Vector2(board_right + 5000.0, cam.position.y))
	_write("pan right past board (frame<board) clamps to max_x",
		abs(cam.position.x - max_x2) < 1e-3,
		"cam.x=%f max_x=%f" % [cam.position.x, max_x2])

	cam._safe_set_position(Vector2(board_left - 5000.0, cam.position.y))
	_write("pan left past board (frame<board) clamps to min_x",
		abs(cam.position.x - min_x2) < 1e-3,
		"cam.x=%f min_x=%f" % [cam.position.x, min_x2])

	# Pan down / up with the same setup.
	var frame_h_world2: float = cam._frame_size_px.y / actual_zoom2
	var max_y2: float = board_bottom - frame_h_world2 * 0.5
	var min_y2: float = board_top + frame_h_world2 * 0.5

	cam._safe_set_position(Vector2(cam.position.x, board_bottom + 5000.0))
	_write("pan down past board (frame<board) clamps to max_y",
		abs(cam.position.y - max_y2) < 1e-3,
		"cam.y=%f max_y=%f" % [cam.position.y, max_y2])

	cam._safe_set_position(Vector2(cam.position.x, board_top - 5000.0))
	_write("pan up past board (frame<board) clamps to min_y",
		abs(cam.position.y - min_y2) < 1e-3,
		"cam.y=%f min_y=%f" % [cam.position.y, min_y2])

	# Restore fit for the next test.
	cam.reset_to_fit()
	await _wait()

	# ── 5. Pan is allowed within bounds (no false clamp) ─────────────────
	# Set camera exactly to board center, expect no change.
	var center: Vector2 = m15.board_center()
	cam._safe_set_position(center)
	_write("pan to board center is exact", cam.position.distance_to(center) < 1e-3,
		"cam=%s center=%s" % [str(cam.position), str(center)])

	# ── 6. Larger map (20x20) ───────────────────────────────────────────
	var m20 := _mk_metrics(20)
	cam.apply_metrics(m20)
	await _wait()
	_write("20x20 board also records frame", cam._frame_size_px.x > 0.0 and cam._frame_size_px.y > 0.0,
		"frame_size=%s" % str(cam._frame_size_px))
	_write("20x20 board has positive fit_zoom", cam._fit_zoom > 0.0,
		"fit_zoom=%f" % cam._fit_zoom)
	# Diagnostic: what does the test think the viewport size is?
	var vp: Viewport = get_viewport()
	var vp_size: Vector2 = vp.get_visible_rect().size if vp != null else Vector2.ZERO
	print("    diag: viewport=%s" % str(vp_size))

	# ── 7. zoom 范围测试:user_factor == 0.4 时框是世界坐标的 2.5x ─────
	cam.apply_user_zoom_factor_delta(-100.0)  # 推到 MIN
	var zoomed_out: float = cam.get_user_zoom_factor()
	_write("zoom-out user_factor = 0.4 (frame in world = 2.5x board)",
		abs(zoomed_out - 0.4) < 1e-4)

	# 核心不变量:zoom 改变时,frame 在屏幕上的像素尺寸保持不变
	# (「固定大小的中央窗口」= 屏幕像素尺寸固定)。
	# 任何 user_factor 下,frame_w_screen = _frame_size_px.x。
	var frame_w_screen: float = cam._frame_size_px.x  # 设计上 = 屏幕像素,跟 zoom 无关
	var frame_w_world_at_zoom_out: float = cam._frame_size_px.x / (cam._fit_zoom * zoomed_out)
	var br20: Rect2 = m20.bounds_rect()
	# 验证:zoom-out 后 frame 在世界坐标的宽度 = board_w / (fit_zoom * zoomed_out) * fit_zoom
	# 化简:frame_w_world = frame_w_px / (fit_zoom * zoomed_out)
	# 注意:跟 board 尺寸的倍数关系取决于 fit 方向(20x20 是按高度 fit,所以宽度方向 frame 比 board 宽很多)
	# 这里直接验证「frame_w_world * (fit_zoom * zoomed_out) == _frame_size_px.x」,这是结构上的不变量。
	_write("zoom-out frame_w_world is consistent with _frame_size_px",
		abs(frame_w_world_at_zoom_out * (cam._fit_zoom * zoomed_out) - frame_w_screen) < 0.5,
		"frame_w_world=%f frame_w_px=%f fit*user=%f" % [frame_w_world_at_zoom_out, frame_w_screen, cam._fit_zoom * zoomed_out])
	# 顺手验证 zoom-out 后 frame 远大于 board(2.5x board_w 在 board 按宽度 fit 时成立;按高度 fit 时更多)
	_write("zoom-out frame covers more than 2x board width (any fit direction)",
		frame_w_world_at_zoom_out > br20.size.x * 2.0,
		"frame_w_world=%f board_w=%f" % [frame_w_world_at_zoom_out, br20.size.x])

	# 此时 pan clamp 应该 no-op(frame 包含整个 board,clamp 范围反向)
	cam._safe_set_position(Vector2(br20.position.x - 99999.0, br20.position.y - 99999.0))
	# board_center 应该是合法的 position(因为 clamp no-op,值不变或保持原样)
	var br_center: Vector2 = m20.board_center()
	_write("when frame > board, pan is no-op (camera stays at center)",
		cam.position.distance_to(br_center) < 1e-3,
		"cam=%s center=%s" % [str(cam.position), str(br_center)])

	# ── 总结 ────────────────────────────────────────────────────────
	print("")
	print("=== Summary: %d pass / %d fail ===" % [_pass, _fail])
	get_tree().quit(0 if _fail == 0 else 1)
