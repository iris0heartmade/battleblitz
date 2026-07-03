"""
Game configuration constants.

All gameplay tuning values live here. Keep magic numbers out of logic modules.
"""
from __future__ import annotations

from typing import Dict, Final, Tuple


# ============================================================
# Map configuration
# ============================================================

MAP_SIZE: Final[int] = 15  # 15x15 grid

# Terrain types as string constants (also stored in DB)
TERRAIN_PLAIN: Final[str] = "plain"
TERRAIN_FOREST: Final[str] = "forest"
TERRAIN_MOUNTAIN: Final[str] = "mountain"
TERRAIN_SNOW_PEAK: Final[str] = "snow_peak"   # 雪山（P2.4：与普通山分开的银顶）
TERRAIN_RIVER: Final[str] = "river"
TERRAIN_CASTLE: Final[str] = "castle"
# New terrains (2026-06-30 P0.4)
TERRAIN_VILLAGE: Final[str] = "village"   # 村落
TERRAIN_BARRACKS: Final[str] = "barracks" # 佣兵站
TERRAIN_ROAD: Final[str] = "road"         # 道路（MP 减半）
TERRAIN_GATE: Final[str] = "gate"         # 关卡（敌方阻拦，不可走）

# Castle interior sub-features (stored in Tile.subtype column)
CASTLE_FLOOR: Final[str] = "castle_floor"     # 地板
CASTLE_WALL: Final[str] = "castle_wall"       # 墙壁（不可走）
CASTLE_THRONE: Final[str] = "castle_throne"   # 王座
CASTLE_STAIRS: Final[str] = "castle_stairs"   # 阶梯
CASTLE_VAULT: Final[str] = "castle_vault"     # 金库
CASTLE_DOOR: Final[str] = "castle_door"       # 门扉

TERRAIN_TYPES: Final[Tuple[str, ...]] = (
    TERRAIN_PLAIN,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_SNOW_PEAK,
    TERRAIN_RIVER,
    TERRAIN_CASTLE,
    TERRAIN_VILLAGE,
    TERRAIN_BARRACKS,
    TERRAIN_ROAD,
    TERRAIN_GATE,
)

CASTLE_SUBTYPES: Final[Tuple[str, ...]] = (
    CASTLE_FLOOR,
    CASTLE_WALL,
    CASTLE_THRONE,
    CASTLE_STAIRS,
    CASTLE_VAULT,
    CASTLE_DOOR,
)

# Tile movement cost when entering the tile, expressed as INTEGER × 2 so
# we never hit float precision in the BFS pathfinder. Road costs `1`
# (i.e. half a plain tile). Blockers cost a high sentinel so the BFS
# filters them out before consulting terrain_passable().
#
# Real cost = integer_cost / 2.
TERRAIN_MOVE_COST: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 2,
    TERRAIN_FOREST: 4,
    TERRAIN_MOUNTAIN: 6,
    TERRAIN_SNOW_PEAK: 6,   # impassable, same movement cost as mountain
    TERRAIN_RIVER: 6,
    TERRAIN_CASTLE: 2,
    TERRAIN_VILLAGE: 2,
    TERRAIN_BARRACKS: 2,
    TERRAIN_ROAD: 1,   # road = half cost
    TERRAIN_GATE: 9999,  # impassable
    # Castle sub-features
    CASTLE_FLOOR: 2,
    CASTLE_WALL: 9999,   # impassable
    CASTLE_THRONE: 2,
    CASTLE_STAIRS: 2,
    CASTLE_VAULT: 2,
    CASTLE_DOOR: 2,
}

# Defense bonus added to a defender's DEF when calculating damage.
TERRAIN_DEF_BONUS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 0,
    TERRAIN_FOREST: 2,
    TERRAIN_MOUNTAIN: 3,
    TERRAIN_SNOW_PEAK: 3,   # same defensive bonus as mountain
    TERRAIN_RIVER: 0,
    TERRAIN_CASTLE: 5,  # legacy; new code uses CASTLE_SUBTYPE_DEF_BONUS
    TERRAIN_VILLAGE: 0,
    TERRAIN_BARRACKS: 1,
    TERRAIN_ROAD: 0,
    TERRAIN_GATE: 0,
    # Castle sub-features: throne is the safest spot, vault is also strong
    CASTLE_FLOOR: 3,
    CASTLE_WALL: 99,   # blocking tile, never actually defends
    CASTLE_THRONE: 6,
    CASTLE_STAIRS: 3,
    CASTLE_VAULT: 5,
    CASTLE_DOOR: 4,
}

