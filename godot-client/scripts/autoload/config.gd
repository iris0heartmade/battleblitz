extends Node
## Config — autoload singleton mirroring `game/app/config.py`.
##
## Single source of truth for game-rule constants in the Godot client.
## Every magic number here MUST match its Python counterpart in
## `game/app/config.py`. See `../docs/路线/Godot移植方案.md` §7.
##
## This file is intentionally a hard-coded mirror. The plan recommends
## exposing a `GET /games/config` endpoint and pulling these at startup,
## but the M1 prototype inlines them to keep the surface area small.

# === Map / grid ===
const MAP_SIZE_DEFAULT: int = 15              # config.MAP_SIZE
const MAX_PLAYERS: int = 4                    # config.MAX_PLAYERS
const MIN_PLAYERS: int = 2                    # config.MIN_PLAYERS
const DEFAULT_PLAYER_COLORS: Array[String] = ["red", "blue", "green", "yellow"]
const WIN_CONDITIONS: Array[String] = ["rout", "seize", "reach", "defend"]

# === Tile rendering ===
const TILE_PIXEL_SIZE: int = 48               # 48×48 PNGs from the JS frontend
const TERRAIN_VARIANT_COUNTS: Dictionary = {
	# Each terrain maps to ONE 16×16 sub-tile in the
	# `OverworldRegularFE8.png` 32×32 master tilemap. We pick the
	# "center" tile of each terrain's 4×4 autotile block (see
	# `FE8_TILE_COORDS`). Batch 2 will switch to a real `TileSet` with
	# `add_terrain_set()` + bitmask autotiling using the surrounding 15
	# transition tiles — the autotile bitmask layout is already baked
	# into the FE8 tilemap (it's a GBA-standard 16-state autotile).
	"plain": 1, "forest": 1, "mountain": 1, "river": 1,
	"snow_peak": 1,
	"castle": 1, "desert": 1, "snow": 1,
	"village": 1, "barracks": 1, "road": 1, "gate": 1,
	"bridge": 1,
	"castle_floor": 1, "castle_wall": 1, "castle_throne": 1,
	"castle_stairs": 1, "castle_vault": 1, "castle_door": 1,
}
# Tile coordinates (col, row) within the 32×32 OverworldRegularFE8
# master tilemap. Each entry is the CENTER tile of that terrain's
# 4×4 autotile block. Empirically verified by slicing the atlas and
# inspecting what each (col, row) actually contains.
const FE8_TILE_COORDS: Dictionary = {
	# M1.5 batch 2 — empirically located by slicing the FE8 atlas
	# into 16×16 sub-tiles and identifying the center of each
	# terrain's 4×4 autotile block. These point at the "pure"
	# sub-tile (no edges, fully surrounded by same terrain).
	# Batch 2 will add the 15 surrounding transition tiles and
	# wire them into a TileSetTerrain for bitmask autotiling.
	"plain":    Vector2i(5, 1),    # light green grass
	"forest":   Vector2i(11, 11),  # dense tree canopy
	"mountain": Vector2i(2, 11),   # brown rocky peak
	"river":    Vector2i(18, 6),   # deep blue water surface
	# Castle interior palette (top-left of tilemap).
	"castle_wall":  Vector2i(0, 0),
	"castle_door":  Vector2i(1, 0),
	"castle_floor": Vector2i(0, 1),
	"castle_throne":Vector2i(2, 1),
	"castle_stairs":Vector2i(3, 1),
	"castle_vault": Vector2i(3, 2),
	"road":     Vector2i(3, 1),    # tan cobblestone
	"gate":     Vector2i(1, 0),    # castle door (reused for now)
	"village":  Vector2i(5, 1),    # TODO: locate in FE8 (bottom area)
	"barracks": Vector2i(5, 1),    # TODO
	"desert":   Vector2i(5, 1),    # sand area
	"snow":     Vector2i(5, 1),    # snow area
	"snow_peak":Vector2i(2, 11),   # reuse mountain for now
	"bridge":   Vector2i(18, 6),   # reuse river for now
	"castle":   Vector2i(0, 1),    # castle floor (default castle)
}
const FE8_TERRAINS: Array[String] = [
	# Terrains that read from `OverworldRegularFE8.png` (a single
	# shared TileSetAtlasSource for all of them). Other terrains fall
	# back to the per-terrain 48×48 PNGs under `res://assets/tiles/`.
	"plain", "forest", "mountain", "river", "castle", "village",
	"barracks", "road", "gate", "desert", "snow", "snow_peak", "bridge",
	"castle_floor", "castle_wall", "castle_throne", "castle_stairs",
	"castle_vault", "castle_door",
]
const FE8_ATLAS_SIZE := Vector2i(512, 512)    # master tilemap dimensions
const FE8_TILE_SIZE := Vector2i(16, 16)       # sub-tile dimensions in the master
const FE8_ATLAS_PATH := "res://FE8/OverworldRegular.png"

