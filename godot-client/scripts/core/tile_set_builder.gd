class_name TileSetBuilder
extends RefCounted
## TileSetBuilder — programmatic TileSet assembly at runtime.
##
## Two source families:
##   1. **FE8 overworld atlas** (`res://assets/tiles_fe8/overworld_fe8.png`,
##      512×512, 32×32 sub-tiles of 16×16) — a single `TileSetAtlasSource`
##      that holds the whole world-map tilemap. All 19 FE8-aware
##      BattleBlitz terrains (plain, forest, mountain, river, castle,
##      village, ...) point into this one atlas. Batch 2 will switch
##      to `add_terrain_set()` bitmask autotiling on top of this.
##   2. **Legacy per-terrain PNGs** (`res://assets/tiles/*.png`,
##      48×48 each) — one `TileSetAtlasSource` per terrain for the
##      few BattleBlitz terrains that don't have an FE8 overworld
##      equivalent (currently only `bridge` and `snow_peak`).
##
## Why a runtime builder rather than hand-edited `.tres`:
##   - 19+ sources × terrain metadata is tedious to hand-edit.
##   - Future swaps of the master tilemap are a one-line Config edit.
##   - We can always export the built TileSet to a `.tres` later.
##
## Conventions:
##   - Source ID 0 = the shared FE8 atlas (always first).
##   - Source IDs 1..N = legacy per-terrain atlases, registered in
##     `Config.TERRAIN_VARIANT_COUNTS` order for determinism.
##   - `SOURCE_IDS["{terrain}|{biome}"]` → source_id.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const MAP_THEME_SCRIPT := preload("res://scripts/core/map_theme.gd")
const TILE_SIZE := MAP_METRICS_SCRIPT.TILE_SIZE
const TILES_DIR := "res://assets/tiles"
const TILESETS_DIR := "res://assets/tilesets"
const _TERRAIN_ASSET_FALLBACKS := {
	"bridge": ["road", "river"],
	"snow_peak": ["mountain"],
	"castle": ["castle_floor"],
	"gate": ["castle_door", "road"],
	"village": ["plain"],
	"barracks": ["plain"],
}

# Populated by `build()`. Keyed by "{terrain}|{biome}" → source_id.
static var SOURCE_IDS: Dictionary = {}
static var _using_fe8_atlas := false
static var ATLAS_COORDS: Dictionary = {}
static var ATLAS_COORD_LISTS: Dictionary = {}

# Cache the built TileSet across calls so we don't rebuild every frame.
static var _cached: TileSet = null


# ============================================================
# Public entry points
# ============================================================

## Build (or return cached) TileSet.
static func build() -> TileSet:
	if _cached != null:
		return _cached
	SOURCE_IDS.clear()
	ATLAS_COORDS.clear()
	ATLAS_COORD_LISTS.clear()
	_using_fe8_atlas = false

	var ts := TileSet.new()
	ts.tile_size = TILE_SIZE

	# 1. The shared FE8 overworld atlas. This is source_id 0. Each
	#    BattleBlitz terrain that has an entry in Config.FE8_TILE_COORDS
	#    points into this atlas at its (col, row) tile coord. We register
	#    one tile per terrain (the CENTER of the 4×4 autotile block);
	#    batch 2 will register the surrounding 15 transition tiles and
	#    wire them into a `TileSetTerrain` with bitmask autotiling.
	var fe8_source := _build_fe8_atlas_source(ts) if Config.USE_FE8_ATLAS else null
	if fe8_source != null:
		_using_fe8_atlas = true
		var fe8_source_id := ts.add_source(fe8_source)
		# The FE8 atlas is biome-agnostic (the master tilemap doesn't
		# have separate biome palettes). Register under "" AND every
		# known biome so the MapLoader's `source_id_for(terrain, biome)`
		# lookup hits whether the caller passes a biome or not.
		for terrain in Config.FE8_TILE_COORDS.keys():
			for biome in MAP_THEME_SCRIPT.source_registration_biomes(String(terrain)):
				SOURCE_IDS["%s|%s" % [terrain, biome]] = fe8_source_id

	if Config.USE_TILESET_ATLASES:
		_register_configured_atlases(ts)

	# 2. Legacy per-terrain atlases for non-FE8 terrains. Registered in
	#    Config.TERRAIN_VARIANT_COUNTS order so the source IDs are
	#    deterministic.
	for terrain in Config.TERRAIN_VARIANT_COUNTS.keys():
		if _using_fe8_atlas and terrain in Config.FE8_TILE_COORDS:
			continue  # already handled by the FE8 atlas
		for biome in _legacy_registration_biomes(String(terrain)):
			if SOURCE_IDS.has("%s|%s" % [terrain, biome]):
				continue
			if SOURCE_IDS.has("%s|" % terrain):
				continue
			var source := _build_legacy_source_for(terrain, String(biome))
			if source == null:
				continue
			var source_id := ts.add_source(source)
			SOURCE_IDS["%s|%s" % [terrain, biome]] = source_id
			if String(biome) == Config.DEFAULT_BIOME:
				SOURCE_IDS["%s|" % terrain] = source_id

	_cached = ts
	return ts

