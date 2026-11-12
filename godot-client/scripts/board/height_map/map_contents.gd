extends Node3D
## 正式地图与试验场共用地貌、单位呈现；所有根节点锚定逻辑格顶面。
const TextureHelper = preload("res://scripts/core/texture_loader.gd")
const UnitAnchor = preload("res://scripts/board/height_map/unit_anchor.gd")
const DetailModels = preload("res://scripts/board/height_map/detail_models.gd")
var details := Node3D.new()
var detail_models: RefCounted

var model: RefCounted
var features := Node3D.new()
var units := Node3D.new()
var unit_nodes: Dictionary = {}
var texture_cache: Dictionary = {}
var material_cache: Dictionary = {}
var feature_counts: Dictionary = {}

func setup(map_model: RefCounted) -> void:
	model = map_model
	detail_models = DetailModels.new(self)
	details.name = "TerrainDetails"
	add_child(details)
	features.name = "Features"
	units.name = "PresetUnits"
	add_child(features)
	add_child(units)
	units.visibility_changed.connect(_sync_unit_collisions)

func rebuild() -> void:
	rebuild_features()
	rebuild_units()

func rebuild_features() -> void:
	detail_models.rebuild(details, model)
	for child in features.get_children():
		child.free()
	feature_counts.clear()
	for y in model.size().y:
		for x in model.size().x:
			var p := Vector2i(x,y)
			var feature: String = model.cell(p).get("feature", "")
			if not feature.is_empty():
				_build_feature(p, feature)

func rebuild_units() -> void:
	var previous: Dictionary = {}
	for child in units.get_children():
		var uid := int(child.get_meta("unit",{}).get("id",-1))
		if uid>=0:
			previous[uid] = child
			units.remove_child(child)
		else:
			child.free()
	unit_nodes.clear()
	for entry in model.units:
		_build_unit(entry)
		var uid := int(entry.get("id",-1))
		if previous.has(uid):
			var p := Vector2i(int(entry.x),int(entry.y))
			var fresh: Node3D = unit_nodes[p].anchor
			var retained: Node3D = previous[uid]
			previous.erase(uid)
			for child in retained.get_children():
				child.free()
			for child in fresh.get_children():
				fresh.remove_child(child)
				retained.add_child(child)
			retained.position = fresh.position
			retained.unit_data = entry.duplicate(true)
			retained.set_meta("unit",entry.duplicate(true))
			fresh.free()
			units.add_child(retained)
			unit_nodes[p].anchor = retained
	for removed in previous.values():
		removed.free()
	_sync_unit_collisions()

func _sync_unit_collisions() -> void:
	# 显隐与拾取一致：隐藏的单位不能变成挡住建筑的“空气墙”。
	for anchor in units.get_children():
		for child in anchor.get_children():
			if child is CollisionObject3D:
				child.collision_layer = 1 if units.visible else 0

func _material(color: Color) -> StandardMaterial3D:
	var key := color.to_html()
	if not material_cache.has(key):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.9
		material_cache[key] = material
	return material_cache[key]

func _color(key: String) -> Color:
	return Color(String(model.rules.palette[key]))

func _mesh(parent: Node3D, mesh: Mesh, position: Vector3, color: Color) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.material_override = _material(color)
	parent.add_child(instance)
	return instance

func _box(parent: Node3D, dimensions: Vector3, position: Vector3, color: Color) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = dimensions
	return _mesh(parent,mesh,position,color)

func _cylinder(parent: Node3D, radius: float, height: float, position: Vector3, color: Color, top_radius: float = -1) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.bottom_radius = radius
	mesh.top_radius = radius if top_radius < 0 else top_radius
	mesh.height = height
	mesh.radial_segments = 8
	return _mesh(parent,mesh,position,color)

func _roof(parent: Node3D, width: float, height: float, depth: float, position: Vector3, color: Color) -> void:
	var roof := PrismMesh.new()
	roof.size = Vector3(width,height,depth)
	_mesh(parent,roof,position,color)

func _flag(parent: Node3D, position: Vector3, color: Color) -> void:
	var flag := Node3D.new()
	flag.name = "OwnerFlag"
	flag.position = position
	flag.set_meta("color",color)
	parent.add_child(flag)
	_cylinder(flag,0.018,0.65,Vector3.UP*0.325,_color("wood"))
	_box(flag,Vector3(0.25,0.17,0.025),Vector3(0.12,0.53,0),color)

