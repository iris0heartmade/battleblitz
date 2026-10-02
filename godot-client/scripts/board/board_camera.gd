extends Camera2D
class_name BoardCamera
## Board camera with a fixed-size "central window" frame.
##
## User model:
##   - 棋盘初始 fit 时,viewport 中央的固定矩形区域(以像素计)=「框」。
##   - 框固定大小:不随 zoom 变化。
##   - 框外的区域不会显示棋盘(由 Camera2D limit_* + 子节点 scale 共同保证)。
##   - 玩家通过 wheel 调 zoom、drag 调 pan,在框内浏览棋盘。
##
## 实现要点:
##   1. fit_zoom 算的是「棋盘刚好填进 _frame_size_px 时的缩放比」,初始化时算一次。
##   2. user_zoom_factor(0.4 ~ 3.0)是玩家乘数;camera.zoom.x = fit_zoom * user_zoom_factor。
##   3. position setter 重写:写入前用「_frame_size_px + 当前 zoom + board_rect」算硬限制,
##      确保 pan 时框的 4 条边不会越过棋盘的 4 条边。
##   4. board.gd 通过 apply_user_zoom_factor(delta) 修改 zoom,不再直接写 camera.zoom。
##      其它所有读 camera.zoom.x / camera.position 的位置不变。
##
## HUD 已经挂在独立的 CanvasLayer(layer=10)上,不受 camera transform 影响。

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const _FIT_MARGIN := 16.0
const _UI_TOP_SAFE_PX := 112.0
const _UI_BOTTOM_SAFE_PX := 16.0
# The inspect card is opt-in. The normal battlefield must not reserve an
# invisible sidebar, while a visible card gets a modest right-side safe area.
const _UI_LEFT_FRACTION := 0.00
const _UI_RIGHT_FRACTION := 0.27

# === user_zoom_factor 上下限 ===
# 0.4 → 看到 2.5 倍 fit 的范围(更广);3.0 → 看到 1/3 倍 fit 的范围(更细)。
const USER_ZOOM_MIN: float = 0.4
const USER_ZOOM_MAX: float = 3.0

var _metrics = null
var _user_positioned: bool = false
var _inspect_card_visible: bool = false

# === Frame (the "central window") ===
# _frame_size_px: 初始 fit 时,viewport 可用区域的像素大小。**不随 zoom 变**。
# 整个「中间那块固定大小」的概念就源自这个值。
var _frame_size_px: Vector2 = Vector2.ZERO
# _frame_center_offset_px: viewport 中心到 frame 中心的偏移(因为右侧 UI 留白)。
var _frame_center_offset_px: Vector2 = Vector2.ZERO

# === Zoom 拆层 ===
# camera.zoom.x = _fit_zoom * _user_zoom_factor
# _fit_zoom: 初始化一次,viewport 大小变才重算(用户改 zoom 不重算)。
# _user_zoom_factor: 玩家乘数(0.4 ~ 3.0)。
var _fit_zoom: float = 1.0
var _user_zoom_factor: float = 1.0


func _ready() -> void:
	var viewport := get_viewport()
	if viewport != null and not viewport.size_changed.is_connected(_on_viewport_size_changed):
		viewport.size_changed.connect(_on_viewport_size_changed)


func apply_metrics(metrics) -> void:
	_metrics = metrics
	if _user_positioned:
		enabled = true
		return
	_refresh_from_metrics(false)
	enabled = true


func apply_new_map_metrics(metrics) -> void:
	_metrics = metrics
	if _user_positioned:
		enabled = true
		return
	reset_to_fit()
	enabled = true


func _on_viewport_size_changed() -> void:
	if _user_positioned:
		return
	_refresh_from_metrics(false)


func reset_to_fit() -> void:
	_user_positioned = false
	_user_zoom_factor = 1.0
	_refresh_from_metrics(false)


func mark_user_positioned() -> void:
	_user_positioned = true


func set_inspect_card_visible(is_visible: bool) -> void:
	if _inspect_card_visible == is_visible:
		return
	_inspect_card_visible = is_visible
	if not _user_positioned:
		_refresh_from_metrics(false)