## Look up the source_id for (terrain, biome). Returns -1 if unknown.
static func source_id_for(terrain: String, biome: String) -> int:
	return int(SOURCE_IDS.get("%s|%s" % [terrain, biome], -1))

static func uses_fe8_atlas() -> bool:
	return _using_fe8_atlas

static func atlas_coord_for(terrain: String, biome: String, x: int = 0, y: int = 0) -> Vector2i:
	var key := _atlas_lookup_key(terrain, biome)
	if key == "":
		return Vector2i(-1, -1)
	var coords: Array = ATLAS_COORD_LISTS.get(key, [])
	if coords.is_empty():
		return ATLAS_COORDS.get(key, Vector2i(-1, -1))
	var idx := _pick_atlas_variant(terrain, biome, x, y, coords.size())
	return Vector2i(coords[idx])

static func atlas_coords_for(terrain: String, biome: String) -> Array:
	var key := _atlas_lookup_key(terrain, biome)
	if key == "":
		return []
	return (ATLAS_COORD_LISTS.get(key, []) as Array).duplicate()

static func _legacy_registration_biomes(terrain: String) -> Array:
	if terrain in Config.BIOME_AWARE_TERRAINS:
		return Config.BIOMES.duplicate()
	return [""]

static func _atlas_lookup_key(terrain: String, biome: String) -> String:
	var exact_key := "%s|%s" % [terrain, biome]
	if ATLAS_COORDS.has(exact_key):
		return exact_key
	if biome == "":
		var default_key := "%s|%s" % [terrain, Config.DEFAULT_BIOME]
		if ATLAS_COORDS.has(default_key):
			return default_key
	var generic_key := "%s|" % terrain
	if ATLAS_COORDS.has(generic_key):
		return generic_key
	return ""

static func _pick_atlas_variant(terrain: String, biome: String, x: int, y: int, count: int) -> int:
	if count <= 1:
		return 0
	var h: int = 0
	var seed := "%s|%s" % [terrain, biome]
	for c in seed:
		h = (h * 31 + c.unicode_at(0)) & 0x7FFFFFFF
	h = (h ^ (x * 73856093) ^ (y * 19349663)) & 0x7FFFFFFF
	return h % count

## Returns the atlas coord for a terrain when the FE8 atlas is the
## source. Pulls the (col, row) lookup from `Config.FE8_TILE_COORDS`.
## Returns `Vector2i(-1, -1)` for non-FE8 terrains.
##
## For the 4 main autotileable terrains (plain / forest / mountain /
## river), this returns the CENTER tile of the 4×4 block. Godot
## handles the actual displayed tile via TerrainSet bitmask autotiling
## once the cell's neighbors are evaluated.
static func fe8_atlas_coord_for(terrain: String) -> Vector2i:
	if not Config.FE8_TILE_COORDS.has(terrain):
		return Vector2i(-1, -1)
	return Config.FE8_TILE_COORDS[terrain]