# ----------------------------------------------------------------
# Building income (P0.4 → P2.4 refactor: data-driven, not hard-coded)
# ----------------------------------------------------------------
# Each entry pairs a terrain id with the rules for paying its owner.
# P2.4 design goals:
#   - One table to look at, not two parallel ones (INCOME_TERRAINS +
#     INCOME_PER_TURN) that have to stay in sync.
#   - Per-building cap is the second design lever: a player can
#     capture many villages, but no single tile can pay more than
#     its `cap_per_player` (or 0 = no cap). The default `cap=None`
#     means no per-player cap.
#   - `requires_owner=True` means the tile only pays once the owner_id
#     is set. (Right now every income tile requires an owner. We
#     keep the field so future tiles like "toll road" can be unowned
#     and pay a flat per-crossing fee instead.)
#
# To add a new yield tile, append one entry; no other config changes
# needed. `_collect_income_for_player` iterates this table.
BUILDING_INCOME: Final[Dict[str, Dict]] = {
    TERRAIN_VILLAGE: {
        "amount": 50,
        "cap_per_player": None,
        "requires_owner": True,
    },
    TERRAIN_BARRACKS: {
        "amount": 100,
        "cap_per_player": None,
        "requires_owner": True,
    },
    CASTLE_VAULT: {
        "amount": 150,
        "cap_per_player": None,
        "requires_owner": True,
    },
}


# ----------------------------------------------------------------
# Backwards-compat aliases
# ----------------------------------------------------------------
# Code that pre-dates the BUILDING_INCOME refactor still references
# these by name. They are derived from BUILDING_INCOME on import so
# there's a single source of truth.
INCOME_TERRAINS: Final[Tuple[str, ...]] = tuple(BUILDING_INCOME.keys())
INCOME_PER_TURN: Final[Dict[str, int]] = {
    t: cfg["amount"] for t, cfg in BUILDING_INCOME.items()
}

# Recruit cost (gold) for spawning a new unit at an owned barracks.
# Placeholder values.
RECRUIT_COST: Final[Dict[str, int]] = {
    "swordsman": 200,
    "archer":    250,
    "knight":    400,
    "warlock":   300,
    "healer":    350,
}

# Relative spawn weight for procedural map generation (excluding castle).
# More weights = more of that terrain. Tuned for ~30% passable forest/mountain mix.
# Default spawn weight table. Used by the legacy "classic" random map
# generator when no style is specified. New procedural code consumes
# per-style weights from MAP_STYLES.
#
# Note: snow_peak is intentionally absent here. It's a snow-biome-only
# terrain, so non-snow styles never spawn it. The snow_outer style's
# own weight table does include it.
TERRAIN_SPAWN_WEIGHTS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 55,
    TERRAIN_FOREST: 14,
    TERRAIN_MOUNTAIN: 8,
    TERRAIN_RIVER: 10,
    TERRAIN_VILLAGE: 5,
    TERRAIN_BARRACKS: 2,
    TERRAIN_ROAD: 5,
    TERRAIN_GATE: 1,  # rare; gates are enemy-built blockers, often placed by hand
}

# Claim mechanic: units must stand on a claim-eligible tile for this many
# of their own turns (the unit performs the claim action each turn) before
# ownership flips.
CLAIM_TURNS_REQUIRED: Final[int] = 2

# Castle spawn config: one castle per player, on the map's symmetric edges.
CASTLES_PER_GAME: Final[int] = 4  # max players; we generate up to 4 castles
CASTLE_NEIGHBOR_RADIUS: Final[int] = 2  # how many tiles around castle are kept passable


# ============================================================
# Map styles (P2.4 — multi-style procedural generation)
# ============================================================
# A map "style" is a (biome, hq_mode, terrain_weight table) combination.
# Styles drive both procedural generation (generate_map) and the create-
# game dropdown's filter/sort.
#
# Three HQ modes are supported:
#   - "single_hq"      : 1 whole-tile `castle` per player + 2-tile safe
#                        zone of plain tiles (current default).
#   - "hq_with_struct" : like "single_hq", but each HQ is wrapped in a
#                        3×3 castle sub-feature template (1 throne +
#                        2 wall + 1 door + 5 floor).
#   - "castle_internal": the *entire* map is composed of `castle_*`
#                        sub-features (no outer tiles).