# === Public API for board.gd 改用 ===
# 通过此 API 改 zoom,而不是直接赋值 camera.zoom。这样 camera 内部的
# _user_zoom_factor / _fit_zoom / limit 状态保持一致。
# `delta_factor` 是 user_zoom_factor 的增量(正值放大,负值缩小)。
# 内部 clamp 到 [USER_ZOOM_MIN, USER_ZOOM_MAX]。
# 返回最终的 user_zoom_factor(可能因 clamp 而与 new_factor 不同)。
func apply_user_zoom_factor_delta(delta_factor: float) -> float:
	if _fit_zoom <= 0.0:
		return _user_zoom_factor
	var new_factor: float = clamp(_user_zoom_factor + delta_factor, USER_ZOOM_MIN, USER_ZOOM_MAX)
	if new_factor == _user_zoom_factor:
		return new_factor
	_user_zoom_factor = new_factor
	zoom = Vector2(_fit_zoom * _user_zoom_factor, _fit_zoom * _user_zoom_factor)
	# zoom 改变后,limit 也要重算(pan 范围变了)。
	_recompute_limits()
	return new_factor


func get_user_zoom_factor() -> float:
	return _user_zoom_factor


# === Position setter 重写 ===
# 不让外部直接 set position,所有 position 改动走 _set_clamped_position。
# 但 board.gd 有直接 set position 的代码,所以保留 position writable,
# 通过 setter 钩子(用 set_position_smoothing_enabled / 不行的话用 _set hook)。
# 简单起见,提供一个 _safe_set_position 公共方法,board.gd 调用它。
func _safe_set_position(new_pos: Vector2) -> void:
	var clamped_pos := _clamp_position_to_frame(new_pos)
	if position != clamped_pos:
		position = clamped_pos


func _clamp_position_to_frame(candidate: Vector2) -> Vector2:
	# 在 zoom = fit_zoom * user_zoom_factor 下:
	# frame 在世界坐标的 size = _frame_size_px / zoom
	# board 的 world rect = _board_rect_for(_metrics)
	# camera.position 是 camera 看的「世界点」(默认 viewport 中心 = position)。
	# 为了让「frame 四条边」不越过 board 的四条边:
	#   frame_left  = candidate.x - frame_w_world / 2
	#   frame_right = candidate.x + frame_w_world / 2
	# 要满足 frame_left >= board_left → candidate.x >= board_left + frame_w_world/2
	# 要满足 frame_right <= board_right → candidate.x <= board_right - frame_w_world/2
	# 等价 clamp 到 [board_left + frame_w_world/2, board_right - frame_w_world/2]
	# 但因为 zoom 改变,frame_w_world = frame_w_px / zoom 也会变,所以 clamp 范围跟 zoom 有关。
	#
	# 注意:_board_rect 的 size 是 fit_zoom 下的世界尺寸(实际 fit 时,frame_w_world == board_w)。
	# 当 zoom 放大(user_factor > 1),frame_w_world = frame_w_px / (fit_zoom * user_factor) < board_w,
	# clamp 范围变窄,pan 空间变小 —— 这正是「超出范围的区域不显示」想要的。
	if _metrics == null or _frame_size_px.x <= 0.0 or _frame_size_px.y <= 0.0:
		return candidate
	var actual_zoom: float = _fit_zoom * _user_zoom_factor
	if actual_zoom <= 0.0:
		return candidate
	var board_rect := _board_rect_for(_metrics)
	if board_rect.size.x <= 0.0 or board_rect.size.y <= 0.0:
		return candidate

	var frame_w_world: float = _frame_size_px.x / actual_zoom
	var frame_h_world: float = _frame_size_px.y / actual_zoom
	var board_left: float = board_rect.position.x
	var board_top: float = board_rect.position.y
	var board_right: float = board_rect.position.x + board_rect.size.x
	var board_bottom: float = board_rect.position.y + board_rect.size.y

	# frame 在世界坐标的 clamp 范围:
	#   camera.x ∈ [board_left + frame_w_world/2, board_right - frame_w_world/2]
	# 如果 frame 比 board 还大(zoom-out 太多),clamp 范围会反向 (min > max):
	# 这种情况下「框已经盖住整张 board」,任意 pan 都没意义,把所有 pan 锁到 board center。
	var min_x: float = board_left + frame_w_world * 0.5
	var max_x: float = board_right - frame_w_world * 0.5
	var min_y: float = board_top + frame_h_world * 0.5
	var max_y: float = board_bottom - frame_h_world * 0.5
	var cx: float = candidate.x
	var cy: float = candidate.y
	if min_x <= max_x:
		cx = clamp(cx, min_x, max_x)
	else:
		# 框 > board:把 pan 锁到 board 中心(唯一「完整可见 board」的位置)
		cx = (board_left + board_right) * 0.5
	if min_y <= max_y:
		cy = clamp(cy, min_y, max_y)
	else:
		cy = (board_top + board_bottom) * 0.5
	return Vector2(cx, cy)