## Persist the built TileSet to disk. Useful for shipping (skip the
## runtime cost on first frame) and for visual diff in the editor.
static func export_to_tres(path: String) -> int:
	var ts := build()
	var err := ResourceSaver.save(ts, path)
	return err


# ============================================================
# Source construction
# ============================================================

## Build the single shared FE8 atlas source. The texture is the
## 512×512 master tilemap upscaled 3× to 1536×1536 with NEAREST so
## each 16×16 sub-tile becomes a 48×48 region. `texture_region_size`
## is 48×48, so a 32×32 sub-tile grid is exposed to the TileMapLayer.
##
## Also configures a `TileSetTerrain` (one per autotileable terrain
## in `Config.FE8_TERRAIN_BLOCK_ORIGINS`). Each terrain's 4×4 block
## of 16 sub-tiles has its `terrain_peering_bits` set so Godot can
## auto-blend edges at render time.
static func _build_fe8_atlas_source(ts: TileSet) -> TileSetAtlasSource:
	var path := Config.FE8_ATLAS_PATH
	var img := _try_load_image(path)
	if img == null:
		push_warning("TileSetBuilder: FE8 atlas missing at %s — falling back to legacy" % path)
		return null
	# Convert to RGBA8 for blit_rect compatibility, then NEAREST scale 3×.
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var scaled_size := Vector2i(Config.FE8_ATLAS_SIZE.x * (TILE_SIZE.x / Config.FE8_TILE_SIZE.x),
		Config.FE8_ATLAS_SIZE.y * (TILE_SIZE.y / Config.FE8_TILE_SIZE.y))
	# 512 * (48 / 16) = 1536. In Godot 4, `Image.resize()` is in-place
	# and returns void. Pass `0` for INTERPOLATION_NEAREST (the integer
	# constant, which the static analyser can't see via `Image.`).
	var src_dup: Image = img.duplicate()
	src_dup.resize(scaled_size.x, scaled_size.y, 0)
	var tex := ImageTexture.create_from_image(src_dup)
	var source := TileSetAtlasSource.new()
	source.texture = tex
	source.texture_region_size = TILE_SIZE
	# Register every (col, row) cell of the 32×32 grid so the MapLoader
	# can set_cell with any (col, row) in the FE8 atlas.
	var cols := Config.FE8_ATLAS_SIZE.x / Config.FE8_TILE_SIZE.x
	var rows := Config.FE8_ATLAS_SIZE.y / Config.FE8_TILE_SIZE.y
	for row in rows:
		for col in cols:
			source.create_tile(Vector2i(col, row))
	source.set_name("fe8_overworld")

	# Configure the autotile TerrainSet. One set, one terrain per
	# autotileable BattleBlitz terrain.
	ts.add_terrain_set()
	var terrain_set_id: int = 0
	var terrain_id_by_name: Dictionary = {}
	var terrain_id: int = 0
	for terrain in Config.FE8_TERRAIN_BLOCK_ORIGINS.keys():
		ts.add_terrain(terrain_set_id)
		ts.set_terrain_name(terrain_set_id, terrain_id, String(terrain))
		terrain_id_by_name[terrain] = terrain_id
		terrain_id += 1
	# For each of the 16 sub-tiles in the 4×4 autotile block, set
	# its `terrain_set`, `terrain`, and `terrain_peering_bits`.
	for terrain in Config.FE8_TERRAIN_BLOCK_ORIGINS.keys():
		var origin: Vector2i = Config.FE8_TERRAIN_BLOCK_ORIGINS[terrain]
		var tid: int = int(terrain_id_by_name[terrain])
		for i in Config.AUTOTILE_PEERING_BITS.size():
			var col_off: int = i % 4
			var row_off: int = i / 4
			var atlas_coord := Vector2i(origin.x + col_off, origin.y + row_off)
			var tile_data: TileData = source.get_tile_data(atlas_coord, 0)
			if tile_data == null:
				continue
			tile_data.terrain_set = terrain_set_id
			tile_data.terrain = tid
			# `set_terrain_peering_bit(peering_index, bit)` sets the
			# bit to true (Godot 4's TileData API only has a setter
			# for the "same terrain" state — there's no explicit
			# "false" setter since unset bits default to false).
			# For 4-bit autotile (NSEW), the bitmask is the same
			# for all 4 corners.
			var bits: int = Config.AUTOTILE_PEERING_BITS[i]
			for corner in 4:    # 0=TL, 1=TR, 2=BR, 3=BL
				for dir in 4:  # 0=N, 1=E, 2=S, 3=W
					if ((bits >> dir) & 1) == 1:
						tile_data.set_terrain_peering_bit(corner, dir)
	return source

