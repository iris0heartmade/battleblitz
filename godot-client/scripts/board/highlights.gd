extends Node2D
class_name Highlights
## Highlights — overlay node for move / attack / path / threat
## indicators on top of the TileMap. M1 ships a working sprite
## palette + a "no-op reset" interface; M2 will fill in the
## reachable-set and attack-range visuals once MapLogic grows up.
##
## Visual convention (mirrors `app.js` `.move-hint / .attack-hint /
## .path-dot`):
##   MOVE      = soft cyan rect outline       (40% alpha)
##   ATTACK    = soft red rect outline         (40% alpha)
##   PATH      = small cyan dot, one per cell  (60% alpha)
##   THREAT    = orange rect outline           (50% alpha)
##   SELECTED  = bright yellow rect outline    (80% alpha)
##   HOVER     = thin white outline             (60% alpha)
##
## Each mode is rendered as its own child Node2D so toggling
## one doesn't re-tessellate the others. M2 may split the per-
## cell outlines into a multi‑mesh if profiling shows 25×25
## boards stutter.

enum Mode { NONE, MOVE, ATTACK, PATH, THREAT, SELECTED, HOVER }

const _COLORS := {
	Mode.MOVE:     Color(0.37, 0.78, 0.98, 0.40),
	Mode.ATTACK:   Color(0.95, 0.40, 0.45, 0.40),
	Mode.PATH:     Color(0.37, 0.78, 0.98, 0.85),
	Mode.THREAT:   Color(0.98, 0.65, 0.30, 0.50),
	Mode.SELECTED: Color(0.98, 0.85, 0.30, 0.85),
	Mode.HOVER:    Color(1.00, 1.00, 1.00, 0.60),
}

# Per-mode child nodes; lazily created on first use.
var _mode_nodes: Dictionary = {}
# Sprite pool per mode (recycled across show_*() calls). The pool
# values are `Node2D` (the actual type is ColorRect, but we treat them
# as Node2D to dodge Variant-inference warnings).
var _pool: Dictionary = {}

var _board_size: Vector2i = Vector2i.ZERO
var _tile_size: Vector2i = Vector2i(48, 48)
var _terrain_layer: TileMapLayer = null


# ============================================================
# Public API
# ============================================================

## Bind the terrain layer used for coordinate translation. Called by
## `Board._ready()` after the TileSet is in place.
func bind_terrain_layer(layer: TileMapLayer) -> void:
	_terrain_layer = layer

## Wipe all highlights and (re)size the sprite pools.
## Called by `Board` after a new map is loaded.
func reset(map_size: Vector2i) -> void:
	_board_size = map_size
	_tile_size = Vector2i(TileSetBuilder.TILE_SIZE)
	_pool.clear()
	# Eagerly allocate one pool per known mode.
	for mode in _COLORS.keys():
		_ensure_mode_node(mode)

func clear() -> void:
	for k in _mode_nodes:
		var node: Node2D = _mode_nodes[k]
		for child in node.get_children():
			if child is Node2D:
				(child as Node2D).visible = false

func show_outline(mode: int, tiles: Array) -> void:
	clear_mode(mode)
	if _terrain_layer == null:
		return
	var node := _ensure_mode_node(mode)
	var color: Color = _COLORS.get(mode, Color.WHITE)
	for i in tiles.size():
		var tile: Vector2i = tiles[i]
		var sprite := _checkout_sprite(node, i, color)
		sprite.position = _tile_to_viewport(tile)
		sprite.visible = true

func show_path(tiles: Array) -> void:
	clear_mode(Mode.PATH)
	if _terrain_layer == null:
		return
	var node := _ensure_mode_node(Mode.PATH)
	var color: Color = _COLORS[Mode.PATH]
	for i in tiles.size():
		var tile: Vector2i = tiles[i]
		var sprite := _checkout_dot(node, i, color)
		sprite.position = _tile_to_viewport(tile)
		sprite.visible = true