# 4×4 autotile block origins in the FE8 master tilemap. Each block
# holds 16 16×16 sub-tiles (one per bitmask state) following the
# standard GBA FE8 layout:
#   (0,0)=center (1,0)=N (2,0)=E (3,0)=NE
#   (0,1)=S      (1,1)=NS (2,1)=SE (3,1)=NSE
#   (0,2)=W      (1,2)=NW (2,2)=EW (3,2)=NEW
#   (0,3)=SW     (1,3)=NSW (2,3)=SEW (3,3)=NESW
# The `terrain_peering_bits` per tile in Godot 4 is the bitmask
# value where bit=1 means "neighbor is same terrain" (no visible edge).
const FE8_TERRAIN_BLOCK_ORIGINS: Dictionary = {
	"plain":    Vector2i(4, 0),    # 4×4 block (4,0)-(7,3), center (5,1)
	"forest":   Vector2i(10, 10),  # (10,10)-(13,13), center (11,11)
	"mountain": Vector2i(1, 10),   # (1,10)-(4,13), center (2,11)
	"river":    Vector2i(17, 5),   # (17,5)-(20,8), center (18,6)
}
# 16 peering-bit values per (col_off, row_off) in the 4×4 block.
# Ordered as: (0,0) (1,0) (2,0) (3,0) (0,1) (1,1) (2,1) (3,1)
#             (0,2) (1,2) (2,2) (3,2) (0,3) (1,3) (2,3) (3,3)
# Maps to bitmask = (W << 3) | (S << 2) | (E << 1) | N
# where bit=1 means "same terrain" (no visible edge).
const AUTOTILE_PEERING_BITS: Array[int] = [
	15, 14, 13, 12,  # row 0: center, N, E, NE
	11, 10, 9,  8,   # row 1: S, N+S, SE, NSE
	7,  6,  5,  4,   # row 2: W, NW, EW, NEW
	3,  2,  1,  0,   # row 3: SW, NSW, SEW, NESW
]
const BIOME_AWARE_TERRAINS: Array[String] = [
	# Mirrors `BIOME_AWARE_TERRAINS` in `game/app/web/app.js:1754`. Asset
	# filename is `<terrain>_<biome>_v{n}.png` for these, plain
	# `<terrain>_v{n}.png` otherwise.
	"forest", "castle",
	"castle_floor", "castle_wall", "castle_throne",
	"castle_stairs", "castle_vault", "castle_door",
]
const BIOMES: Array[String] = ["grass", "desert", "snow"]
const DEFAULT_BIOME: String = "grass"

# === Terrain passability (×2 integer encoding from game_logic.py) ===
## Move cost on each terrain. The Python engine stores `unit.mov` in
## MP points where MP = cost / 2 (so road = 1 = half a point). The
## client BFS MUST keep this integer arithmetic to stay in sync with
## server judgement.
const TERRAIN_MOVE_COST: Dictionary = {
	"plain": 2, "forest": 4, "mountain": 6, "snow_peak": 6,
	"river": 6, "castle": 2, "village": 2, "barracks": 2,
	"road": 1, "gate": 9999, "bridge": 1,
	# Castle sub-features use the same costs as castle_floor unless the
	# server overrides them; mirrored from `CASTLE_SUBTYPE_*` tables.
	"castle_floor": 2, "castle_wall": 9999, "castle_throne": 2,
	"castle_stairs": 2, "castle_vault": 2, "castle_door": 2,
}
const TERRAIN_DEF_BONUS: Dictionary = {
	"plain": 0, "forest": 2, "mountain": 3, "snow_peak": 3,
	"river": 0, "castle": 5, "village": 0, "barracks": 1,
	"road": 0, "gate": 0, "bridge": 0,
	"castle_floor": 3, "castle_wall": 99, "castle_throne": 6,
	"castle_stairs": 3, "castle_vault": 5, "castle_door": 4,
}

# === Economy ===
const BUILDING_INCOME: Dictionary = {
	# config.BUILDING_INCOME.amount — gold per turn when owned.
	"village": 50, "barracks": 100, "castle_vault": 150,
}
const RECRUIT_COST: Dictionary = {
	# config.RECRUIT_COST — gold to spawn a unit at a barracks.
	"swordsman": 200, "archer": 250, "knight": 400,
	"warlock": 300, "healer": 350,
}

# === Morale / combat (UI preview only) ===
const MORALE_MAX: int = 3                     # config.MORALE_MAX
const MORALE_ATK_PER_STAR: float = 0.10       # config.MORALE_ATK_PER_STAR
const MORALE_DEF_PER_STAR: float = 0.05       # config.MORALE_DEF_PER_STAR
const BASE_CRIT_RATE: float = 0.05            # config.BASE_CRIT_RATE
const CRIT_PER_LEVEL: float = 0.01            # config.CRIT_PER_LEVEL
const CRIT_MULTIPLIER: float = 1.5            # config.CRIT_MULTIPLIER
const COUNTER_DAMAGE_MULT: float = 0.5        # half-damage counter

# === Seize / claim ===
const CLAIM_TURNS_REQUIRED: int = 2          # config.CLAIM_TURNS_REQUIRED