## Register labeled 48px-grid atlas sheets before falling back to
## legacy per-terrain PNGs.
static func _register_configured_atlases(ts: TileSet) -> void:
	var source_id_by_path: Dictionary = {}
	_register_labeled_atlases(ts, source_id_by_path)
	for key in Config.TILESET_ATLAS_COORDS.keys():
		if SOURCE_IDS.has(key):
			continue
		var entry: Dictionary = Config.TILESET_ATLAS_COORDS[key]
		var path := String(entry.get("path", ""))
		if path == "":
			continue
		var source_id: int = -1
		if source_id_by_path.has(path):
			source_id = int(source_id_by_path[path])
		else:
			var source := _build_grid_atlas_source(path)
			if source == null:
				continue
			source_id = ts.add_source(source)
			source_id_by_path[path] = source_id
		var coord: Vector2i = entry.get("coord", Vector2i(-1, -1))
		var source_for_check: TileSetAtlasSource = ts.get_source(source_id) as TileSetAtlasSource
		if source_for_check == null or not source_for_check.has_tile(coord):
			push_warning("TileSetBuilder: atlas %s has no tile at %s for %s" % [path, str(coord), key])
			continue
		_register_atlas_key(key, source_id, coord)


static func _register_labeled_atlases(ts: TileSet, source_id_by_path: Dictionary) -> void:
	var dir := DirAccess.open(TILESETS_DIR)
	if dir == null:
		return
	dir.list_dir_begin()
	while true:
		var name := dir.get_next()
		if name == "":
			break
		if dir.current_is_dir() or not name.ends_with(".txt"):
			continue
		var stem := name.substr(0, name.length() - 4)
		var image_path := "%s/%s.png" % [TILESETS_DIR, stem]
		var text_path := "%s/%s" % [TILESETS_DIR, name]
		if not FileAccess.file_exists(image_path):
			continue
		var source_id: int = -1
		if source_id_by_path.has(image_path):
			source_id = int(source_id_by_path[image_path])
		else:
			var source := _build_grid_atlas_source(image_path)
			if source == null:
				continue
			source_id = ts.add_source(source)
			source_id_by_path[image_path] = source_id
		_register_labels_from_file(text_path, source_id)
	dir.list_dir_end()


static func _register_labels_from_file(text_path: String, source_id: int) -> void:
	var file := FileAccess.open(text_path, FileAccess.READ)
	if file == null:
		return
	var rows := file.get_as_text().strip_edges().split("\n", false)
	file.close()
	for y in range(rows.size()):
		var labels := _labels_from_row(String(rows[y]))
		for x in range(labels.size()):
			var coord := Vector2i(x, y)
			for key in _atlas_keys_for_label(String(labels[x]), y):
				_register_atlas_key(key, source_id, coord)