# Style ID constants (also reused in preset JSON files / API)
STYLE_GRASS_OUTER:     Final[str] = "grass_outer"      # default + open plains
STYLE_SNOW_OUTER:      Final[str] = "snow_outer"       # cold biomes
STYLE_DESERT_OUTER:    Final[str] = "desert_outer"     # arid biomes
STYLE_COMPACT_OUTER:   Final[str] = "compact_outer"    # small fast maps
STYLE_CASTLE_INTERNAL: Final[str] = "castle_internal"  # 100% castle-internal

# Each style carries:
#   - display_cn: short Chinese label for UI dropdown ("草地 外圈")
#   - biome: passed straight through to Game.map_biome
#   - mode: HQ mode (see constants above)
#   - weights: terrain-weight table for outer tiles (ignored in
#              "castle_internal")
#   - safe_zone_radius: how many tiles around each HQ stay plain
#               (mode == "single_hq"/"hq_with_struct" only)
#   - wall_density / door_count / vault_count / stairs_count: only used
#               by mode == "castle_internal"
MAP_STYLES: Final[Dict[str, Dict]] = {
    STYLE_GRASS_OUTER: {
        "display_cn": "草地 外圈",
        "biome": "grass",
        "mode": "single_hq",
        "safe_zone_radius": 2,
        "weights": {
            TERRAIN_PLAIN:    55,
            TERRAIN_FOREST:   14,
            TERRAIN_MOUNTAIN:  8,
            TERRAIN_RIVER:    10,
            TERRAIN_VILLAGE:   5,
            TERRAIN_BARRACKS:  2,
            TERRAIN_ROAD:      5,
        },
    },
    STYLE_SNOW_OUTER: {
        "display_cn": "雪地 外圈",
        "biome": "snow",
        "mode": "single_hq",
        "safe_zone_radius": 2,
        # P2.4 polish — snow biome is now PURE-snow. Drop the grey
        # TERRAIN_MOUNTAIN weight (was 6) and bump TERRAIN_SNOW_PEAK
        # 12 → 18 so the silver-peak count stays visually rich.
        "weights": {
            TERRAIN_PLAIN:    40,
            TERRAIN_FOREST:   12,
            TERRAIN_SNOW_PEAK: 18,   # snow-biome silver peaks
            # TERRAIN_MOUNTAIN intentionally absent — snow maps are pure-snow
            TERRAIN_RIVER:    15,
            TERRAIN_VILLAGE:   5,
            TERRAIN_BARRACKS:  2,
            TERRAIN_ROAD:      5,
        },
    },
    STYLE_DESERT_OUTER: {
        "display_cn": "沙漠 外圈",
        "biome": "desert",
        "mode": "single_hq",
        "safe_zone_radius": 2,
        "weights": {
            TERRAIN_PLAIN:    65,
            TERRAIN_FOREST:    8,
            TERRAIN_MOUNTAIN: 10,
            TERRAIN_RIVER:     5,
            TERRAIN_VILLAGE:   3,
            TERRAIN_BARRACKS:  2,
            TERRAIN_ROAD:      5,
        },
    },
    STYLE_COMPACT_OUTER: {
        "display_cn": "小城外圈",
        "biome": "grass",
        "mode": "single_hq",
        "safe_zone_radius": 1,
        "weights": {
            TERRAIN_PLAIN:    70,
            TERRAIN_FOREST:   12,
            TERRAIN_MOUNTAIN:  5,
            TERRAIN_RIVER:     4,
            TERRAIN_VILLAGE:   5,
            TERRAIN_BARRACKS:  2,
            TERRAIN_ROAD:      2,
        },
    },
    STYLE_CASTLE_INTERNAL: {
        "display_cn": "城堡内部",
        "biome": "grass",
        "mode": "castle_internal",
        # Tile palette: pre-computed probabilities per sub-feature.
        # The generator picks one per tile, then overrides the HQ cells
        # to be `castle_throne` and adds door/stairs/vault around them.
        "tile_palette": {
            CASTLE_FLOOR: 80,
            CASTLE_WALL:  20,
        },
        # HQ decorations (placed on top of the palette result)
        "door_count_per_hq": 2,
        "stairs_count_per_hq": 1,
        "vault_count_per_hq": 1,
    },
}