func _build_feature(p: Vector2i, kind: String) -> void:
	var anchor := Node3D.new()
	anchor.name = "%s_%d_%d" % [kind,p.x,p.y]
	anchor.position = model.surface(p)
	anchor.set_meta("cell", p)
	anchor.set_meta("feature", kind)
	features.add_child(anchor)
	feature_counts[kind] = int(feature_counts.get(kind,0)) + 1
	var faction: String = model.cell(p).get("faction", "neutral")
	var color := Color(String(model.rules.factions[faction].color))
	match kind:
		"castle": _castle(anchor,color)
		"village": _village(anchor)
		"barracks": _barracks(anchor,color)
		"wall": _box(anchor,Vector3(0.92,0.85,0.32),Vector3(0,0.425,0),_color("wall"))
		"gate":
			for x in [-0.34,0.34]:
				_box(anchor,Vector3(0.22,0.9,0.4),Vector3(x,0.45,0),_color("wall"))
			_box(anchor,Vector3(0.88,0.18,0.4),Vector3(0,0.85,0),_color("wall"))
		"bridge":
			for z in range(7):
				_box(anchor,Vector3(0.78,0.06,0.12),Vector3(0,0.08,-0.42+z*0.14),_color("wood"))
		"road":
			for z in range(3):
				_box(anchor,Vector3(0.65,0.025,0.24),Vector3(0,0.02,-0.28+z*0.28),_color("stone"))
		"stairs":
			for z in range(4):
				_box(anchor,Vector3(0.8,0.08*(z+1),0.2),Vector3(0,0.04*(z+1),-0.3+z*0.2),_color("stone"))
		"vault": _box(anchor,Vector3(0.48,0.36,0.34),Vector3(0,0.18,0),_color("wood"))
		"forest": _forest(anchor,p)
	if kind == "village":
		_flag(anchor,Vector3(0.3,0.15,0.2),color)
	# 建筑/树木作为格子点击目标；碰撞不参与正式战斗。
	var height: float = float(model.rules.get("feature_heights",{}).get(kind,1.1 if kind=="castle" else 0.8))
	var body := StaticBody3D.new()
	body.set_meta("cell",p)
	body.set_meta("content",true)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.8,height,0.8)
	shape.shape = box
	shape.position.y = height*0.5
	body.add_child(shape)
	anchor.add_child(body)

func _castle(parent: Node3D, color: Color) -> void:
	_box(parent,Vector3(0.86,0.08,0.86),Vector3(0,0.04,0),_color("stone"))
	_box(parent,Vector3(0.49,0.45,0.46),Vector3(0,0.3,-0.09),_color("wall"))
	_roof(parent,0.58,0.27,0.57,Vector3(0,0.64,-0.09),_color("roof"))
	for x in [-0.32,0.32]:
		for z in [-0.30,0.30]:
			_cylinder(parent,0.13,0.56,Vector3(x,0.36,z),_color("stone"))
			_cylinder(parent,0.17,0.23,Vector3(x,0.75,z),_color("roof"),0)
	_box(parent,Vector3(0.16,0.24,0.025),Vector3(0,0.2,0.15),_color("door"))
	_flag(parent,Vector3(0,0.76,-0.12),color)
	detail_models.castle(parent)

func _house(parent: Node3D, position: Vector3, scale_factor: float) -> void:
	var house := Node3D.new()
	house.position = position
	house.scale = Vector3.ONE * scale_factor
	parent.add_child(house)
	_box(house,Vector3(0.46,0.34,0.43),Vector3(0,0.17,0),_color("wall"))
	_roof(house,0.57,0.25,0.55,Vector3(0,0.45,0),_color("roof"))
	_box(house,Vector3(0.1,0.18,0.02),Vector3(0,0.09,0.225),_color("door"))
	_box(house,Vector3(0.08,0.08,0.02),Vector3(0.14,0.23,0.225),_color("window"))
	_box(house,Vector3(0.07,0.23,0.09),Vector3(-0.13,0.49,-0.05),_color("stone"))
	detail_models.house(house)

func _village(parent: Node3D) -> void:
	_box(parent,Vector3(0.85,0.035,0.85),Vector3(0,0.018,0),_color("stone"))
	_house(parent,Vector3(-0.19,0.04,-0.16),0.95)
	_house(parent,Vector3(0.22,0.04,0.21),0.7)
	_cylinder(parent,0.11,0.14,Vector3(-0.22,0.1,0.25),_color("wood"))

func _barracks(parent: Node3D, color: Color) -> void:
	_box(parent,Vector3(0.85,0.04,0.85),Vector3(0,0.02,0),_color("wood"))
	_roof(parent,0.61,0.48,0.62,Vector3(-0.1,0.29,-0.12),_color("canvas"))
	_roof(parent,0.22,0.31,0.025,Vector3(-0.1,0.22,0.205),_color("door"))
	_flag(parent,Vector3(0.30,0.04,-0.28),color)
	_box(parent,Vector3(0.17,0.17,0.17),Vector3(0.28,0.12,0.25),_color("wood"))
	_cylinder(parent,0.07,0.24,Vector3(0.19,0.16,0.04),_color("stone"))