static func _labels_from_row(row: String) -> Array[String]:
	var out: Array[String] = []
	var pieces := row.split("【", false)
	for piece in pieces:
		var end_idx := String(piece).find("】")
		if end_idx < 0:
			continue
		var label := String(piece).substr(0, end_idx).strip_edges()
		if label != "":
			out.append(label)
	return out


static func _atlas_keys_for_label(label: String, row: int) -> Array[String]:
	var keys: Array[String] = []
	if label.contains("道路"):
		if row == 1:
			keys.append("road|grass")
		elif row == 3:
			keys.append("road|desert")
		elif row == 5:
			keys.append("road|snow")
		return keys
	if label.begins_with("草原") and not label.contains("森林"):
		keys.append("plain|grass")
		return keys
	if label.contains("草原森林"):
		keys.append("forest|grass")
		return keys
	if label.contains("雪地森林"):
		keys.append("forest|snow")
		return keys
	if label.contains("沙漠树"):
		keys.append("forest|desert")
		return keys
	if label.begins_with("沙漠"):
		keys.append("desert|desert")
		return keys
	if label.begins_with("雪地") and not label.contains("森林"):
		keys.append("snow|snow")
		return keys
	if label.begins_with("村庄"):
		keys.append("village|")
		return keys
	if label.begins_with("佣兵站"):
		keys.append(_biome_key_for_row("barracks", row))
		return keys
	if label.begins_with("城堡"):
		keys.append(_biome_key_for_row("castle", row))
		return keys
	if label.begins_with("守卫塔"):
		keys.append(_biome_key_for_row("gate", row))
		return keys
	if label.begins_with("金库") or label.begins_with("被打开的金库"):
		keys.append("castle_vault|")
		return keys
	if label.begins_with("王座"):
		keys.append("castle_throne|")
		return keys
	if label.begins_with("雪山"):
		keys.append("mountain|snow")
		keys.append("snow_peak|snow")
		return keys
	if label.begins_with("沙山"):
		keys.append("mountain|desert")
		return keys
	if label.begins_with("山"):
		keys.append("mountain|grass")
	return keys


static func _biome_key_for_row(terrain: String, row: int) -> String:
	if row == 2:
		return "%s|desert" % terrain
	if row == 3:
		return "%s|snow" % terrain
	return "%s|grass" % terrain


static func _register_atlas_key(key: String, source_id: int, coord: Vector2i) -> void:
	SOURCE_IDS[key] = source_id
	ATLAS_COORDS[key] = coord
	var coords: Array = ATLAS_COORD_LISTS.get(key, [])
	if not coords.has(coord):
		coords.append(coord)
	ATLAS_COORD_LISTS[key] = coords
	var parts := String(key).split("|", false)
	if parts.size() >= 2 and String(parts[1]) == Config.DEFAULT_BIOME:
		var generic_key := "%s|" % String(parts[0])
		if not SOURCE_IDS.has(generic_key):
			SOURCE_IDS[generic_key] = source_id
			ATLAS_COORDS[generic_key] = coord
			ATLAS_COORD_LISTS[generic_key] = coords.duplicate()


static func _build_grid_atlas_source(path: String) -> TileSetAtlasSource:
	var img := _try_load_image(path)
	if img == null:
		push_warning("TileSetBuilder: atlas sheet missing at %s" % path)
		return null
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var tex := ImageTexture.create_from_image(img)
	var source := TileSetAtlasSource.new()
	source.resource_name = path
	source.texture = tex
	source.texture_region_size = TILE_SIZE
	var cols: int = img.get_width() / TILE_SIZE.x
	var rows: int = img.get_height() / TILE_SIZE.y
	for row in rows:
		for col in cols:
			source.create_tile(Vector2i(col, row))
	return source


