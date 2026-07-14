class_name MapTheme
extends RefCounted
## Terrain/theme routing helpers for ground, structure, decor, and biome lookup.

enum LayerKind { GROUND, STRUCTURE, DECOR }

const _GROUND_OVERLAY_TERRAINS := {
	"castle": true,
	"village": true,
	"barracks": true,
	"gate": true,
}

const _STRUCTURE_SOURCE_KEYS := {
	"castle": true,
	"village": true,
	"barracks": true,
	"gate": true,
	"castle_floor": true,
	"castle_wall": true,
	"castle_throne": true,
	"castle_stairs": true,
	"castle_vault": true,
	"castle_door": true,
}


static func layer_for_cell(terrain: String, subtype: String) -> int:
	var lookup_key := source_lookup_key(terrain, subtype)
	if _STRUCTURE_SOURCE_KEYS.has(lookup_key):
		return LayerKind.STRUCTURE
	return LayerKind.GROUND


static func ground_lookup_key(terrain: String, subtype: String = "") -> String:
	if terrain == "castle" and subtype != "":
		return "castle"
	if _GROUND_OVERLAY_TERRAINS.has(terrain):
		return "plain"
	return terrain


static func source_lookup_key(terrain: String, subtype: String) -> String:
	if subtype != "":
		return subtype
	return terrain


static func uses_shared_source(terrain_key: String) -> bool:
	return Config.FE8_TILE_COORDS.has(terrain_key)


static func uses_biome(terrain_key: String) -> bool:
	return terrain_key in Config.BIOME_AWARE_TERRAINS and not uses_shared_source(terrain_key)


static func source_lookup_biome(terrain_key: String, biome: String) -> String:
	if not uses_biome(terrain_key):
		return ""
	if biome in Config.BIOMES:
		return biome
	return Config.DEFAULT_BIOME


static func source_registration_biomes(terrain_key: String) -> Array:
	if uses_shared_source(terrain_key):
		var aliases: Array = [""]
		if terrain_key in Config.BIOME_AWARE_TERRAINS:
			for biome in Config.BIOMES:
				aliases.append(biome)
		return aliases
	if uses_biome(terrain_key):
		return Config.BIOMES.duplicate()
	return [""]
