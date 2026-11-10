extends Node3D
## 地形几何与拾取：每个面拥有自己的法线，侧面不会被当作顶面。
const Contents = preload("res://scripts/board/height_map/map_contents.gd")

var model: RefCounted
var terrain_root := Node3D.new()
var materials: Dictionary = {}
var side_materials: Dictionary = {}
var rim_materials: Dictionary = {}
var marker := MeshInstance3D.new()
var unit := Sprite3D.new()
var grid := MeshInstance3D.new()
var surface_grid := MeshInstance3D.new()
var face_count := 0
var selected := Vector2i(4, 4)
var xray_selected := false
var contents: Node3D

func setup(map_model: RefCounted) -> void:
	model = map_model
	add_child(terrain_root)
	for key in model.TERRAINS:
		var material := StandardMaterial3D.new()
		material.roughness = 1.0
		var texture_path: String = model.settings.textures[key]
		material.albedo_texture = load(texture_path)
		material.albedo_color = Color(String(model.settings.top_tints[key]))
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		materials[key] = material
		var side := StandardMaterial3D.new()
		side.albedo_texture = load(String(model.settings.side_textures[key]))
		side.roughness = 0.95
		side.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		side_materials[key] = side
		var rim := StandardMaterial3D.new()
		rim.albedo_color = Color(String(model.settings.rim_colors[key]))
		rim.roughness = 1.0
		rim_materials[key] = rim
	add_child(marker)
	add_child(surface_grid)
	add_child(unit)
	unit.texture = load(String(model.settings.unit_texture))
	unit.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	unit.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	unit.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	unit.alpha_scissor_threshold = 0.35
	unit.shaded = false
	if unit.texture:
		unit.pixel_size = 1.3 / float(unit.texture.get_height())
	add_child(grid)
	grid.visible = false
	contents = Contents.new()
	add_child(contents)
	contents.setup(model)
	rebuild()

func rebuild() -> void:
	for child in terrain_root.get_children():
		terrain_root.remove_child(child)
		child.free()
	face_count = 0
	for y in model.size().y:
		for x in model.size().x:
			_build_cell(Vector2i(x, y))
	_update_surface_grid()
	_make_grid()
	contents.rebuild()
	if not model.units.is_empty():
		unit.visible = false
	selected = selected.clamp(Vector2i.ZERO,model.size()-Vector2i.ONE)
	select(selected)

func _update_surface_grid() -> void:
	var points := PackedVector3Array()
	var half: float = float(model.settings.cell_size) * 0.5
	for y in model.size().y:
		for x in model.size().x:
			var center: Vector3 = model.surface(Vector2i(x, y)) + Vector3.UP * 0.009
			var corners := [Vector3(-half,0,-half), Vector3(half,0,-half), Vector3(half,0,half), Vector3(-half,0,half)]
			for i in 4:
				points.append(center + corners[i])
				points.append(center + corners[(i+1)%4])
	surface_grid.mesh = _lines(points, Color(0.13,0.18,0.12,0.18))

func _build_cell(p: Vector2i) -> void:
	var center: Vector3 = model.surface(p)
	var half: float = float(model.settings.cell_size) * 0.5
	var corners := [center + Vector3(-half, 0, -half), center + Vector3(half, 0, -half), center + Vector3(half, 0, half), center + Vector3(-half, 0, half)]
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	tool.set_material(materials[model.cell(p).terrain])
	var turns := (p.x * 17 + p.y * 31) % 4 if model.cell(p).terrain != "water" else 0
	_quad(tool, corners, Vector3.UP, turns)
	var mesh := tool.commit()
	var sides := SurfaceTool.new()
	sides.begin(Mesh.PRIMITIVE_TRIANGLES)
	var kind: String = model.cell(p).terrain
	sides.set_material(side_materials[kind])
	var rims := SurfaceTool.new()
	rims.begin(Mesh.PRIMITIVE_TRIANGLES)
	rims.set_material(rim_materials[kind])
	var has_sides := false
	var dirs := [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]
	for i in 4:
		var neighbor: Vector2i = p + dirs[i]
		var bottom: float = model.surface(neighbor).y if model.contains(neighbor) else float(model.settings.base_height)
		if bottom >= center.y:
			continue
		var a: Vector3 = corners[i]
		var b: Vector3 = corners[(i + 1) % 4]
		var rim_y: float = maxf(bottom, center.y - float(model.settings.rim_depth))
		var ar := Vector3(a.x, rim_y, a.z)
		var br := Vector3(b.x, rim_y, b.z)
		var normal := Vector3(dirs[i].x, 0, dirs[i].y)
		_quad(rims, [a, ar, br, b], normal)
		if rim_y > bottom:
			_quad(sides, [ar, Vector3(a.x, bottom, a.z), Vector3(b.x, bottom, b.z), br], normal)
		has_sides = true
	if has_sides:
		sides.commit(mesh)
		rims.commit(mesh)
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	terrain_root.add_child(instance)
	# 碰撞采用同一份网格，确保画面与鼠标命中一致。
	var body := StaticBody3D.new()
	body.set_meta("cell", p)
	var shape := CollisionShape3D.new()
	shape.shape = mesh.create_trimesh_shape()
	body.add_child(shape)
	instance.add_child(body)