## Build a legacy per-terrain atlas (vertical strip of 48×N×48) for
## non-FE8 terrains.
static func _build_legacy_source_for(terrain: String, biome: String) -> TileSetAtlasSource:
	var n_variants: int = int(Config.TERRAIN_VARIANT_COUNTS.get(terrain, 1))
	var atlas := _load_atlas_image(terrain, biome, n_variants)
	if atlas == null:
		return null
	var tex := ImageTexture.create_from_image(atlas)
	var source := TileSetAtlasSource.new()
	source.texture = tex
	source.texture_region_size = TILE_SIZE
	source.create_tile(Vector2i(0, 0))
	for v in range(1, n_variants):
		source.create_alternative_tile(Vector2i(0, 0), v)
	source.set_name("%s_%s" % [terrain, biome] if biome != "" else terrain)
	return source

## Build the 48 × (48*n_variants) atlas by stacking the per-variant PNGs
## top‑to‑bottom. Returns null if ANY variant is missing.
static func _load_atlas_image(terrain: String, biome: String, n_variants: int) -> Image:
	var w := TILE_SIZE.x
	var h := TILE_SIZE.y * n_variants
	var atlas := Image.create(w, h, false, Image.FORMAT_RGBA8)
	for v in range(n_variants):
		var img := _load_tile_variant_image(terrain, biome, v)
		if img == null:
			push_warning("TileSetBuilder: missing tile asset for %s/%s v%d; using plain fallback" % [terrain, biome, v])
			img = _load_tile_variant_image("plain", "", 0)
		if img == null:
			_fill_plain_color(atlas, terrain, v)
			continue
		if img.get_format() != Image.FORMAT_RGBA8:
			img.convert(Image.FORMAT_RGBA8)
		if img.get_width() != w or img.get_height() != TILE_SIZE.y:
			img.resize(w, TILE_SIZE.y, Image.INTERPOLATE_NEAREST)
		var rect := Rect2i(0, 0, w, TILE_SIZE.y)
		atlas.blit_rect(img, rect, Vector2i(0, v * TILE_SIZE.y))
	return atlas

static func _load_tile_variant_image(terrain: String, biome: String, variant_index: int) -> Image:
	for candidate in _tile_asset_candidates(terrain, biome):
		var candidate_terrain: String = String(candidate.get("terrain", terrain))
		var candidate_biome: String = String(candidate.get("biome", ""))
		var basename := Config.tile_asset_basename(candidate_terrain, candidate_biome, 0, variant_index)
		if basename == "":
			continue
		var path := "%s/%s.png" % [TILES_DIR, basename]
		var img := _try_load_image(path)
		if img != null:
			return img
	return null

static func _tile_asset_candidates(terrain: String, biome: String) -> Array[Dictionary]:
	var candidates: Array[Dictionary] = [{"terrain": terrain, "biome": biome}]
	if biome != "":
		candidates.append({"terrain": terrain, "biome": ""})
	for fallback in _TERRAIN_ASSET_FALLBACKS.get(terrain, []):
		candidates.append({"terrain": String(fallback), "biome": biome})
		if biome != "":
			candidates.append({"terrain": String(fallback), "biome": ""})
	candidates.append({"terrain": "plain", "biome": ""})
	return candidates

static func _try_load_image(path: String) -> Image:
	# 07-21 M7 — runtime I/O 路径收口到 TextureLoader。TileSetBuilder
	# 之前是直接 ResourceLoader.load() + Image.load_from_file() 两段
	# fallback,容易在导出 / 跨平台构建时遗漏路径(本仓库 .import
	# 系统未启用)。TextureLoader 内部对 `res://` 与 globalised 路径
	# 都有显式分支,后续如需 redirect 也只改一处。
	if not FileAccess.file_exists(path):
		return null
	return TextureLoader.load_image(path)

static func _fill_plain_color(atlas: Image, terrain: String, variant_index: int) -> void:
	var y0 := variant_index * TILE_SIZE.y
	var color: Color = Config.TERRAIN_COLORS.get(terrain, Config.TERRAIN_COLORS.get("plain", Color("#79b66a")))
	for x in TILE_SIZE.x:
		for y in TILE_SIZE.y:
			atlas.set_pixel(x, y0 + y, color)
