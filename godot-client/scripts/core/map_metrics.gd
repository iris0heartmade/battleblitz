class_name MapMetrics
extends RefCounted
## Shared board-space metrics for the 48x48 tile renderer.

const TILE_SIZE: Vector2i = Vector2i(48, 48)
const HALF_TILE: Vector2 = Vector2(24.0, 24.0)

var map_size: Vector2i = Vector2i.ZERO


func _init(size: Vector2i = Vector2i.ZERO) -> void:
	map_size = Vector2i(max(size.x, 0), max(size.y, 0))


static func board_size_for(size: Vector2i) -> Vector2i:
	return Vector2i(size.x * TILE_SIZE.x, size.y * TILE_SIZE.y)


static func board_center_for(size: Vector2i) -> Vector2:
	var pixel_size := board_size_for(size)
	return Vector2(pixel_size.x * 0.5, pixel_size.y * 0.5)


static func bounds_for(size: Vector2i) -> Rect2:
	var pixel_size := board_size_for(size)
	return Rect2(Vector2.ZERO, Vector2(pixel_size.x, pixel_size.y))


func board_size() -> Vector2i:
	return board_size_for(map_size)


func board_center() -> Vector2:
	return board_center_for(map_size)


func bounds() -> Rect2:
	return bounds_for(map_size)


func bounds_rect() -> Rect2:
	return bounds()


func contains(tile: Vector2i) -> bool:
	return tile.x >= 0 and tile.y >= 0 and tile.x < map_size.x and tile.y < map_size.y


func cell_origin(tile: Vector2i) -> Vector2:
	return Vector2(tile.x * TILE_SIZE.x, tile.y * TILE_SIZE.y)


func cell_to_local(tile: Vector2i) -> Vector2:
	return cell_origin(tile) + HALF_TILE


func local_to_cell(pos: Vector2) -> Vector2i:
	return Vector2i(floori(pos.x / float(TILE_SIZE.x)), floori(pos.y / float(TILE_SIZE.y)))