func _quad(tool: SurfaceTool, vertices: Array, normal: Vector3, turns: int = 0) -> void:
	face_count += 1
	var side := normal != Vector3.UP
	var height: float = vertices[0].distance_to(vertices[1]) if side else float(model.settings.cell_size)
	var uv := [Vector2.ZERO, Vector2(0, height), Vector2(1, height), Vector2(1, 0)] if side else [Vector2.ZERO, Vector2(1, 0), Vector2.ONE, Vector2(0, 1)]
	for i in [0, 1, 2, 0, 2, 3]:
		tool.set_normal(normal)
		tool.set_uv(uv[(i + turns) % 4])
		tool.add_vertex(vertices[i])

func pick(camera: Camera3D, screen: Vector2) -> Dictionary:
	var origin := camera.project_ray_origin(screen)
	var direction := camera.project_ray_normal(screen)
	var query := PhysicsRayQueryParameters3D.create(origin, origin + direction * 1000.0)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty() or not hit.collider.has_meta("cell"):
		return {}
	return {"cell": hit.collider.get_meta("cell"), "top": hit.normal.y > 0.9 or hit.collider.has_meta("content"), "normal": hit.normal}

func select(p: Vector2i) -> void:
	selected = p
	var center: Vector3 = model.surface(p)
	var half: float = float(model.settings.cell_size) * 0.48
	var points := PackedVector3Array()
	var corners := [Vector3(-half, 0, -half), Vector3(half, 0, -half), Vector3(half, 0, half), Vector3(-half, 0, half)]
	for i in 4:
		points.append(center + corners[i] + Vector3.UP * 0.025)
		points.append(center + corners[(i+1)%4] + Vector3.UP * 0.025)
	marker.mesh = _lines(points, Color(1.0, 0.85, 0.25))
	marker.mesh.surface_get_material(0).no_depth_test = xray_selected
	unit.position = center + Vector3.UP * 0.67
	if contents != null:
		contents.select(p,xray_selected)

func toggle_units() -> void:
	if model.units.is_empty():
		unit.visible = not unit.visible
	else:
		contents.units.visible = not contents.units.visible

func set_xray(enabled: bool) -> void:
	# 仅辅助查看选中框和角色，不改变地形碰撞，也不允许鼠标穿墙选格。
	xray_selected = enabled
	unit.no_depth_test = enabled
	select(selected)

func _make_grid() -> void:
	var points := PackedVector3Array()
	var half: float = float(model.settings.cell_size) * 0.5
	for x in range(model.size().x + 1):
		var edge: float = x * float(model.settings.cell_size) - half
		points.append(Vector3(edge, 0.015, -half))
		points.append(Vector3(edge, 0.015, (model.size().y - 0.5) * float(model.settings.cell_size)))
	for y in range(model.size().y + 1):
		var edge: float = y * float(model.settings.cell_size) - half
		points.append(Vector3(-half, 0.015, edge))
		points.append(Vector3((model.size().x - 0.5) * float(model.settings.cell_size), 0.015, edge))
	grid.mesh = _lines(points, Color(0.45, 0.72, 0.9, 0.45))

func _lines(points: PackedVector3Array, color: Color) -> ImmediateMesh:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = color
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES, material)
	for point in points:
		mesh.surface_add_vertex(point)
	mesh.surface_end()
	return mesh
