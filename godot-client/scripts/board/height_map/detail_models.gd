extends RefCounted
## 共享低面数实体造型；材质由宿主缓存，细节没有碰撞。
var host: Node
var settings: Dictionary
var meshes: Dictionary = {}

func _init(owner_node: Node) -> void:
	host = owner_node
	settings = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/detail_models.json"))

func color(key: String) -> Color:
	return Color(String(settings.palette[key]))

func blob(parent: Node3D, at: Vector3, size: Vector3, shade: Color) -> MeshInstance3D:
	if not meshes.has("stone"):
		var sphere := SphereMesh.new()
		sphere.radial_segments = 9
		sphere.rings = 5
		sphere.radius = 0.5
		sphere.height = 1
		meshes.stone = sphere
	var node: MeshInstance3D = host._mesh(parent, meshes.stone, at, shade)
	node.scale = size
	return node

func rebuild(root: Node3D, model: RefCounted) -> void:
	for child in root.get_children():
		child.free()
	for y in model.size().y:
		for x in model.size().x:
			var p := Vector2i(x,y)
			if not String(model.cell(p).get("feature","")).is_empty():
				continue
			var kind := String(model.cell(p).terrain)
			var profile: Dictionary = settings.terrains[kind]
			var seed_value := posmod((x*73856093) ^ (y*19349663),2147483647)
			if seed_value % 100 >= int(profile.density):
				continue
			var anchor := Node3D.new()
			anchor.name = "Detail_%d_%d" % [x,y]
			anchor.set_meta("cell",p)
			anchor.position = model.surface(p)
			anchor.scale = Vector3.ONE * float(model.settings.cell_size)
			root.add_child(anchor)
			var turn := float(seed_value % 360) * PI / 180
			var radius := float(settings.edge_radius)
			var point := Vector3(cos(turn)*radius,0,sin(turn)*radius)
			var factor := 0.85 + float(seed_value % 31)/100.0
			match kind:
				"grass": _grass(anchor,point,factor,seed_value)
				"rock": _rocks(anchor,point,factor)
				"sand": _sand(anchor,point,factor)
				"water": _water(anchor,point,factor)

func _grass(parent: Node3D, p: Vector3, factor: float, seed_value: int) -> void:
	blob(parent,p+Vector3(0,0.025,0),Vector3(0.31,0.09,0.23)*factor,color("turf"))
	if seed_value % 2 == 0:
		for i in 3:
			var at := p+Vector3((i-1)*0.065,0.075+float(i%2)*0.035,0)
			blob(parent,at,Vector3(0.13,0.14,0.13)*factor,color("leaf_light") if i==1 else color("leaf"))
	else:
		blob(parent,p+Vector3(0.06,0.055,0),Vector3(0.12,0.1,0.11),color("stone"))
	_tuft(parent,p+Vector3(-0.08,0,0.08),color("grass"))

func _rocks(parent: Node3D, p: Vector3, factor: float) -> void:
	for i in 3:
		var height := (0.12+float(i%2)*0.14)*factor
		var rock := blob(parent,p+Vector3((i-1)*0.09,height*0.45,0.035*(i%2)),Vector3(0.18,height,0.16)*factor,color("stone_light") if i==1 else color("stone"))
		rock.rotation_degrees.y = float(i*47)
	blob(parent,p+Vector3(-0.08,0.014,0.09),Vector3(0.13,0.025,0.08),color("moss"))

func _sand(parent: Node3D, p: Vector3, factor: float) -> void:
	blob(parent,p+Vector3(0,0.012,0),Vector3(0.34,0.1,0.23)*factor,color("sand"))
	blob(parent,p+Vector3(0.07,0.035,0.025),Vector3(0.14,0.075,0.11),color("sandstone"))
	_tuft(parent,p+Vector3(-0.09,0,0.06),color("dry_grass"))

func _water(parent: Node3D, p: Vector3, factor: float) -> void:
	blob(parent,p+Vector3(0,-0.015,0),Vector3(0.3,0.055,0.23)*factor,color("shoal"))
	blob(parent,p+Vector3(0.04,0.045,0),Vector3(0.14,0.13,0.13),color("stone"))
	for i in 3:
		var stem: MeshInstance3D = host._cylinder(parent,0.006,0.14+0.025*i,p+Vector3(-0.065+0.02*i,0.07+0.0125*i,0.02),color("reed"))
		stem.rotation_degrees.z = float((i-1)*12)

func _tuft(parent: Node3D, at: Vector3, shade: Color) -> void:
	for i in 3:
		var blade: MeshInstance3D = host._cylinder(parent,0.009,0.07,at+Vector3((i-1)*0.015,0.035,0),shade,0.002)
		blade.rotation_degrees.z = float((i-1)*22)

func house(parent: Node3D) -> void:
	# 门框、窗框和木梁在前后左右都有体积，旋转后仍然完整。
	for z in [-0.226,0.226]:
		for x in [-0.2,0.2]:
			host._box(parent,Vector3(0.025,0.34,0.025),Vector3(x,0.17,z),color("timber"))
		host._box(parent,Vector3(0.44,0.025,0.025),Vector3(0,0.31,z),color("timber"))
	for x in [-0.239,0.239]:
		host._box(parent,Vector3(0.015,0.1,0.13),Vector3(x,0.21,0),color("timber"))
		host._box(parent,Vector3(0.019,0.07,0.09),Vector3(x,0.21,0),color("glass"))
	host._box(parent,Vector3(0.13,0.025,0.09),Vector3(0,0.014,0.245),color("stone"))
	host._box(parent,Vector3(0.035,0.035,0.57),Vector3(0,0.58,0),color("timber"))
	for x in [-0.28,0.28]:
		host._box(parent,Vector3(0.025,0.025,0.56),Vector3(x,0.335,0),color("roof_trim"))

func castle(parent: Node3D) -> void:
	for x in [-0.32,0.32]:
		for z in [-0.3,0.3]:
			for side in [-1,1]:
				host._box(parent,Vector3(0.055,0.1,0.02),Vector3(x,0.43,z+side*0.128),color("timber"))
	for x in [-0.18,0,0.18]:
		host._box(parent,Vector3(0.09,0.08,0.065),Vector3(x,0.58,0.17),color("stone_light"))
	for side in [-1,1]:
		host._box(parent,Vector3(0.018,0.13,0.085),Vector3(side*0.25,0.36,-0.08),color("glass"))

func tree(parent: Node3D, at: Vector3, height: float) -> void:
	host._cylinder(parent,0.038,height*0.65,at+Vector3.UP*height*0.325,color("timber"),0.022)
	for i in 5:
		var angle := float(i)*TAU/5.0
		var point := at+Vector3(cos(angle)*0.12,height*(0.55+float(i%2)*0.12),sin(angle)*0.12)
		var branch: MeshInstance3D = host._cylinder(parent,0.018,0.23,point-Vector3.UP*0.09,color("timber"),0.008)
		branch.rotation_degrees = Vector3(sin(angle)*35,0,cos(angle)*35)
		blob(parent,point,Vector3(0.27,0.3,0.27),color("leaf_light") if i%2==0 else color("leaf"))
	blob(parent,at+Vector3.UP*height*0.85,Vector3(0.28,0.3,0.28),color("leaf_light"))