func show_hover(tile: Vector2i) -> void:
	clear_mode(Mode.HOVER)
	if tile.x < 0 or tile.y < 0 or tile.x >= _board_size.x or tile.y >= _board_size.y:
		return
	show_outline(Mode.HOVER, [tile])

func show_selected(tile: Vector2i) -> void:
	if tile.x < 0 or tile.y < 0:
		clear_mode(Mode.SELECTED)
		return
	show_outline(Mode.SELECTED, [tile])

func clear_mode(mode: int) -> void:
	if not _mode_nodes.has(mode):
		return
	var node: Node2D = _mode_nodes[mode]
	for child in node.get_children():
		if child is Node2D:
			(child as Node2D).visible = false


# ============================================================
# Sprite pool
# ============================================================

func _ensure_mode_node(mode: int) -> Node2D:
	if _mode_nodes.has(mode):
		return _mode_nodes[mode]
	var node := Node2D.new()
	node.name = "Mode_%d" % mode
	add_child(node)
	_mode_nodes[mode] = node
	return node

func _checkout_sprite(parent: Node2D, index: int, color: Color) -> Node2D:
	# Lazy-create a pool per parent (mode). The pool key includes
	# `index` for deterministic ordering, so recycling is just
	# "reuse the Nth sprite".
	if not _pool.has(parent):
		_pool[parent] = []
	var pool: Array = _pool[parent]
	while pool.size() <= index:
		var sprite := _make_outline_sprite(color)
		parent.add_child(sprite)
		pool.append(sprite)
	# Refresh color in case the highlight mode's color was edited.
	# Pool values are Node2D-wrapped; access .color via a method-style
	# call so the static type checker doesn't complain.
	var sprite: Node2D = pool[index]
	_apply_color(sprite, color)
	return sprite

func _checkout_dot(parent: Node2D, index: int, color: Color) -> Node2D:
	if not _pool.has(parent):
		_pool[parent] = []
	var pool: Array = _pool[parent]
	while pool.size() <= index:
		var dot := _make_dot_sprite(color)
		parent.add_child(dot)
		pool.append(dot)
	var dot: Node2D = pool[index]
	_apply_color(dot, color)
	return dot

func _apply_color(node: Node, color: Color) -> void:
	# ColorRect exposes `.color` directly; the outline wrapper is a
	# Node2D parent of 4 ColorRect children. Walk the children too.
	if node is ColorRect:
		(node as ColorRect).color = color
		return
	for child in node.get_children():
		if child is ColorRect:
			(child as ColorRect).color = color

func _make_outline_sprite(color: Color) -> Node2D:
	# A 48×48 wrapper holding 4 thin ColorRect bars at the edges.
	# The wrapper itself is invisible (modulate.a = 0) so only the
	# border is visible — matches the JS frontend's `.move-hint`
	# cell outline. M2 can swap to a Line2D ring if the four-bar
	# trick looks chunky at high DPI.
	var wrapper := Node2D.new()
	for side in [
		{"x": 0, "y": 0, "w": _tile_size.x, "h": 3},
		{"x": 0, "y": _tile_size.y - 3, "w": _tile_size.x, "h": 3},
		{"x": 0, "y": 0, "w": 3, "h": _tile_size.y},
		{"x": _tile_size.x - 3, "y": 0, "w": 3, "h": _tile_size.y},
	]:
		var bar := ColorRect.new()
		bar.size = Vector2(side.w, side.h)
		bar.position = Vector2(side.x - _tile_size.x * 0.5, side.y - _tile_size.y * 0.5)
		bar.color = color
		bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
		wrapper.add_child(bar)
	return wrapper

func _make_dot_sprite(color: Color) -> ColorRect:
	var dot := ColorRect.new()
	dot.size = Vector2(8, 8)
	dot.position = -dot.size * 0.5
	dot.color = color
	dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return dot

## Convert a tile coord to a global position using the bound layer.
func _tile_to_viewport(tile: Vector2i) -> Vector2:
	if _terrain_layer == null:
		return Vector2.ZERO
	return _terrain_layer.to_global(_terrain_layer.map_to_local(tile))
