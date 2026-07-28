extends Camera2D
class_name BoardCamera

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const _FIT_MARGIN := 16.0
# The inspect card is opt-in. The normal battlefield must not reserve an
# invisible sidebar, while a visible card gets a modest right-side safe area.
const _UI_LEFT_FRACTION := 0.00
const _UI_RIGHT_FRACTION := 0.27

var _metrics = null
var _user_positioned: bool = false
var _inspect_card_visible: bool = false


func _ready() -> void:
	var viewport := get_viewport()
	if viewport != null and not viewport.size_changed.is_connected(_on_viewport_size_changed):
		viewport.size_changed.connect(_on_viewport_size_changed)

func apply_metrics(metrics) -> void:
	_metrics = metrics
	if _user_positioned:
		enabled = true
		return
	else:
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
	_refresh_from_metrics(false)


func mark_user_positioned() -> void:
	_user_positioned = true


func set_inspect_card_visible(is_visible: bool) -> void:
	if _inspect_card_visible == is_visible:
		return
	_inspect_card_visible = is_visible
	if not _user_positioned:
		_refresh_from_metrics(false)



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
	var usable_h: float = viewport_size.y
	# Board 实际可视区中心 = viewport 中心 + 偏移(因为棋盘偏向 viewport 右侧)
	var ui_left_px: float = viewport_size.x * _UI_LEFT_FRACTION
	var center_offset_x: float = (ui_left_px + usable_w * 0.5) - viewport_size.x * 0.5
	var board_center := _board_center_for(_metrics, board_rect)
	position = Vector2(board_center.x - center_offset_x, board_center.y)

	var zoom_x: float = max(0.01, (usable_w - _FIT_MARGIN) / board_rect.size.x)
	var zoom_y: float = max(0.01, (usable_h - _FIT_MARGIN) / board_rect.size.y)
	var fit_zoom: float = min(zoom_x, zoom_y)
	if not position_only:
			zoom_x = max(0.01, (usable_w - _FIT_MARGIN) / board_rect.size.x)
			zoom_y = max(0.01, (usable_h - _FIT_MARGIN) / board_rect.size.y)
			fit_zoom = min(zoom_x, zoom_y)
			zoom = Vector2(fit_zoom, fit_zoom)

	# M3+ TODO: tighten the limits back to board_rect once the HUD is
	# hosted on a dedicated CanvasLayer that lives ABOVE the camera
	# transform. Right now every Control (HUD pills, war-report panel)
	# rides the same canvas_transform, so clamping limits to board_rect
	# pushes them into a 720×720 sub-rectangle of the viewport. Leaving
	# limits at the full viewport keeps the UI where we put it in .tscn.
	# limits 设为棋盘实际范围,用户可在此范围内自由拖拽
	limit_left = int(floor(board_rect.position.x))
	limit_top = int(floor(board_rect.position.y))
	limit_right = int(ceil(board_rect.position.x + board_rect.size.x))
	limit_bottom = int(ceil(board_rect.position.y + board_rect.size.y))


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
