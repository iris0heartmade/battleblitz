extends Camera3D
## 正交环绕相机：只改变3D视野，不改变菜单和HUD坐标。

var focus := Vector3.ZERO
var yaw := 45.0
var pitch := 30.0
var defaults: Dictionary
var target_yaw := 45.0
var target_focus := Vector3.ZERO
var top_inset := 80.0
var right_inset := 40.0
var bottom_inset := 60.0
var left_inset := -1.0

func _process(delta: float) -> void:
	if is_equal_approx(yaw, target_yaw) and focus.is_equal_approx(target_focus):
		return
	# 指数插值使不同帧率的转向速度一致；最后收敛到准确角度。
	yaw = lerpf(yaw, target_yaw, 1.0 - exp(-float(defaults.camera_turn_smoothing) * delta))
	if absf(yaw - target_yaw) < 0.01:
		yaw = target_yaw
	focus = focus.lerp(target_focus, 1.0 - exp(-float(defaults.camera_follow_smoothing) * delta))
	if focus.distance_to(target_focus) < 0.001:
		focus = target_focus
	update_view()

func safe_rect() -> Rect2:
	var viewport_size := get_viewport().get_visible_rect().size
	var left := float(defaults.camera_safe_left) if left_inset < 0 else left_inset
	return Rect2(Vector2(left, top_inset), viewport_size - Vector2(left + right_inset, top_inset + bottom_inset))

func set_inspect_card_visible(enabled: bool) -> void:
	right_inset = get_viewport().get_visible_rect().size.x*0.27 if enabled else 40.0
	update_view()

func keep_visible(point: Vector3) -> void:
	# 仅在安全区边缘滚屏；不强迫每次移动都回到屏幕中央。
	var screen := unproject_position(point)
	var safe := safe_rect().grow(-float(defaults.camera_follow_margin))
	var nearest := screen.clamp(safe.position, safe.end)
	var delta := screen - nearest
	if delta.length() < 1:
		return
	var pixel_scale := size / get_viewport().get_visible_rect().size.y
	target_focus = focus + (global_basis.x * delta.x - global_basis.y * delta.y) * pixel_scale

func turn(degrees: float, smooth: bool = true) -> void:
	# 目标角连续累加，不在360°处折返，快速连续点击也不会反向绕远。
	target_yaw += degrees
	if not smooth:
		yaw = target_yaw
		update_view()

func orbit_drag(delta: Vector2) -> void:
	# 拖动接管当前朝向，取消尚未结束的按钮动画。
	target_yaw = yaw
	turn(-delta.x * float(defaults.camera_drag_sensitivity), false)
	pitch = clampf(pitch + delta.y * float(defaults.camera_drag_sensitivity), 20.0, 60.0)
	update_view()

func focus_on(point: Vector3) -> void:
	focus = point
	target_focus = point
	update_view()

func setup(config: Dictionary) -> void:
	defaults = config
	projection = Camera3D.PROJECTION_ORTHOGONAL
	near = 0.1
	far = 200.0
	current = true
	reset_view()

func reset_view() -> void:
	focus = Vector3((float(defaults.width)-1)*0.5*float(defaults.cell_size), 0, (float(defaults.depth)-1)*0.5*float(defaults.cell_size))
	target_focus = focus
	yaw = float(defaults.camera_yaw)
	target_yaw = yaw
	pitch = float(defaults.camera_pitch)
	size = float(defaults.camera_size)
	update_view()

func update_view() -> void:
	# 把镜头中心移到编辑面板右侧的可用区域。
	var viewport_size := get_viewport().get_visible_rect().size
	h_offset = -(safe_rect().get_center().x - viewport_size.x * 0.5) * size / maxf(1, viewport_size.y)
	# 战斗底栏占用下方空间时，也将棋盘视觉中心移入上方安全区域。
	v_offset = (safe_rect().get_center().y - viewport_size.y * 0.5) * size / maxf(1, viewport_size.y) if bottom_inset > 0 else 0.0
	var direction := Vector3(sin(deg_to_rad(yaw))*cos(deg_to_rad(pitch)), sin(deg_to_rad(pitch)), cos(deg_to_rad(yaw))*cos(deg_to_rad(pitch)))
	position = focus + direction * 40.0
	look_at(focus, Vector3.UP)

func pan(delta: Vector2) -> void:
	var scale_factor := size / maxf(1, get_viewport().get_visible_rect().size.y)
	focus += (-global_basis.x * delta.x + global_basis.y * delta.y) * scale_factor
	target_focus = focus
	update_view()

func zoom(factor: float) -> void:
	size = clampf(size * factor, float(defaults.camera_min_size), float(defaults.camera_max_size))
	update_view()