func _recompute_limits() -> void:
	# Camera2D 内置的 limit_* 是 world-coord clamp box;我们用 _clamp_position_to_frame 手动 clamp,
	# limit_* 留为全 viewport 范围(不依赖 Camera2D 内置 limit 行为,避免双重 clamp 的诡异)。
	if _metrics == null:
		return
	var board_rect := _board_rect_for(_metrics)
	limit_left = int(floor(board_rect.position.x - 1.0e6))
	limit_top = int(floor(board_rect.position.y - 1.0e6))
	limit_right = int(ceil(board_rect.position.x + board_rect.size.x + 1.0e6))
	limit_bottom = int(ceil(board_rect.position.y + board_rect.size.y + 1.0e6))


# === 内部重算 ===
func _refresh_from_metrics(position_only: bool = false) -> void:
	if _metrics == null:
		return

	var board_rect := _board_rect_for(_metrics)
	if board_rect.size.x <= 0.0 or board_rect.size.y <= 0.0:
		return

	var viewport := get_viewport()
	if viewport == null:
		return
	var viewport_size := viewport.get_visible_rect().size
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		return

	var reserved_right: float = _UI_RIGHT_FRACTION if _inspect_card_visible else 0.0
	var usable_w: float = viewport_size.x * (1.0 - _UI_LEFT_FRACTION - reserved_right)
	var usable_h: float = max(1.0, viewport_size.y - _UI_TOP_SAFE_PX - _UI_BOTTOM_SAFE_PX)

	# 记录「框」的固定像素尺寸 + frame 中心相对 viewport 中心的偏移
	# (用于 _clamp_position_to_frame:用户 pan 时,框的 4 条边不能越过 board 4 条边)。
	_frame_size_px = Vector2(usable_w - _FIT_MARGIN, usable_h - _FIT_MARGIN)
	_frame_size_px.x = max(1.0, _frame_size_px.x)
	_frame_size_px.y = max(1.0, _frame_size_px.y)
	var ui_left_px: float = viewport_size.x * _UI_LEFT_FRACTION
	_frame_center_offset_px = Vector2(
		(ui_left_px + usable_w * 0.5) - viewport_size.x * 0.5,
		(_UI_TOP_SAFE_PX + usable_h * 0.5) - viewport_size.y * 0.5
	)

	# 算 fit_zoom:让 board 完整 fit 进 _frame_size_px(取 min(w, h) 那个方向)。
	var zoom_x: float = _frame_size_px.x / board_rect.size.x
	var zoom_y: float = _frame_size_px.y / board_rect.size.y
	_fit_zoom = max(0.01, min(zoom_x, zoom_y))

	# camera.zoom = fit_zoom * user_zoom_factor。
	# 如果 user_factor 是 1.0,就是 fit(恢复原行为)。
	zoom = Vector2(_fit_zoom * _user_zoom_factor, _fit_zoom * _user_zoom_factor)

	# 初始 position = board_center - frame_center_offset(让 board 中心对准 frame 中心)
	var board_center := _board_center_for(_metrics, board_rect)
	var target_pos: Vector2 = Vector2(
		board_center.x - _frame_center_offset_px.x,
		board_center.y - _frame_center_offset_px.y
	)
	# 走 clamp(虽然此时 frame 正好 fit 整个 board,clamp 是 no-op,但保持逻辑一致)
	position = _clamp_position_to_frame(target_pos)

	# limit_* 设大一点(让 Camera2D 内置 limit 不挡),真实 clamp 走 _clamp_position_to_frame。
	_recompute_limits()


func _board_rect_for(metrics) -> Rect2:
	if metrics.has_method("bounds_rect"):
		return metrics.bounds_rect()

	var board_size: Vector2i = _board_size_for(metrics)
	var tile_size := Vector2(MAP_METRICS_SCRIPT.TILE_SIZE)
	return Rect2(Vector2.ZERO, Vector2(board_size) * tile_size)


func _board_center_for(metrics, board_rect: Rect2) -> Vector2:
	if metrics.has_method("board_center"):
		return metrics.board_center()
	return board_rect.position + (board_rect.size * 0.5)


func _board_size_for(metrics) -> Vector2i:
	if _has_property(metrics, "board_size"):
		return metrics.board_size
	if _has_property(metrics, "map_size"):
		return metrics.map_size
	return Vector2i.ZERO


func _has_property(target: Object, property_name: String) -> bool:
	if target == null:
		return false
	for property_info in target.get_property_list():
		if String(property_info.get("name", "")) == property_name:
			return true
	return false
