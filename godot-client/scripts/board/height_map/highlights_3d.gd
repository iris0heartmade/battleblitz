extends Node3D
## 所有高亮贴合实际格顶；共享原Highlights模式编号，业务层无需知道3D坐标。
var model: RefCounted
var _mode_nodes: Dictionary = {}
var _signatures: Dictionary = {}

func setup(map_model: RefCounted) -> void:
	model = map_model

func reset(_metrics = null) -> void:
	clear()

func clear() -> void:
	for mode in _mode_nodes.keys():
		clear_mode(mode)

func clear_mode(mode: int) -> void:
	if _mode_nodes.has(mode):
		_mode_nodes[mode].free()
		_mode_nodes.erase(mode)
	_signatures.erase(mode)

func show_outline(mode: int, tiles: Array) -> void:
	_draw(mode,tiles,Highlights._COLORS.get(mode,Color.WHITE))

func show_path(tiles: Array) -> void:
	_draw(Highlights.Mode.PATH,tiles,Highlights._COLORS[Highlights.Mode.PATH])

func show_hover(tile: Vector2i) -> void:
	show_outline(Highlights.Mode.HOVER,[tile])

func show_selected(tile: Vector2i) -> void:
	show_outline(Highlights.Mode.SELECTED,[tile])

func show_cursor_at(tile: Vector2i, _color: Color) -> void:
	show_outline(Highlights.Mode.CURSOR,[tile])

func _draw(mode: int, tiles: Array, color: Color) -> void:
	if _signatures.get(mode,[]) == tiles:
		return
	clear_mode(mode)
	_signatures[mode] = tiles.duplicate()
	var layer := Node3D.new()
	add_child(layer)
	_mode_nodes[mode] = layer
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = color
	for p in tiles:
		if not p is Vector2i or not model.contains(p):
			continue
		var mesh := MeshInstance3D.new()
		var plane := PlaneMesh.new()
		var width := 0.18 if mode == Highlights.Mode.PATH else 0.94
		plane.size = Vector2.ONE*width*float(model.settings.cell_size)
		mesh.mesh = plane
		mesh.material_override = material
		mesh.position = model.surface(p)+Vector3.UP*(0.04+mode*0.002)
		layer.add_child(mesh)
