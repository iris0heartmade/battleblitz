extends Node


func _ready() -> void:
	var failed := 0
	var ts := TileSetBuilder.build()
	var checks := {
		"plain|": ["res://assets/tilesets/base_terrain_roads.png", Vector2i(0, 0)],
		"road|": ["res://assets/tilesets/base_terrain_roads.png", Vector2i(0, 1)],
		"village|": ["res://assets/tilesets/village_castle_mountains.png", Vector2i(0, 0)],
		"forest|grass": ["res://assets/tilesets/trees_mountains.png", Vector2i(0, 0)],
	}
	var variant_checks := {
		"plain|grass": 4,
		"desert|desert": 4,
		"snow|snow": 4,
		"road|grass": 4,
		"forest|grass": 4,
		"forest|snow": 4,
		"forest|desert": 4,
		"village|": 4,
		"castle|grass": 2,
		"castle|desert": 2,
		"castle|snow": 2,
		"mountain|grass": 4,
		"mountain|desert": 4,
		"snow_peak|snow": 8,
	}
	for key in checks.keys():
		var parts := String(key).split("|", false)
		var terrain := String(parts[0])
		var biome := String(parts[1]) if parts.size() > 1 else ""
		var sid := TileSetBuilder.source_id_for(terrain, biome)
		if sid < 0:
			print("FAIL missing source id: %s" % key)
			failed += 1
			continue
		var source := ts.get_source(sid)
		if not (source is TileSetAtlasSource):
			print("FAIL source is not atlas: %s" % key)
			failed += 1
			continue
		var atlas_source: TileSetAtlasSource = source
		var expected: Array = checks[key]
		if atlas_source.resource_name != String(expected[0]):
			print("FAIL path %s got %s expected %s" % [key, atlas_source.resource_name, String(expected[0])])
			failed += 1
		var coords_for_key: Array = TileSetBuilder.atlas_coords_for(terrain, biome)
		if not coords_for_key.has(expected[1]):
			print("FAIL coord pool %s missing %s from %s" % [key, str(expected[1]), str(coords_for_key)])
			failed += 1
		elif not atlas_source.has_tile(expected[1]):
			print("FAIL atlas tile missing %s at %s" % [key, str(expected[1])])
			failed += 1
	for key in variant_checks.keys():
		var parts := String(key).split("|", false)
		var terrain := String(parts[0])
		var biome := String(parts[1]) if parts.size() > 1 else ""
		var coords: Array = TileSetBuilder.atlas_coords_for(terrain, biome)
		var expected_count: int = int(variant_checks[key])
		if coords.size() != expected_count:
			print("FAIL variant count %s got %d expected %d: %s" % [key, coords.size(), expected_count, str(coords)])
			failed += 1
	var seen_plain := {}
	for x in range(8):
		var coord := TileSetBuilder.atlas_coord_for("plain", "grass", x, 0)
		seen_plain[coord] = true
	if seen_plain.size() < 2:
		print("FAIL plain grass should vary across map cells: %s" % str(seen_plain.keys()))
		failed += 1
	var seen_forest := {}
	for x in range(8):
		var coord := TileSetBuilder.atlas_coord_for("forest", "grass", x, 1)
		seen_forest[coord] = true
	if seen_forest.size() < 2:
		print("FAIL forest grass should vary across map cells: %s" % str(seen_forest.keys()))
		failed += 1
	if failed > 0:
		get_tree().quit(1)
	else:
		print("PASS tileset atlas mapping")
		get_tree().quit(0)