func _forest(parent: Node3D, p: Vector2i) -> void:
	for i in 2:
		var x := -0.19 if i == 0 else 0.2
		var z := -0.14 if i == 0 else 0.16
		var height := 0.62 + float((p.x+p.y+i)%3)*0.07
		detail_models.tree(parent,Vector3(x,0,z),height)

func _build_unit(entry: Dictionary) -> void:
	var p := Vector2i(int(entry.x),int(entry.y))
	var anchor := UnitAnchor.new()
	anchor.unit_data = entry.duplicate(true)
	anchor.name = "%s_%s_%d_%d" % [entry.color,entry.type,p.x,p.y]
	anchor.position = model.surface(p)
	anchor.set_meta("unit",entry.duplicate(true))
	units.add_child(anchor)
	var color := Color(String(model.rules.factions[entry.color].color))
	_cylinder(anchor,0.29,0.025,Vector3(0,0.022,0),color)
	var asset_path: String = model.rules.unit_textures.get(entry.type,"res://assets/unit_portraits/portrait_%s.png" % entry.type)
	var hero: String = str(entry.get("hero_id","")) if entry.get("hero_id") != null else ""
	if not hero.is_empty() and ResourceLoader.exists("res://assets/heroes/%s.png" % hero):
		asset_path = "res://assets/heroes/%s.png" % hero
	if not ResourceLoader.exists(asset_path):
		asset_path = "res://assets/classic/%s.png" % entry.type
	if not ResourceLoader.exists(asset_path):
		asset_path = String(model.rules.unit_textures.swordsman)
	if not texture_cache.has(asset_path):
		texture_cache[asset_path] = TextureHelper.load_resized(asset_path,int(model.rules.unit_texture_limit))
	var texture: Texture2D = texture_cache[asset_path]
	var sprite := Sprite3D.new()
	sprite.texture = texture
	sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	sprite.shaded = false
	if entry.get("has_acted",false):
		sprite.modulate = Color(0.6,0.6,0.6)
	if texture:
		sprite.pixel_size = float(model.rules.unit_height) / float(texture.get_height())
	sprite.position.y = float(model.rules.unit_height)*0.5 + 0.035
	# 佣兵站有驻军时，角色移到同一格的前沿，避免帐篷吞掉下半身。
	if not String(model.cell(p).get("feature", "")).is_empty():
		sprite.position += Vector3(0.22,0,0.22)
	anchor.add_child(sprite)
	if int(entry.get("hp",-1))>=0 and int(entry.get("max_hp",-1))>0:
		var label := Label3D.new()
		label.name = "HealthLabel"
		label.text = "%d/%d" % [int(entry.hp),int(entry.max_hp)]
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.font_size = 32
		label.outline_size = 8
		label.pixel_size = 0.0055
		label.position.y = float(model.rules.unit_height)+0.2
		anchor.add_child(label)
	_add_unit_badges(anchor,entry)
	var body := StaticBody3D.new()
	body.set_meta("cell",p)
	body.set_meta("content",true)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.42,float(model.rules.unit_height),0.42)
	shape.position = sprite.position
	shape.shape = box
	body.add_child(shape)
	anchor.add_child(body)
	unit_nodes[p] = {"anchor":anchor,"sprite":sprite}

func _add_unit_badges(anchor: Node3D, entry: Dictionary) -> void:
	var pieces: Array[String] = ["Lv%d" % int(entry.get("level",1))]
	if entry.has("mp"):
		pieces.append("MP%d" % int(entry.mp))
	if int(entry.get("morale",0))>0:
		pieces.append("★%d" % int(entry.morale))
	var status: Array[String] = []
	for effect in entry.get("status_effects",[]):
		if effect is Dictionary:
			status.append(str(model.rules.get("status_labels",{}).get(effect.get("type",""),effect.get("type",""))))
	if int(entry.get("silence_until_turn",0))>0 and status.is_empty():
		status.append("沉默")
	if not status.is_empty():
		pieces.append("/".join(status))
	var label := Label3D.new()
	label.name = "UnitBadge"
	label.text = " · ".join(pieces)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.position.y = 0.12
	label.pixel_size = 0.003
	label.font_size = 28
	label.outline_size = 8
	anchor.add_child(label)
	var team: String = str(entry.get("team","")) if entry.get("team") != null else ""
	if model.rules.get("team_colors",{}).has(team):
		var badge := Label3D.new()
		badge.name = "TeamBadge"
		badge.text = team.trim_prefix("team_").to_upper()
		badge.modulate = Color(str(model.rules.team_colors[team]))
		badge.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		badge.position = Vector3(0.3,float(model.rules.unit_height)+0.03,0)
		badge.pixel_size = 0.006
		badge.font_size = 32
		badge.outline_size = 8
		anchor.add_child(badge)

func select(p: Vector2i, xray: bool) -> void:
	for coordinate in unit_nodes:
		unit_nodes[coordinate].sprite.no_depth_test = xray and coordinate == p
