extends Camera2D
class_name BoardCamera

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const _FIT_MARGIN := 16.0

var _metrics = null


func _ready() -> void:
	var viewport := get_viewport()
	if viewport != null and not viewport.size_changed.is_connected(_on_viewport_size_changed):
		viewport.size_changed.connect(_on_viewport_size_changed)


func apply_metrics(metrics) -> void:
	_metrics = metrics
	_refresh_from_metrics()
	# Only switch the camera on once we have real map metrics —
	# otherwise its anchor_mode=DRAG_CENTER drags the canvas origin
	# to viewport_size/2, which clips the main menu UI into the
	# bottom-right quadrant.
	enabled = true


func _on_viewport_size_changed() -> void:
	_refresh_from_metrics()


func _refresh_from_metrics() -> void:
	if _metrics == null:
		return

	var board_rect := _board_rect_for(_metrics)
	if board_rect.size.x <= 0.0 or board_rect.size.y <= 0.0:
		return

	position = _board_center_for(_metrics, board_rect)

	var viewport := get_viewport()
	if viewport == null:
		return
	var viewport_size := viewport.get_visible_rect().size
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		return

	var zoom_x: float = min(1.0, max(0.01, (viewport_size.x - _FIT_MARGIN) / board_rect.size.x))
	var zoom_y: float = min(1.0, max(0.01, (viewport_size.y - _FIT_MARGIN) / board_rect.size.y))
	var fit_zoom: float = min(zoom_x, zoom_y)
	zoom = Vector2(fit_zoom, fit_zoom)

	limit_left = int(floor(board_rect.position.x))
	limit_top = int(floor(board_rect.position.y))
	limit_right = int(ceil(board_rect.end.x))
	limit_bottom = int(ceil(board_rect.end.y))


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
