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

const TILE_SIZE := Vector2i(48, 48)
const TILES_DIR := "res://assets/tiles"

# Populated by `build()`. Keyed by "{terrain}|{biome}" → source_id.
static var SOURCE_IDS: Dictionary = {}

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

	var ts := TileSet.new()
	ts.tile_size = TILE_SIZE

	# 1. The shared FE8 overworld atlas. This is source_id 0. Each
	#    BattleBlitz terrain that has an entry in Config.FE8_TILE_COORDS
	#    points into this atlas at its (col, row) tile coord. We register
	#    one tile per terrain (the CENTER of the 4×4 autotile block);
	#    batch 2 will register the surrounding 15 transition tiles and
	#    wire them into a `TileSetTerrain` with bitmask autotiling.
	var fe8_source := _build_fe8_atlas_source(ts)
	if fe8_source != null:
		var fe8_source_id := ts.add_source(fe8_source)
		# The FE8 atlas is biome-agnostic (the master tilemap doesn't
		# have separate biome palettes). Register under "" AND every
		# known biome so the MapLoader's `source_id_for(terrain, biome)`
		# lookup hits whether the caller passes a biome or not.
		for terrain in Config.FE8_TILE_COORDS.keys():
			SOURCE_IDS["%s|" % terrain] = fe8_source_id
			for biome in Config.BIOMES:
				SOURCE_IDS["%s|%s" % [terrain, biome]] = fe8_source_id

	# 2. Legacy per-terrain atlases for non-FE8 terrains. Registered in
	#    Config.TERRAIN_VARIANT_COUNTS order so the source IDs are
	#    deterministic.
	for terrain in Config.TERRAIN_VARIANT_COUNTS.keys():
		if terrain in Config.FE8_TILE_COORDS:
			continue  # already handled by the FE8 atlas
		var biomes := _biomes_for(terrain)
		for biome in biomes:
			var source := _build_legacy_source_for(terrain, biome)
			if source == null:
				continue
			var source_id := ts.add_source(source)
			SOURCE_IDS["%s|%s" % [terrain, biome]] = source_id

	_cached = ts
	return ts

## Look up the source_id for (terrain, biome). Returns -1 if unknown.
static func source_id_for(terrain: String, biome: String) -> int:
	return int(SOURCE_IDS.get("%s|%s" % [terrain, biome], -1))

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

static func _biomes_for(terrain: String) -> Array:
	if terrain in Config.BIOME_AWARE_TERRAINS:
		return Config.BIOMES.duplicate()
	return [""]    # empty biome → non-biome asset

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
		var basename := Config.tile_asset_basename(terrain, biome, 0, v)
		if basename == "":
			_fill_magenta(atlas, v)
			continue
		var path := "%s/%s.png" % [TILES_DIR, basename]
		var img := _try_load_image(path)
		if img == null:
			push_warning("TileSetBuilder: missing %s — filling magenta" % path)
			_fill_magenta(atlas, v)
			continue
		if img.get_format() != Image.FORMAT_RGBA8:
			img.convert(Image.FORMAT_RGBA8)
		var rect := Rect2i(0, 0, min(img.get_width(), w), min(img.get_height(), TILE_SIZE.y))
		atlas.blit_rect(img, rect, Vector2i(0, v * TILE_SIZE.y))
	return atlas

static func _try_load_image(path: String) -> Image:
	if not FileAccess.file_exists(path):
		return null
	if ResourceLoader.exists(path):
		var res: Resource = load(path)
		if res is Texture2D:
			var tex: Texture2D = res
			if tex.get_image() != null:
				return tex.get_image()
	return Image.load_from_file(path)

static func _fill_magenta(atlas: Image, variant_index: int) -> void:
	var y0 := variant_index * TILE_SIZE.y
	for x in TILE_SIZE.x:
		for y in TILE_SIZE.y:
			atlas.set_pixel(x, y0 + y, Color.MAGENTA)
