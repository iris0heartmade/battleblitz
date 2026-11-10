extends Node3D
## 范围只画在逻辑格顶面，不自造寻路或伤害规则。

func show_cells(model: RefCounted, cells: Array, color: Color) -> void:
	clear()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = color
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	for coordinate in cells:
		var p: Vector2i = coordinate
		if not model.contains(p):
			continue
		var plane := PlaneMesh.new()
		plane.size = Vector2.ONE * float(model.settings.cell_size) * 0.88
		var instance := MeshInstance3D.new()
		instance.mesh = plane
		instance.material_override = material
		instance.position = model.surface(p) + Vector3.UP*0.045
		add_child(instance)

func clear() -> void:
	for child in get_children():
		remove_child(child)
		child.free()