# === Player colours (used by unit sprite tinting, HUD chrome) ===
const PLAYER_COLOR_RGB: Dictionary = {
	"red":    Color("#e85a6a"),
	"blue":   Color("#5fa8e8"),
	"green":  Color("#7ec97e"),
	"yellow": Color("#f0c75e"),
}
# Terrain palette for the legacy fallback colours documented in §4.2 of
# the port plan — used when an art asset is missing.
const TERRAIN_COLOR_RGB: Dictionary = {
	"plain":    Color("#cfe5b6"),
	"forest":   Color("#4f8a47"),
	"mountain": Color("#8c8c8c"),
	"river":    Color("#5fb0e8"),
	"castle":   Color("#f0c75e"),
	"village":  Color("#cfe5b6"),
	"barracks": Color("#cfe5b6"),
	"road":     Color("#d6c89a"),
	"gate":     Color("#5a4a3a"),
	"bridge":   Color("#bba679"),
	"snow":     Color("#f4f8ff"),
	"snow_peak":Color("#c8d6e0"),
	"desert":   Color("#e6d4a3"),
}

# === Network defaults (overridden by UserSettings at startup) ===
const DEFAULT_API_BASE: String = "http://127.0.0.1:8000"
const DEFAULT_WS_BASE: String = "ws://127.0.0.1:8000"
const PROTOCOL_VERSION: int = 1               # protocol/v1.py:PROTOCOL_VERSION
const WS_HEARTBEAT_SEC: int = 30              # ws_gateway heartbeat

# === Terrain character → name table (mirrors app.js TERRAIN_CHAR_TO_NAME) ===
## Used by MapLoader to translate the compact layout string in a map JSON
## into the long terrain names used everywhere else. The lower-case chars
## are in-map feature toggles (village/barracks/road/gate/bridge).
const TERRAIN_CHAR_TO_NAME: Dictionary = {
	"P": "plain", "F": "forest", "M": "mountain", "S": "snow_peak",
	"R": "river", "C": "castle",
	"v": "village", "b": "barracks", "r": "road", "g": "gate",
	"j": "bridge",
	# Map `H` (HQ) → castle. Some maps (e.g. `balanced_2p_15`) use
	# `H` for the player HQ tile; the JS frontend's TERRAIN_CHAR_TO_NAME
	# doesn't include it and silently falls through to `plain`, which
	# renders an invisible "ghost" castle. Treat H the same as C.
	"H": "castle",
	# Castle sub-feature in-line chars (uppercase = top-down look,
	# lowercase = mirror variant). Mirrors the legend in
	# `game/app/game_logic.py:1391`.
	"F2": "castle_floor", "W": "castle_wall", "T": "castle_throne",
	"D": "castle_door", "S2": "castle_stairs", "V": "castle_vault",
	"f": "castle_floor", "w": "castle_wall", "t": "castle_throne",
	"d": "castle_door", "s": "castle_stairs", "v2": "castle_vault",
}


# ============================================================
# Helpers
# ============================================================

## Returns true if the given terrain can ever be walked on. Mirrors the
## passability check in `game/app/utils.py` (castle_wall / gate = false).
func is_passable(terrain: String) -> bool:
	if not TERRAIN_MOVE_COST.has(terrain):
		return false
	return TERRAIN_MOVE_COST[terrain] < 9999

## Deterministic tile variant picker. Mirrors `pickTileVariant` in
## `game/app/web/app.js:1762`. Hash constants are the same — the tile
## art should be the SAME for the same (terrain, x, y) across the JS and
## Godot clients, so we can A/B compare screenshots.
func pick_tile_variant(terrain: String, x: int, y: int) -> int:
	var n: int = TERRAIN_VARIANT_COUNTS.get(terrain, 2)
	var h: int = 0
	for c in terrain:
		h = (h * 31 + c.unicode_at(0)) & 0xFFFFFFFF
	h = (h ^ (x * 73856093) ^ (y * 19349663)) & 0xFFFFFFFF
	return h % n

## Returns the on-disk asset path (no `.import`/`.png` suffix at this
## layer; the TileSetBuilder resolves to `.png` when wiring the atlas).
## Returns "" if the terrain is unknown.
func tile_asset_basename(terrain: String, biome: String, x: int, y: int) -> String:
	if not TERRAIN_VARIANT_COUNTS.has(terrain):
		return ""
	var variant: int = pick_tile_variant(terrain, x, y)
	var base: String = terrain
	if terrain in BIOME_AWARE_TERRAINS:
		base = "%s_%s" % [terrain, biome]
	return "%s_v%d" % [base, variant]

## Returns the colour tint for a player — used to colour unit sprites
## and the HUD until per-unit hero art lands in a later milestone.
func player_color(name: String) -> Color:
	return PLAYER_COLOR_RGB.get(name, Color.WHITE)

## True iff the terrain is a `castle` cell that has a sub-feature
## (castle_floor / castle_wall / ...). MapLoader uses this to decide
## whether to draw on the CastleLayer in addition to the base terrain.
func has_castle_subtype(terrain: String) -> bool:
	return terrain.begins_with("castle_")