# ============================================================
# Player configuration
# ============================================================

MAX_PLAYERS: Final[int] = 4
MIN_PLAYERS: Final[int] = 2
# P2.4 — spectator cap is independent of capacity so a fully-booked
# room can still attract an audience. Used by Game.max_spectators
# default and by the join route as the upper bound.
DEFAULT_MAX_SPECTATORS: Final[int] = 8
DEFAULT_PLAYER_COLORS: Final[Tuple[str, ...]] = ("red", "blue", "green", "yellow")


# ============================================================
# Skill identifiers — canonical string constants
# ============================================================
# Logic lives in app/classes/units/skills/. These are the only stable IDs.

SKILL_DOUBLE_STRIKE: Final[str] = "double_strike"
SKILL_SNIPE:        Final[str] = "snipe"


# ============================================================
# Combat configuration
# ============================================================

BASE_CRIT_RATE: Final[float] = 0.05       # 5%
CRIT_PER_LEVEL: Final[float] = 0.01       # +1% per level
CRIT_MULTIPLIER: Final[float] = 1.5


# ============================================================
# Progression configuration
# ============================================================

EXP_PER_KILL: Final[int] = 10
EXP_PER_ASSIST: Final[int] = 5   # if a teammate landed the killing blow
EXP_TO_LEVEL: Final[int] = 60    # every 60 EXP triggers level-up (faster pacing)
MAX_LEVEL: Final[int] = 10
LEVEL_UP_STAT_BONUS: Final[float] = 0.05   # +5% to all base stats on level up
LEVEL_UP_BONUS_POINTS: Final[int] = 2      # manual stat points per level (auto for now)


# ============================================================
# Turn / timeout configuration
# ============================================================

TURN_TIMEOUT_HOURS: Final[int] = 24
TURNS_CHECK_INTERVAL_SECONDS: Final[int] = 10  # background-task poll cadence

# Abandoned-room cleanup
ABANDONED_LOBBY_MINUTES: Final[int] = 30  # waiting game with 0 players older than this gets deleted
ABANDONED_FINISHED_HOURS: Final[int] = 24  # finished games older than this get deleted
LOBBY_CLEANUP_INTERVAL_SECONDS: Final[int] = 60  # how often to scan for abandoned lobbies


# ============================================================
# Counter-attack tuning
# ============================================================
# When a defender survives an attack and can hit the attacker, it deals
# `COUNTER_DAMAGE_MULT * normal_damage` (rounded down, min 1).
# Fire-Emblem uses 0.5 (50%); raise it to make counter more punishing,
# lower it to make counter mostly cosmetic.
COUNTER_DAMAGE_MULT: Final[float] = 0.5
# Some units may bypass counter entirely (e.g. ranged kiting units).
# Leave empty for now; populated by per-unit skills later.
COUNTER_IMMUNE_SKILLS: Final[tuple[str, ...]] = ()

# AI player
AI_THINK_DELAY_SECONDS: Final[float] = 1.2  # delay between AI actions so humans can watch
AI_MAX_ACTIONS_PER_TURN: Final[int] = 5      # safety cap so a buggy AI can't loop forever
AI_AGGRO_RANGE: Final[int] = 4               # AI prefers targets within this many tiles

# ============================================================
# Morale system (replaces EXP/Level)
# ============================================================
MORALE_MAX: Final[int] = 3
MORALE_ATK_PER_STAR: Final[float] = 0.10  # +10% ATK per star (max +30% at 3 stars)
MORALE_DEF_PER_STAR: Final[float] = 0.05  # +5%  DEF per star (max +15% at 3 stars)


# ============================================================
# Movement points (MP) system
# ============================================================
# Each unit starts the turn with MP equal to its `mov` value, and each
# tile entered deducts the terrain's move cost. Attacks cost 0 MP.
# Per-unit MP pool / move-after-action behaviour: see app/classes/units/.


# ============================================================
# DB / app configuration
# ============================================================

DEFAULT_DB_PATH: Final[str] = "battleblitz.db"
APP_TITLE: Final[str] = "BattleBlitz Server"
APP_VERSION: Final[str] = "0.1.0"