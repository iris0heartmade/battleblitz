extends RefCounted
## 逻辑格到高差舞台的适配。保留原terrain/subtype，表现不改变通行规则。
const TERRAINS := ["grass", "rock", "sand", "water"]
var settings: Dictionary
var rules: Dictionary
var cells: Array = []
var units: Array = []

func _init() -> void:
	settings = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/geometry.json"))
	rules = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/catalog.json"))
	var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/presentation.json"))
	settings.merge(profile.camera,true)
	rules.factions.merge(profile.factions,true)
	rules.unit_textures.merge(profile.unit_textures,true)
	rules.team_colors = profile.team_colors
	rules.status_labels = profile.status_labels
	rules.feature_heights = profile.feature_heights
	rules.merge({"terrain_profiles":profile.terrains},true)

func size() -> Vector2i:
	return Vector2i(int(settings.width),int(settings.depth))

func contains(p: Vector2i) -> bool:
	return p.x>=0 and p.y>=0 and p.x<size().x and p.y<size().y

func cell(p: Vector2i) -> Dictionary:
	return cells[p.y*size().x+p.x]

func elevation(p: Vector2i) -> int:
	return int(cell(p).height)

func surface(p: Vector2i) -> Vector3:
	return Vector3(p.x*float(settings.cell_size),elevation(p)*float(settings.height_step),p.y*float(settings.cell_size))

func load_cells(dimensions: Vector2i, lookup: Dictionary, biome: String, elevations: Array = []) -> void:
	settings.width = dimensions.x
	settings.depth = dimensions.y
	cells.clear()
	for y in dimensions.y:
		for x in dimensions.x:
			var source: Dictionary = lookup.get(Vector2i(x,y),{"terrain":"plain","subtype":""})
			var terrain := String(source.get("terrain","plain"))
			var subtype := str(source.subtype) if source.get("subtype") != null else ""
			var profile: Dictionary = rules.terrain_profiles.get(subtype,rules.terrain_profiles.get(terrain,rules.terrain_profiles.plain))
			var entry: Dictionary = profile.duplicate(true)
			if biome == "desert" and entry.terrain == "grass":
				entry.terrain = "sand"
			if biome == "snow" and entry.terrain == "grass":
				entry.terrain = "rock"
			entry.source_terrain = terrain
			entry.subtype = subtype
			entry.faction = "neutral"
			if y<elevations.size() and elevations[y] is Array and x<elevations[y].size():
				entry.height = clampi(int(elevations[y][x]),int(settings.min_height),int(settings.max_height))
			elif source.get("elevation") != null:
				entry.height = clampi(int(source.elevation),int(settings.min_height),int(settings.max_height))
			cells.append(entry)

func normalize_units(entries: Array) -> Array:
	var normalized: Array = []
	for source in entries:
		if not source is Dictionary or int(source.get("hp",1))<=0:
			continue
		var entry: Dictionary = source.duplicate(true)
		entry.type = str(entry.get("unit_type",entry.get("type","swordsman")))
		entry.color = str(entry.get("color","red"))
		var p := Vector2i(int(entry.get("x",-1)),int(entry.get("y",-1)))
		if contains(p):
			normalized.append(entry)
	return normalized
