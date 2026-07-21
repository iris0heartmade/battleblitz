"""
Game-lifecycle routes: create, join, fetch state, start.

`start_game` is a thin wrapper around the module-level
`_start_battle_internal()` helper so that other modules (notably the
mainline routes) can spawn battles without going through the public
`POST /games/{id}/start` endpoint and its player-count guard.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    MAX_CASTLES,
    DEFAULT_MAX_SPECTATORS,
    DEFAULT_PLAYER_COLORS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    TERRAIN_CASTLE,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_RIVER,
    TERRAIN_SNOW_PEAK,
)
from app.database import get_session
from app.game_logic import (
    MapPresetResult,
    build_ai_player,
    generate_map_preset,
    _unit_name,
)
from app.mainline.spawn_overrides import apply_spawn_overrides
from app.classes.units import get_or_none as _get_unit_or_none
from app.battle_config import UnknownBattleTrackError, expand_battle_config
from app.commanders.effects import bake_passive_into_units, can_fire_co_power
from app.commanders.actions import can_player_fire_now
from app.commanders.registry import get_power_threshold
from app.classes.heroes import get_or_none as _get_hero_or_none
from app.models import ActionLog, Game, Player, Tile, Unit
from app.schemas import (
    AddAIRequest,
    CreateGameRequest,
    GameStateOut,
    GameSummaryOut,
    JoinGameRequest,
    LobbyInfoOut,
    PlayerCOStateOut,
    PlayerOut,
    PresetInfo,
    PresetsResponse,
    RejoinGameRequest,
    RejoinGameResponse,
    UpdateSeatRequest,
    UpdateCommanderRequest,
    UpdateTeamRequest,
    TileOut,
    UnitOut,
    ActionLogOut,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger("audit.user")

router = APIRouter(prefix="/games", tags=["game"])


def _next_color(used_colors: List[str]) -> str:
    for c in DEFAULT_PLAYER_COLORS:
        if c not in used_colors:
            return c
    raise HTTPException(status.HTTP_409_CONFLICT, "没有可用的颜色")


# Seat 0..3 maps to the starting color/faction order used by maps.
def _color_for_seat(seat: int) -> str:
    if seat < 0 or seat >= len(DEFAULT_PLAYER_COLORS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "座位不存在")
    return DEFAULT_PLAYER_COLORS[seat]


def _host_player(players: List[Player]) -> Optional[Player]:
    real_players = [p for p in players if not p.is_spectator]
    if not real_players:
        return None
    return min(real_players, key=lambda p: p.id)


# ============================================================
# P2.4 — derive per-room capacity from the chosen map preset.
# ============================================================
def _effective_max_players(map_preset: Optional[str]) -> int:
    """Compute the room capacity (= max players + AI) for a chosen map.

    Order of precedence:
      1. If the preset declares `recommended_players`, use it (clamped
         to [MIN_PLAYERS, MAX_PLAYERS]).
      2. Otherwise, fall back to the global MAX_PLAYERS (=4).

    Maps are looked up against `MAP_PRESETS` from `game_logic.py`.
    Custom-maps (`custom:<id>`) are not in that dict, so they get the
    default — which is the same as today's behaviour for handcrafted
    maps.
    """
    from app.game_logic import MAP_PRESETS  # local import to avoid cycles
    if map_preset and map_preset in MAP_PRESETS:
        rec = MAP_PRESETS[map_preset].get("recommended_players")
        if rec is not None:
            return max(MIN_PLAYERS, min(int(rec), MAX_PLAYERS))
    return MAX_PLAYERS


# ============================================================
# Module-level helper used by /games/{id}/start AND by mainline routes
# ============================================================

_CHAR_TO_TERRAIN = {
    "P": TERRAIN_PLAIN,
    "F": TERRAIN_FOREST,
    "M": TERRAIN_MOUNTAIN,
    "S": TERRAIN_SNOW_PEAK,   # P2.4 — snow-biome silver peaks
    "R": TERRAIN_RIVER,
    "C": TERRAIN_CASTLE,
}


def _char_to_terrain(ch: str) -> str:
    """Map a single ASCII char (P/F/M/R/C) to its terrain string id."""
    return _CHAR_TO_TERRAIN.get(ch, TERRAIN_PLAIN)


def _expand_user_battle_config(
    battle_config: "BattleConfig | None",
) -> dict:
    """Expand a user-submitted BattleConfig into the stored form.

    Centralised so ``create_game`` can catch ``UnknownBattleTrackError``
    cleanly. ``strict=True`` is mandatory on the public create-game
    path — silent fallback to a missing track would persist a config
    the frontend can't play.
    """
    if battle_config is None:
        return {}
    return expand_battle_config(
        battle_config.model_dump(exclude_none=True),
        strict=True,
    )


def _validate_commander_id(commander_id: str | None) -> None:
    if commander_id is None:
        return
    hero = _get_hero_or_none(commander_id)
    if hero is None or not getattr(hero, "is_commander", False):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown commander: {commander_id}",
        )


def _apply_hero_overrides(
    units: List["Unit"],
    hero_overrides: List[Dict],
    real_players: List["Player"],
) -> None:
    """Bind hero templates to freshly-spawned units.

    For every override entry the helper picks ONE unit out of ``units``
    (matching by ``(color, x, y)`` first, then by color) and mutates it
    in place: sets ``name``, ``hero_id``, and any stat overrides
    declared on the hero's profile.  ``skills`` are NOT touched — they
    continue to come from the base class (heroes inherit skills).

    Args:
        units: Units just appended to the session, in spawn order.
        hero_overrides: Caller-supplied list of
            ``{color, x?, y?, hero_id, name?}`` dicts.
        real_players: Players that own those units (used to map
            ``color`` to ``player_id`` for matching).  The helper
            tolerates overrides that reference a color with no
            player — they're logged and skipped.

    The helper is intentionally side-effect-only: it mutates ``units``
    in place and never raises.  A mistyped hero_id is logged at
    WARNING level so spawns always succeed even if the designer
    shipped a broken mainline JSON.
    """
    # Lazy import — heroes is a content package; pulling it at module
    # import time would slow every test fixture that just exercises
    # base-class unit logic.
    from app.classes.heroes import get_or_none as _get_hero
    from app.classes.units import get_or_none as _get_unit_class

    color_to_pid = {p.color: p.id for p in real_players if p.color}
    # Track which units have been claimed so color-only matches don't
    # double-claim a unit that's already been picked by an exact-match
    # override.
    claimed_ids: set[int] = set()

    for override in hero_overrides:
        hero_id = override.get("hero_id")
        if not hero_id:
            logger.warning("hero override missing hero_id; entry=%r", override)
            continue
        target_color = override.get("color")
        target_x = override.get("x")
        target_y = override.get("y")
        override_name = override.get("name")

        if target_color not in color_to_pid:
            logger.warning(
                "hero override skipped: no player with color=%r "
                "(hero_id=%r)",
                target_color, hero_id,
            )
            continue

        target_pid = color_to_pid[target_color]
        hero = _get_hero(hero_id)
        if hero is None:
            logger.warning(
                "hero override skipped: hero_id=%r not in registry",
                hero_id,
            )
            continue

        # 1) Exact (color, x, y) match.
        candidate: Optional["Unit"] = None
        if target_x is not None and target_y is not None:
            for u in units:
                if u.id in claimed_ids:
                    continue
                if u.player_id != target_pid:
                    continue
                if u.x == int(target_x) and u.y == int(target_y):
                    candidate = u
                    break

        # 2) Fallback: first unclaimed unit of the right color in
        #    spawn order.  This handles the common case where the
        #    mainline only knows the color and lets the map's
        #    initial_units decide the actual tile.
        if candidate is None:
            for u in units:
                if u.id in claimed_ids:
                    continue
                if u.player_id != target_pid:
                    continue
                candidate = u
                break

        if candidate is None:
            logger.warning(
                "hero override could not find a unit: hero_id=%r "
                "color=%r x=%s y=%s",
                hero_id, target_color, target_x, target_y,
            )
            continue

        # Apply the hero binding.
        claimed_ids.add(candidate.id)
        candidate.hero_id = hero_id
        candidate.name = override_name or hero.display_cn

        # ── Base-class reconciliation ──
        # The candidate was spawned from the map's initial_units
        # entry, which set ``unit_type`` and base stats from THAT
        # base class.  When the hero's ``base_class_id`` differs
        # (e.g. the map has only swordsmen but the chapter wants a
        # warlock hero) we must RE-DERIVE the base stats from the
        # hero's base class — otherwise stat fields the hero doesn't
        # override (mdef / mp / matk) would silently keep the map's
        # base-class values, producing a Frankenstein unit.  The
        # same fix applies when a (x, y) match grabs a unit of a
        # different class.
        hero_base = _get_unit_class(hero.base_class_id)
        if hero_base is None:
            logger.warning(
                "hero override skipped: hero %r declares unknown "
                "base_class_id %r",
                hero_id, hero.base_class_id,
            )
            continue
        if candidate.unit_type != hero.base_class_id:
            logger.warning(
                "hero type mismatch: hero %r is %r but map placed a "
                "%r at (%d, %d); re-deriving base stats from %r",
                hero_id, hero.base_class_id,
                candidate.unit_type, candidate.x, candidate.y,
                hero.base_class_id,
            )
            candidate.unit_type = hero.base_class_id
            candidate.hp = hero_base.base_hp
            candidate.max_hp = hero_base.base_hp
            candidate.atk = hero_base.base_atk
            candidate.def_ = hero_base.base_def
            candidate.matk = hero_base.base_matk
            candidate.mdef = hero_base.base_mdef
            candidate.mov = hero_base.base_mov
            candidate.mp = hero_base.mp_pool
            candidate.skills = list(hero_base.default_skills)

        # Stat overrides — None means inherit from base class.  The
        # base-class values were already written (either by the map
        # at spawn time, or by the reconciliation above), so we only
        # overwrite the fields the hero actually overrides.
        if hero.hp_override is not None:
            candidate.hp = hero.hp_override
            candidate.max_hp = hero.hp_override
        if hero.atk_override is not None:
            candidate.atk = hero.atk_override
        if hero.def_override is not None:
            candidate.def_ = hero.def_override
        if hero.matk_override is not None:
            candidate.matk = hero.matk_override
        if hero.mdef_override is not None:
            candidate.mdef = hero.mdef_override
        if hero.mov_override is not None:
            candidate.mov = hero.mov_override
        # mp_pool_override is applied independently of mov_override so
        # designers can keep MP distinct from movement (e.g. a slow
        # caster with deep MP).  When mp_pool_override is unset, MP
        # already inherited from the base class.
        if hero.mp_pool_override is not None:
            candidate.mp = hero.mp_pool_override
        # Skill union: base class default_skills + hero active + hero
        # passive, deduped while preserving order.  Done AFTER the
        # base-class reconciliation above (which may have rewritten
        # candidate.skills to hero_base.default_skills), so we always
        # start from the right base set.
        merged_skills: List[str] = list(candidate.skills)
        for sid in (*hero.active_skills, *hero.passive_skills):
            if sid and sid not in merged_skills:
                merged_skills.append(sid)
        candidate.skills = merged_skills
        campaign_state = override.get("campaign_state")
        if isinstance(campaign_state, dict):
            campaign_class_id = campaign_state.get("class_id")
            campaign_stats = dict(campaign_state.get("base_stats", {}))
            if campaign_class_id and campaign_class_id != candidate.unit_type:
                campaign_class = _get_unit_class(campaign_class_id)
                if campaign_class is None:
                    logger.warning(
                        "hero campaign state skipped: hero_id=%r class_id=%r unknown",
                        hero_id,
                        campaign_class_id,
                    )
                else:
                    candidate.unit_type = campaign_class_id
                    candidate.skills = list(campaign_class.default_skills)
            candidate.level = int(campaign_state.get("level", candidate.level))
            candidate.exp = int(campaign_state.get("exp", candidate.exp))
            if "hp" in campaign_stats:
                hp = int(campaign_stats["hp"])
                candidate.hp = hp
                candidate.max_hp = hp
            if "atk" in campaign_stats:
                candidate.atk = int(campaign_stats["atk"])
            if "def" in campaign_stats:
                candidate.def_ = int(campaign_stats["def"])
            if "matk" in campaign_stats:
                candidate.matk = int(campaign_stats["matk"])
            if "mdef" in campaign_stats:
                candidate.mdef = int(campaign_stats["mdef"])
            if "mov" in campaign_stats:
                candidate.mov = int(campaign_stats["mov"])
            if "mp" in campaign_stats:
                candidate.mp = int(campaign_stats["mp"])
            # Keep permanent attributes separate from the effective combat
            # values below.  Settlement writes this snapshot, not the Unit's
            # equipment-modified fields.
            candidate.campaign_base_stats = {
                "hp": int(candidate.max_hp),
                "atk": int(candidate.atk),
                "def": int(candidate.def_),
                "matk": int(candidate.matk),
                "mdef": int(candidate.mdef),
                "mov": int(candidate.mov),
                "mp": int(campaign_stats.get("mp", candidate.mp)),
            }
            # Campaign equipment is a persistent pre-battle choice.  Apply
            # it only after all class/level values have been materialised so
            # every combat path sees the same effective stats.
            from app.hero_domain.equipment import equipped_stat_bonuses
            equipment_bonuses = equipped_stat_bonuses(
                dict(campaign_state.get("equipment", {}))
            )
            if "hp" in equipment_bonuses:
                candidate.max_hp += equipment_bonuses["hp"]
                candidate.hp += equipment_bonuses["hp"]
            if "atk" in equipment_bonuses:
                candidate.atk += equipment_bonuses["atk"]
            if "def" in equipment_bonuses:
                candidate.def_ += equipment_bonuses["def"]
            if "matk" in equipment_bonuses:
                candidate.matk += equipment_bonuses["matk"]
            if "mdef" in equipment_bonuses:
                candidate.mdef += equipment_bonuses["mdef"]
            if "mov" in equipment_bonuses:
                candidate.mov += equipment_bonuses["mov"]
            merged_skills = list(candidate.skills)
            for sid in campaign_state.get("learned_skills", []):
                if sid and sid not in merged_skills:
                    merged_skills.append(sid)
            candidate.skills = merged_skills
        logger.info(
            "hero bound: unit_id=%d hero_id=%r class=%r name=%r "
            "hp=%d atk=%d def=%d matk=%d mdef=%d mov=%d mp=%d",
            candidate.id, hero_id, hero.base_class_id, candidate.name,
            candidate.hp, candidate.atk, candidate.def_,
            candidate.matk, candidate.mdef, candidate.mov, candidate.mp,
        )


async def _start_battle_internal(
    session: AsyncSession,
    game: Game,
    players: List[Player],
    *,
    map_preset: Optional[str] = None,
    map_seed: Optional[int] = None,
    hero_overrides: Optional[List[Dict]] = None,
    spawn_overrides: Optional[Dict] = None,
) -> None:
    """Generate tiles, spawn units, mark castles + tile occupancy.

    Used by both ``start_game`` (the HTTP endpoint) and the mainline
    routes (``routes/mainline.py``). The caller is responsible for
    committing/rolling back the session.

    Args:
        session: Active async DB session.
        game: A persisted ``Game`` row (with ``id``).
        players: Already-persisted ``Player`` rows belonging to ``game``.
        map_preset: Override the game's preset (otherwise game.map_preset).
        map_seed: Override the game's seed (otherwise game.map_seed).
        hero_overrides: Optional list of hero binding descriptors. Each
            entry is a dict shaped like
            ``{"color": "blue", "x": 2, "y": 2, "hero_id": "yun", "name": "云"}``.
            The helper matches each entry to a freshly-spawned unit and
            applies the hero's name, stat overrides, and ``hero_id`` tag.
            Matching priority is exact ``(color, x, y)`` first, then
            color-only (first unclaimed unit of that color in map order).
            Unmatched overrides log a warning and are skipped — the
            spawn never crashes because a hero was mistyped.
        spawn_overrides: Optional battle-level patch applied to the
            map's ``initial_units`` before Unit rows are materialized.
    """
    game_id = game.id

    preset_id = map_preset or getattr(game, "map_preset", None) or "classic"
    seed = map_seed if map_seed is not None else game.map_seed

    # P2.4 — spectators don't occupy a castle and don't get units.
    # Their seats are above MAX_PLAYERS so castle_positions(seat) is
    # never even asked for them; skip the loop entirely so the
    # spectator's `seat` doesn't accidentally fall into castle_xy.
    real_players = [p for p in players if not p.is_spectator]

    # P2.6 — Data-driven map: tiles + initial_units come from the map
    # definition itself. Custom maps (from /editor/maps) are referenced
    # as "custom:<id>" and bypass the procedural generator but still
    # follow the same `initial_units` schema.
    custom_map_biome: Optional[str] = None
    custom_tile_owners: List[Dict[str, Any]] = []
    result: MapPresetResult
    if preset_id.startswith("custom:"):
        from app.routes.editor import _read_map
        custom_id = preset_id[len("custom:"):]
        data = _read_map(custom_id)
        custom_layout = data["layout"]
        # Use custom map's biome if game doesn't have one explicitly set
        custom_map_biome = data.get("biome", "grass")
        custom_tile_owners = list(data.get("tile_owners", []))
        # Tile grid is sized by the custom map; bypass procedural generator
        grid: List[List[Tile]] = []
        for y, row in enumerate(custom_layout):
            grid_row: List[Tile] = []
            for x, ch in enumerate(row):
                grid_row.append(Tile(
                    game_id=game_id,
                    x=x, y=y,
                    terrain=_char_to_terrain(ch),
                ))
            grid.append(grid_row)
        result = MapPresetResult(
            tiles=grid,
            initial_units=list(data.get("initial_units", [])),
        )
    else:
        result = generate_map_preset(
            preset_id=preset_id,
            seed=seed,
            num_castles=max(2, min(MAX_CASTLES, len(real_players))),
        )
    if spawn_overrides:
        result.initial_units = apply_spawn_overrides(
            list(result.initial_units),
            spawn_overrides,
        )

    # If game.map_biome wasn't set but custom map has one, sync it
    if custom_map_biome and not getattr(game, "map_biome", None):
        game.map_biome = custom_map_biome

    map_size = len(result.tiles)
    tiles: List[Tile] = [t for row in result.tiles for t in row]
    for t in tiles:
        t.game_id = game_id
    session.add_all(tiles)

    # P2.6+ — derive castle ownership from the map's ACTUAL layout instead
    # of using a hard-coded geometry (which silently mis-owned castles on
    # every hand-authored map whose 'C' tiles didn't happen to land on
    # the (2,2) / (12,12) / etc. corners).
    #
    # Algorithm: scan the loaded tiles for TERRAIN_CASTLE in row-major
    # order (top-left → bottom-right) and pair the first N with the
    # first N player seats.  The map author controls which cell is
    # "seat 0's HQ" by placing it earliest in row-major order, which is
    # the natural convention used by all hand-authored maps so far.
    castle_xy: Dict[int, Tuple[int, int]] = {}
    if len(real_players) > 0:
        layout_castles = sorted(
            ((t.x, t.y) for t in tiles if t.terrain == TERRAIN_CASTLE),
            # row-major: by (y, x).  Equal y → leftmost first.
            key=lambda xy: (xy[1], xy[0]),
        )
        for seat, pos in enumerate(layout_castles[: len(real_players)]):
            castle_xy[seat] = pos
        if len(layout_castles) < len(real_players):
            logger.warning(
                "Game %d: layout has %d castle tiles but %d players — "
                "extra players will not own a castle",
                game.id, len(layout_castles), len(real_players),
            )

    # P2.6 — Data-driven spawn: units come from map's initial_units, NOT from a roster.
    # Each entry has {x, y, type, color, level} and is matched to a player by color.
    color_to_player = {p.color: p for p in real_players if p.color}
    units: List[Unit] = []
    existing_count_by_player: Dict[int, int] = {}
    for u in result.initial_units:
        unit_type = u["type"]
        uc = _get_unit_or_none(unit_type)
        if uc is None:
            continue
        target_player = color_to_player.get(u["color"])
        if target_player is None:
            # No matching player for this color — skip
            continue
        pid = target_player.id
        name_idx = existing_count_by_player.get(pid, 0)
        existing_count_by_player[pid] = name_idx + 1
        units.append(Unit(
            player_id=pid,
            unit_type=unit_type,
            name=_unit_name(unit_type, name_idx),
            level=int(u.get("level", 1)),
            exp=0,
            # Spawn-level HP override (test fixtures). When ``u["hp"]``
            # is set, the unit spawns wounded; both current and max
            # collapse to the override so HP bars and ``max_hp``
            # queries stay consistent. ``None`` (default) keeps the
            # class's ``base_hp``.
            hp=int(u["hp"]) if u.get("hp") is not None else uc.base_hp,
            max_hp=int(u["hp"]) if u.get("hp") is not None else uc.base_hp,
            atk=uc.base_atk, def_=uc.base_def,
            matk=uc.base_matk, mdef=uc.base_mdef,
            mov=uc.mp_pool, mp=uc.mp_pool,
            # New units start at 0 stars of morale; the gold-star UI
            # is preserved as three empty ★☆☆ indicators and the
            # engine bumps it by 1 per kill up to MORALE_MAX (3).
            morale=0,
            x=int(u["x"]), y=int(u["y"]),
            has_acted=False, has_moved=False,
            skills=list(uc.default_skills),
        ))
    if units:
        session.add_all(units)
    await session.flush()

    # P2.6+ — apply hero overrides on top of the freshly-spawned units.
    # The base-class unit is already persisted; we just mutate its
    # name / stats / hero_id tag so the hero "wears" the base class.
    if hero_overrides:
        _apply_hero_overrides(units, hero_overrides, real_players)

    for player in real_players:
        owned_units = [unit for unit in units if unit.player_id == player.id]
        if owned_units:
            from types import SimpleNamespace
            target = SimpleNamespace(commander_id=player.commander_id,
                                     units=owned_units, co_state=player.co_state)
            bake_passive_into_units(target)
            player.co_state = target.co_state

    # The initial current player has already started turn 1 when battle
    # creation completes; record that lifecycle edge immediately.
    first_player = next(
        (p for p in real_players if p.seat == game.current_player_index), None,
    )
    if first_player is not None:
        from types import SimpleNamespace
        target = SimpleNamespace(
            commander_id=first_player.commander_id,
            units=[u for u in units if u.player_id == first_player.id],
            co_state=first_player.co_state,
        )
        from app.commanders.effects import on_player_turn_start
        on_player_turn_start(target, game.turn_number)
        first_player.co_state = target.co_state

    seat_to_player = {p.seat: p for p in players}
    for seat, (cx, cy) in castle_xy.items():
        for t in tiles:
            if t.x == cx and t.y == cy:
                t.owner_id = seat_to_player[seat].id
                logger.info(f"Game {game.id}: castle at ({cx},{cy}) assigned to player {seat_to_player[seat].id}(seat={seat})")
                break

    # P0.4 — assign initial ownership of income buildings near each castle
    # so players can collect income from turn 1.
    from app.config import TERRAIN_VILLAGE, TERRAIN_BARRACKS
    for seat, (cx, cy) in castle_xy.items():
        pid = seat_to_player[seat].id
        for t in tiles:
            if t.terrain in (TERRAIN_VILLAGE, TERRAIN_BARRACKS):
                # Find closest castle by Manhattan distance
                min_dist = float('inf')
                closest_seat = None
                for s, (sx, sy) in castle_xy.items():
                    dist = abs(t.x - sx) + abs(t.y - sy)
                    if dist < min_dist:
                        min_dist = dist
                        closest_seat = s
                # Assign to the closest castle's owner
                if closest_seat == seat:
                    t.owner_id = pid
                    logger.debug(f"Game {game.id}: income building ({t.terrain}) at ({t.x},{t.y}) -> player {pid}(seat={seat}), dist={min_dist}")

    if custom_tile_owners:
        for owner in custom_tile_owners:
            color = str(owner.get("color", ""))
            target_player = color_to_player.get(color)
            if target_player is None:
                logger.warning(
                    "Game %d: tile owner color %r at (%s,%s) has no player; skipped",
                    game.id, color, owner.get("x"), owner.get("y"),
                )
                continue
            ox = int(owner.get("x", -1))
            oy = int(owner.get("y", -1))
            for t in tiles:
                if t.x == ox and t.y == oy:
                    t.owner_id = target_player.id
                    logger.debug(
                        "Game %d: custom tile owner (%d,%d) -> player %d color=%s",
                        game.id, ox, oy, target_player.id, color,
                    )
                    break

    for u in units:
        for t in tiles:
            if t.x == u.x and t.y == u.y:
                t.occupied_unit_id = u.id
                break

    # P2.3 — convert the reach-mode target (x, y) that was stashed
    # on the Game row at create-game time into a real Tile FK. We do
    # this AFTER the tiles have been created so we can look up the
    # tile_id reliably. If the (x, y) doesn't exist (bad preset or
    # someone set reach on a 15x15 map pointing at (99, 99)) we
    # just clear the pending value and the game falls back to rout
    # when no team has units (the existing default).
    if game.win_condition == "reach":
        xy = getattr(game, "_pending_reach_xy", None)
        if xy is not None:
            for t in tiles:
                if t.x == xy[0] and t.y == xy[1]:
                    game.reach_tile_id = t.id
                    break
        if game.reach_tile_id is None:
            # No valid target found — quietly demote to rout so the
            # game still ends in a sane way.
            game.win_condition = "rout"
        # Clean up the transient attribute so it never reaches the
        # session and pollutes future model serializations.
        if hasattr(game, "_pending_reach_xy"):
            del game._pending_reach_xy

    game.status = "playing"
    # P2.4 — pick the LOWEST non-spectator seat as the first player
    # so a host who converted to spectator doesn't leave
    # current_player_index stuck at their former real-player seat
    # (where there's now an AI or nothing).
    real_seats = sorted(p.seat for p in players if not p.is_spectator)
    game.current_player_index = real_seats[0] if real_seats else 0
    for p in players:
        p.has_ended_turn = False





@router.post("", response_model=GameSummaryOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    body: CreateGameRequest,
    session: AsyncSession = Depends(get_session),
) -> GameSummaryOut:
    seed = body.map_seed if body.map_seed is not None else random.randint(0, 2**31 - 1)
    # P2.9 — defensive expansion. expand_battle_config with strict=True
    # raises UnknownBattleTrackError on a bad track_id; we convert that
    # to HTTP 400 before reaching the DB session so the client gets a
    # clear message and the available track list. The validator only
    # fires when battle_config is actually supplied, so existing
    # create_game callers without BGM continue to work.
    try:
        battle_config = _expand_user_battle_config(body.battle_config)
    except UnknownBattleTrackError as exc:
        available = ", ".join(exc.available) if exc.available else "(none)"
        logger.warning(
            "create_game rejected: unknown bgm track_id=%r available=%s",
            exc.track_id, available,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unknown bgm track_id: {exc.track_id!r} (available: {available})",
        )
    commander_id = battle_config.get("commander")
    _validate_commander_id(commander_id)
    for ai_commander_id in (battle_config.get("ai_commanders") or {}).values():
        _validate_commander_id(ai_commander_id)
    # P2.4 — derive capacity from the chosen map's recommended_players.
    # `_effective_max_players` clamps to [MIN_PLAYERS, MAX_PLAYERS] and
    # falls back to the global cap when the preset doesn't declare one.
    capacity = _effective_max_players(body.map_preset)
    game = Game(
        name=body.name,
        status="waiting",
        turn_number=1,
        current_player_index=0,
        map_seed=seed,
        map_preset=body.map_preset,
        map_biome=body.map_biome,
        # P2.3 — victory condition.
        win_condition=body.win_condition,
        defend_turns=body.defend_turns,
        # P2.4 — per-room capacity derived from the map.
        capacity=capacity,
        # P2.4 — spectator slots are independent of capacity (a full
        # room can still attract an audience). Falls back to
        # DEFAULT_MAX_SPECTATORS; future versions may let the host
        # override at create-time.
        max_spectators=DEFAULT_MAX_SPECTATORS,
        # Strict mode: reject unknown track_ids at create-time instead
        # of persisting a battle_config the frontend cannot play. Caught
        # below and surfaced as HTTP 400 with the available list.
        battle_config=battle_config,
    )
    # P2.3 — for "reach" mode, look up the target tile so we can
    # render the goal pulse on the client + drive the win check.
    # We don't have tiles yet (those are created in _start_battle_internal
    # after the lobby is filled), so we stash the (x, y) on the Game
    # row for now and translate to reach_tile_id at start time.
    if body.win_condition == "reach" and body.reach_tile:
        # Persist as a transient attribute; the migration in
        # _start_battle_internal reads it back before populating
        # reach_tile_id. Cheaper than adding a second column.
        game._pending_reach_xy = (
            int(body.reach_tile["x"]), int(body.reach_tile["y"])
        )
    session.add(game)
    await session.flush()
    logger.info(
        "Game created: id=%d name=%r seed=%d capacity=%d map_preset=%s biome=%s",
        game.id, game.name, seed, capacity, body.map_preset, body.map_biome,
    )
    return GameSummaryOut.model_validate(game)


@router.post("/{game_id}/join", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join_game(
    game_id: int,
    body: JoinGameRequest,
    session: AsyncSession = Depends(get_session),
) -> PlayerOut:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始")

    existing = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()

    # P2.4 — spectator vs player gate. Spectators have their own
    # counter (`existing_spectators`) and capacity (`game.max_spectators`).
    # Players share `(game_id, seat)` UNIQUE so spectator seats must be
    # offset to avoid colliding with seat=0..N-1 of the real players.
    is_spectator = (body.role == "spectator")
    if is_spectator:
        existing_spectators = [p for p in existing if p.is_spectator]
        if len(existing_spectators) >= game.max_spectators:
            raise HTTPException(status.HTTP_409_CONFLICT, "观战席已满")
        # Spectators don't get a real color; reserve a neutral grey
        # sentinel that can't clash with DEFAULT_PLAYER_COLORS. We
        # still satisfy the (game_id, color) UNIQUE constraint.
        used_colors_incl_spectators = [p.color for p in existing]
        color = "spectator" if "spectator" not in used_colors_incl_spectators else \
                f"spectator_{len(existing_spectators)}"
    else:
        used_colors = [p.color for p in existing if not p.is_spectator]
        if len([p for p in existing if not p.is_spectator]) >= game.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, "房间已满")
        if body.seat is not None:
            if body.seat >= game.capacity:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "座位不存在")
            if any(p.seat == body.seat and not p.is_spectator for p in existing):
                raise HTTPException(status.HTTP_409_CONFLICT, "座位已被占用")
        color = _color_for_seat(body.seat) if body.seat is not None else (body.color or "")
        if not color or color in used_colors:
            color = _next_color(used_colors)

    if any(p.user_name == body.user_name for p in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "此游戏中用户名已被占用")

    # P2.4 — spectator seats live above real players' seats. Real
    # player seats are dense (0..N-1) to keep alive_seats math simple
    # in turns.py; spectator seats start at MAX_PLAYERS (4) so they
    # never collide with a real seat even on a 2-player map.
    if is_spectator:
        existing_real_seats = [p.seat for p in existing if not p.is_spectator]
        spectator_offset = len([p for p in existing if p.is_spectator])
        # Place spectators starting from MAX_PLAYERS so they never
        # shadow a real seat (even after player removals renumber
        # real seats back down).
        seat = MAX_PLAYERS + spectator_offset
    else:
        if body.seat is not None:
            seat = body.seat
        else:
            used_real_seats = {p.seat for p in existing if not p.is_spectator}
            seat = next((s for s in range(game.capacity) if s not in used_real_seats), len(used_real_seats))

    # P2.3 — team_id resolution. Spectators don't pick a team.
    if is_spectator:
        team_id = None
    else:
        team_id = body.team if body.team else None

    player = Player(
        game_id=game_id,
        user_name=body.user_name,
        color=color,
        seat=seat,
        team_id=team_id,
        is_spectator=is_spectator,
    )
    session.add(player)
    try:
        await session.flush()
        # P2.3 — commit so other sessions (and follow-up HTTP calls
        # in the same request) immediately see the new row. Without
        # this, the team's color-resolution step in the next join
        # doesn't see the just-created Player.
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        # Surface the actual constraint that fired for diagnostics
        # (the client's Chinese 409 message is fine either way).
        import logging
        logging.getLogger(__name__).warning("join IntegrityError: %s", e)
        audit.warning(
            "USER_ACTION | user=%s | game=%d | action=JOIN | result=FAIL | reason=constraint_violation",
            body.user_name, game_id,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "加入失败（约束冲突）")

    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=JOIN | result=SUCCESS | "
        "user_name=%s | color=%s | seat=%d",
        player.id, game_id, player.user_name, player.color, player.seat,
    )
    logger.info(
        "Player joined: id=%d game=%d name=%r color=%s seat=%d",
        player.id, game_id, player.user_name, player.color, player.seat,
    )

    return PlayerOut(
        id=player.id,
        user_name=player.user_name,
        color=player.color,
        is_alive=player.is_alive,
        has_ended_turn=player.has_ended_turn,
        seat=player.seat,
        is_ai=player.is_ai,
        team=player.team_id,
        gold=player.gold or 0,
        is_spectator=player.is_spectator,
        units=[],
    )


@router.patch("/{game_id}/players/{player_id}/team")
async def update_player_team(
    game_id: int,
    player_id: int,
    body: UpdateTeamRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a player's team in the lobby.

    - The host (seat 0) may change **any** player's team (including AI).
    - Other players may only change their **own** team.
    - Game must be in 'waiting' status.
    - Set team to empty / null to enter 自由模式 (no team).
    """
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始，无法修改队伍")

    target = await session.get(Player, player_id)
    if target is None or target.game_id != game_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不存在")

    # Load all players to determine host (seat 0).
    all_players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()
    host = _host_player(all_players)

    # The caller identifies themselves in the request body.
    # (In a LAN game without real auth, the frontend gates the UI;
    #  this check is a safety net, not a fortress.)
    caller = next((p for p in all_players if p.id == body.caller_player_id), None)
    if caller is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法识别请求者")

    # Permission check
    is_host = host is not None and caller.id == host.id
    is_self = caller.id == target.id
    if not (is_host or is_self):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有房主可以修改其他玩家的队伍")

    target.team_id = body.team if body.team else None
    await session.flush()

    return {"ok": True, "player_id": player_id, "team": target.team_id}


@router.patch("/{game_id}/players/{player_id}/seat", response_model=GameStateOut)
async def update_player_seat(
    game_id: int,
    player_id: int,
    body: UpdateSeatRequest,
    session: AsyncSession = Depends(get_session),
) -> GameStateOut:
    """Move a waiting-room player to a seat, swapping occupants for the host."""
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始，无法修改座位")
    if body.seat >= game.capacity:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "座位不存在")

    target = await session.get(Player, player_id)
    if target is None or target.game_id != game_id or target.is_spectator:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")

    all_players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()
    caller = next((p for p in all_players if p.id == body.caller_player_id), None)
    if caller is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法识别请求者")
    host = _host_player(all_players)
    is_host = host is not None and caller.id == host.id
    is_self = caller.id == target.id
    if not (is_host or is_self):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有房主可以移动其他玩家")

    occupant = next(
        (p for p in all_players if not p.is_spectator and p.seat == body.seat and p.id != target.id),
        None,
    )
    if occupant is not None and not is_host:
        raise HTTPException(status.HTTP_409_CONFLICT, "座位已被占用")

    old_seat = target.seat
    if occupant is not None:
        target.seat = -1 - target.id
        target.color = f"seat_swap_{target.id}"
        await session.flush()
        occupant.seat = old_seat
        occupant.color = _color_for_seat(old_seat)
    target.seat = body.seat
    target.color = _color_for_seat(body.seat)
    await session.flush()
    return await _build_state(session, game)


@router.patch("/{game_id}/players/{player_id}/commander")
async def update_player_commander(
    game_id: int,
    player_id: int,
    body: UpdateCommanderRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pick the commander for a player in the lobby.

    - The host (seat 0) may change **any** player's commander (including AI).
    - Other players may only change their **own** commander.
    - Game must be in 'waiting' status.
    - Side effect: also writes ``game.battle_config.seat_commanders[seat]``
      so the choice survives through /start and is applied at game start.
    """
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始，无法修改指挥官")

    target = await session.get(Player, player_id)
    if target is None or target.game_id != game_id or target.is_spectator:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")

    all_players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()
    caller = next((p for p in all_players if p.id == body.caller_player_id), None)
    if caller is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法识别请求者")
    host = _host_player(all_players)
    is_host = host is not None and caller.id == host.id
    is_self = caller.id == target.id
    if not (is_host or is_self):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有房主可以修改其他玩家的指挥官")

    target.commander_id = body.commander_id
    # Mirror to game.battle_config.seat_commanders so /start picks it up
    battle_config = dict(game.battle_config or {})
    seat_commanders = dict(battle_config.get("seat_commanders") or {})
    seat_commanders[str(target.seat)] = body.commander_id
    battle_config["seat_commanders"] = seat_commanders
    game.battle_config = battle_config
    await session.flush()

    return {"ok": True, "player_id": player_id, "seat": target.seat,
            "commander_id": body.commander_id}


@router.post("/{game_id}/rejoin", response_model=RejoinGameResponse)
async def rejoin_game(
    game_id: int,
    body: RejoinGameRequest,
    session: AsyncSession = Depends(get_session),
) -> RejoinGameResponse:
    """Resume an existing player in a game using their player_id.

    This is what the client calls on page load when it has a stored session.
    Works for any game status (waiting / playing / finished).
    """
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    player = await session.get(Player, body.player_id)
    if player is None or player.game_id != game_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")
    return RejoinGameResponse(
        game_id=game.id,
        game_status=game.status,
        player=PlayerOut(
            id=player.id,
            user_name=player.user_name,
            color=player.color,
            is_alive=player.is_alive,
            has_ended_turn=player.has_ended_turn,
            seat=player.seat,
            is_ai=player.is_ai,
            team=player.team_id,
            gold=player.gold or 0,
            is_spectator=player.is_spectator,
            units=[],
        ),
    )


class RejoinByNameRequest(BaseModel):
    user_name: str


@router.post("/{game_id}/rejoin_by_name", response_model=RejoinGameResponse)
async def rejoin_by_name(
    game_id: int,
    body: RejoinByNameRequest,
    session: AsyncSession = Depends(get_session),
) -> RejoinGameResponse:
    """Resume a game by user_name (used by the "从记录开始" save-slot button).

    The client knows the game's id (from the save slot) and the player's
    user_name (from settings) but not the player_id. This endpoint looks up
    the matching Player row by (game_id, user_name).
    """
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    player = (
        await session.execute(
            select(Player).where(
                Player.game_id == game_id, Player.user_name == body.user_name
            )
        )
    ).scalars().first()
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该存档中没有此用户名的玩家")
    return RejoinGameResponse(
        game_id=game.id,
        game_status=game.status,
        player=PlayerOut(
            id=player.id,
            user_name=player.user_name,
            color=player.color,
            is_alive=player.is_alive,
            has_ended_turn=player.has_ended_turn,
            seat=player.seat,
            is_ai=player.is_ai,
            team=player.team_id,
            gold=player.gold or 0,
            is_spectator=player.is_spectator,
            units=[],
        ),
    )


@router.post("/{game_id}/start", response_model=GameStateOut)
async def start_game(
    game_id: int,
    session: AsyncSession = Depends(get_session),
) -> GameStateOut:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status == "playing":
        # Idempotent: return current state
        return await _build_state(session, game)
    if game.status == "finished":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已经结束")

    players = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()
    # P2.4 — only real players (no spectators) count toward MIN_PLAYERS.
    real_player_count = sum(1 for p in players if not p.is_spectator)
    if real_player_count < MIN_PLAYERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"need at least {MIN_PLAYERS} players (currently {real_player_count})",
        )

    battle_config = game.battle_config or {}
    host_commander = battle_config.get("commander")
    ai_commanders = battle_config.get("ai_commanders") or {}
    seat_commanders = battle_config.get("seat_commanders") or {}
    for player in players:
        commander_id = None
        if not player.is_spectator:
            commander_id = seat_commanders.get(player.seat) or seat_commanders.get(str(player.seat))
        if not player.is_spectator and player.seat == 0:
            commander_id = commander_id or host_commander
        if player.is_ai:
            commander_id = commander_id or ai_commanders.get(player.seat) or ai_commanders.get(str(player.seat))
        if commander_id:
            player.commander_id = commander_id
            player.co_state = {
                "commander_id": commander_id,
                "meter": 0,
                "threshold": get_power_threshold(commander_id),
                "is_power_active": False,
                "last_start_turn": -1,
            }

    await _start_battle_internal(session, game, players)

    # P0.4 — collect income for the first player at game start so turn 1
    # income is granted based on initial building ownership.
    from app.routes.turns import _collect_income_for_player

    # Force a flush so the tile.owner_id assignments from
    # `_start_battle_internal` are visible to the SELECT inside
    # `_collect_income_for_player`. Without this, the ownership
    # changes are still pending in the session and the income
    # query returns zero tiles.
    await session.flush()

    # P2.6 fix — grant initial income to EVERY non-spectator player,
    # not just seat 0. Previously only the first player got it, so
    # seats 1..N had to wait for their first turn cycle to receive
    # gold for the buildings they already own at game start.
    for p in players:
        if not p.is_spectator:
            await _collect_income_for_player(session, game, p)

    # P2.4 — schedule the very first turn. In a real-player-first
    # setup, the human gets to act and AI will be chained from
    # end_turn. But when the FIRST seat belongs to an AI (e.g. the
    # only "real" player converts to spectator and all that's left
    # are AI), nothing kicks off the AI's loop, so the game stalls
    # in phase="player" forever. Detect that case and spawn the
    # background chain so AI can take its first turn.
    real_players_seats = sorted(p.seat for p in players if not p.is_spectator)
    if real_players_seats:
        first_seat = real_players_seats[0]
        first_player = next(p for p in players if p.seat == first_seat and not p.is_spectator)
        if first_player.is_ai:
            game.phase = "ai"
            from app.routes.turns import _run_ai_turn_chain
            asyncio.create_task(_run_ai_turn_chain(game.id))
        else:
            # Even when first is human, set phase='player' explicitly
            # (in case DB default drifted or was wrong).
            game.phase = "player"

    # P2.6 — units are now data-driven by initial_units per map; the log
    # line below uses the spawned count from the DB. Falling back to 0 if
    # the spawn hasn't happened yet.
    roster_total = 0  # Filled in by _start_battle_internal; pre-start placeholder

    session.add(
        ActionLog(
            game_id=game_id,
            turn_number=game.turn_number,
            player_id=None,
            action_type="system",
            description=f"游戏开始，玩家：{len(players)} 人",
        )
    )

    logger.info(
        "Game started: id=%d players=%d units=%d map_preset=%s seed=%d",
        game_id, len(players),
        roster_total * len(players),
        getattr(game, "map_preset", None) or "classic", game.map_seed,
    )
    audit.info(
        "USER_ACTION | user=system | game=%d | action=GAME_START | result=SUCCESS | "
        "players=%d",
        game_id, len(players),
    )

    return await _build_state(session, game)


@router.get("/{game_id}/lobby", response_model=LobbyInfoOut)
async def get_lobby_info(
    game_id: int,
    session: AsyncSession = Depends(get_session),
) -> LobbyInfoOut:
    """P2.3 — compact lobby view that lets the front-end render
    'join the red team' dropdowns without first fetching the full
    game state.

    Aggregates the players in the game by team_id (or by color
    when team_id is unset). The capacity field is 0 today
    (no enforced per-team cap); when we add 2v2 hard caps, the
    front-end can grey out the Join button when capacity is hit.
    """
    from collections import Counter
    from app.schemas import LobbyTeamOut

    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")

    players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()

    # Use the same team_id resolution as check_win_condition: 1V1
    # free-for-all (no team_id set) becomes its own team per player
    # so the rout / seize / reach / defend logic works without
    # forcing the joiner to set an explicit team.
    from app.game_logic import _team_of
    team_buckets: dict[str, list] = {}
    for p in players:
        t = _team_of(p)
        team_buckets.setdefault(t, []).append(p)

    teams_out: list[LobbyTeamOut] = []
    for t, members in sorted(team_buckets.items()):
        colors = Counter(m.color for m in members)
        rep_color, _count = colors.most_common(1)[0]
        teams_out.append(LobbyTeamOut(
            team=t,
            player_count=len(members),
            color=rep_color,
            is_full=len(players) >= MAX_PLAYERS and len(members) >= 1,
            capacity=0,
        ))

    return LobbyInfoOut(
        game_id=game.id,
        status=game.status,
        # P2.4 — `max_players` reflects the room's actual capacity
        # (driven by the chosen map preset), not the global MAX_PLAYERS.
        max_players=game.capacity,
        player_count=len(players),
        teams=teams_out,
        win_condition=game.win_condition,
        win_reason=game.win_reason,
    )


@router.get("/{game_id}/state", response_model=GameStateOut)
async def get_game_state(
    game_id: int,
    session: AsyncSession = Depends(get_session),
) -> GameStateOut:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    return await _build_state(session, game)


@router.get("", response_model=List[GameSummaryOut])
async def list_games(
    user_name: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> List[GameSummaryOut]:
    """List games. If ``user_name`` is provided, only games where a player
    with that user_name participated are returned (used by save management
    so users don't see other players' saves)."""
    if user_name:
        # Only games where the named player is a participant
        sq = select(Player.game_id).where(Player.user_name == user_name).subquery()
        stmt = select(Game).where(Game.id.in_(sq)).order_by(Game.id.desc())
    else:
        stmt = select(Game).order_by(Game.id.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [GameSummaryOut.model_validate(g) for g in rows]


@router.get("/presets", response_model=PresetsResponse)
async def list_presets() -> PresetsResponse:
    """Return available map and unit-composition presets for the create-game form.

    Includes both built-in presets (game/maps/*.json) AND user-designed maps
    saved via the map editor (game/maps/custom/*.json). Custom maps are
    prefixed with "custom:" so the frontend can distinguish them.
    """
    from app.game_logic import MAP_PRESETS, _resolve_size
    from app.routes.editor import _CUSTOM_DIR, _list_custom_maps
    maps: List[PresetInfo] = [
        PresetInfo(
            id=p["id"], name=p["name"], description=p["description"],
            biome=p.get("biome", "grass"),
            # P2.6 — size may be {width, height} dict on new presets; the
            # API still exposes a single int (we use width as the canonical
            # edge length for the square-grid legacy UI).
            size=_resolve_size(p.get("size", 15))["width"],
            # P2.4 — expose recommended_players so the create-game
            # category selector on the frontend can filter by it.
            recommended_players=p.get("recommended_players"),
            # P2.4 polish — pass designer notes through (legacy
            # reach/defend maps carry a ⚠️ deprecation warning).
            notes=p.get("notes"),
        )
        for p in MAP_PRESETS.values()
    ]
    # Append user-designed maps
    for m in _list_custom_maps(_CUSTOM_DIR):
        maps.append(PresetInfo(
            id=f"custom:{m['id']}",
            name=f"📐 {m['name']}",
            description=f"自定义地图 · {m['width']}×{m['height']} · {m['biome']}",
            biome=m["biome"],
            # Custom maps have no recommended_players declared; server
            # falls back to MAX_PLAYERS=4 (the global cap).
            recommended_players=None,
        ))
    return PresetsResponse(maps=maps)


@router.get("/skills")
async def list_skills():
    """Return metadata for all skills (for frontend reference panel)."""
    from app.classes.units.skills import list_all as _list_all_skills
    return [
        {
            "skill_id": s.skill_id,
            "display_cn": s.display_cn,
            "display_en": s.display_en,
            "is_passive": s.is_passive,
            "default_users": s.default_users,
        }
        for s in _list_all_skills()
    ]


@router.get("/units")
async def list_unit_classes():
    """Return metadata for all unit classes (glyph, skills, stats, etc.).
    The frontend uses this to render units without hardcoding type info."""
    from app.classes.units import list_all
    return [
        {
            "type_id": u.type_id,
            "display_cn": u.display_cn,
            "display_en": u.display_en,
            "glyph": u.glyph,
            "base_hp": u.base_hp,
            "base_atk": u.base_atk,
            "base_def": u.base_def,
            "base_matk": u.base_matk,
            "base_mdef": u.base_mdef,
            "attack_kind": u.attack_kind,
            "base_mov": u.base_mov,
            "mp_pool": u.mp_pool,
            "attack_range": u.attack_range,
            "can_move_after_action": u.can_move_after_action,
            "default_skills": list(u.default_skills),
            "strong_against": list(u.strong_against),
            "terrain_movement": {
                terrain: dict(rule) for terrain, rule in u.terrain_movement.items()
            },
        }
        for u in list_all()
    ]


@router.post("/{game_id}/add-ai", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def add_ai_player(
    game_id: int,
    body: AddAIRequest,
    session: AsyncSession = Depends(get_session),
) -> PlayerOut:
    """Add an AI-controlled player to a waiting game."""
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始")
    players = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()
    if len([p for p in players if not p.is_spectator]) >= game.capacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "房间已满")
    used_colors = [p.color for p in players]
    color = _next_color(used_colors)
    # P2.4 — AI seats must ONLY consider real players; spectator
    # seats live in [MAX_PLAYERS..], separate from the castable
    # range, so an add_ai call must not "jump past" them.
    seat = max((p.seat for p in players if not p.is_spectator), default=-1) + 1
    # Generate a unique AI name
    ai_count = sum(1 for p in players if p.is_ai)
    backend_tag = body.agent_kind  # "rules" or "llm"
    ai_name = f"电脑-{ai_count + 1}-{body.difficulty}-{backend_tag}"
    if any(p.user_name == ai_name for p in players):
        ai_name = f"电脑-{ai_count + 1}-{body.difficulty}-{seat}"
    ai = build_ai_player(game, seat=seat, color=color, name=ai_name)
    ai.agent_kind = body.agent_kind
    ai.agent_personality = body.personality
    session.add(ai)
    await session.flush()
    return PlayerOut(
        id=ai.id, user_name=ai.user_name, color=ai.color,
        is_alive=ai.is_alive, has_ended_turn=ai.has_ended_turn,
        seat=ai.seat, is_ai=ai.is_ai,
        agent_kind=ai.agent_kind, agent_personality=ai.agent_personality,
        team=None, is_spectator=False,
        gold=0,
        units=[],
    )


@router.delete("/{game_id}/players/{player_id}", response_model=GameStateOut)
async def remove_player(
    game_id: int,
    player_id: int,
    session: AsyncSession = Depends(get_session),
) -> GameStateOut:
    """Remove an AI (or any pre-start) player from a waiting game."""
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已开始")
    player = await session.get(Player, player_id)
    if player is None or player.game_id != game_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")
    # Free the player's seat (cascade will remove their units)
    await session.delete(player)
    await session.flush()
    # P2.4 — re-number remaining REAL player seats so they're
    # contiguous. Spectators live in a separate range (above
    # MAX_PLAYERS) so they MUST be excluded from this loop;
    # otherwise a remove would yank a spectator down to seat 0
    # and break turn-cycle math.
    remaining_real = (
        await session.execute(
            select(Player)
            .where(Player.game_id == game_id, Player.is_spectator.is_(False))
            .order_by(Player.seat)
        )
    ).scalars().all()
    for new_seat, p in enumerate(remaining_real):
        if p.seat != new_seat:
            p.seat = new_seat
    # Also pack spectator seats contiguously above MAX_PLAYERS so the
    # spectator offset lookup in join_game remains predictable.
    remaining_spec = (
        await session.execute(
            select(Player)
            .where(Player.game_id == game_id, Player.is_spectator.is_(True))
            .order_by(Player.seat)
        )
    ).scalars().all()
    for offset, p in enumerate(remaining_spec):
        target = MAX_PLAYERS + offset
        if p.seat != target:
            p.seat = target
    return await _build_state(session, game)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a saved game (and all related rows via cascade).

    Used by the in-game "存档管理" screen so users can wipe a stale slot
    when a schema change breaks an old save.
    """
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    await session.delete(game)
    await session.flush()


# ============================================================
# Helpers
# ============================================================

def _with_combat_stats(unit: Unit) -> dict:
    """Augment a Unit row with the class-level attack-range stats the
    client needs to render range overlays (otherwise the UI has to
    hard-code the values per unit type and they drift out of sync).

    Skills (e.g. archer's `snipe`) may further modify these values on
    the server; here we just expose the class defaults. The frontend
    should also treat `attack_range` as the *base* and apply its own
    knowledge of skills when relevant.
    """
    from app.classes.units import get as _get_unit
    profile = _get_unit(unit.unit_type)
    from app.movement import resolve_movement_profile
    return {
        **unit.__dict__,
        "attack_range": profile.attack_range,
        "min_attack_range": profile.min_attack_range,
        "terrain_movement": resolve_movement_profile(unit).as_dict(),
    }


async def _build_state(session: AsyncSession, game: Game) -> GameStateOut:
    """Assemble full game state in one query batch."""
    players = (
        await session.execute(
            select(Player).where(Player.game_id == game.id).order_by(Player.seat)
        )
    ).scalars().all()

    units = (
        await session.execute(
            select(Unit).where(Unit.player_id.in_([p.id for p in players]))
        )
    ).scalars().all() if players else []
    units_by_player: dict = {}
    for u in units:
        units_by_player.setdefault(u.player_id, []).append(u)

    tiles = (
        await session.execute(
            select(Tile).where(Tile.game_id == game.id).order_by(Tile.y, Tile.x)
        )
    ).scalars().all()

    logs = (
        await session.execute(
            select(ActionLog).where(ActionLog.game_id == game.id).order_by(ActionLog.id.desc()).limit(50)
        )
    ).scalars().all()

    # P2.4 polish — surface active claim sessions so the client can
    # render a "X turns remaining" progress indicator on the tile.
    # (Without this, players only see a toast and forget their
    # claim is mid-flight.)
    from app.models import ClaimSession as _ClaimSession
    pending_claims_rows = (
        await session.execute(
            select(_ClaimSession).where(_ClaimSession.game_id == game.id)
        )
    ).scalars().all()
    # Map each session's tile_id → (x, y) via the already-loaded tiles.
    tile_by_id = {t.id: t for t in tiles}
    pending_claims = []
    for cs in pending_claims_rows:
        tile = tile_by_id.get(cs.tile_id)
        if tile is None:
            continue  # session pointing at a deleted tile — skip
        pending_claims.append({
            "tile_id":        cs.tile_id,
            "tile_x":         tile.x,
            "tile_y":         tile.y,
            "started_turn":   cs.started_turn,
            "completes_turn": cs.completes_turn,
            "turns_remaining": max(0, cs.completes_turn - game.turn_number),
            "total_turns":    max(1, cs.completes_turn - cs.started_turn),
            "target_player_id": cs.target_player_id,
        })

    # Current player = first alive player whose seat >= current_player_index, else wrap.
    current_player_id = None
    if players:
        alive_seats = sorted(p.seat for p in players if p.is_alive and not p.is_spectator)
        if alive_seats:
            seat = next(
                (s for s in alive_seats if s >= game.current_player_index),
                alive_seats[0],
            )
            current_player_id = next(p.id for p in players if p.seat == seat)

    return GameStateOut(
        game=GameSummaryOut.model_validate(game),
        tiles=[TileOut.model_validate(t) for t in tiles],
        players=[
            PlayerOut(
                id=p.id,
                user_name=p.user_name,
                color=p.color,
                is_alive=p.is_alive,
                has_ended_turn=p.has_ended_turn,
                seat=p.seat,
                is_ai=p.is_ai,
                agent_kind=p.agent_kind,
                agent_personality=p.agent_personality,
                team=p.team_id,
                gold=p.gold or 0,
                is_spectator=p.is_spectator,
                units=[
                    UnitOut.model_validate(
                        _with_combat_stats(u)
                    )
                    for u in sorted(units_by_player.get(p.id, []), key=lambda x: (x.unit_type, x.id))
                ],
            )
            for p in players
        ],
        current_player_id=current_player_id,
        logs=[ActionLogOut.model_validate(l) for l in logs],
        # P2.4 polish — client uses this to draw a "X turns remaining"
        # progress indicator on the tile.
        pending_claims=pending_claims,
        co_states=[
            PlayerCOStateOut(
                player_id=p.id,
                seat=p.seat,
                color=p.color,
                commander_id=p.commander_id,
                meter=(p.co_state or {}).get("meter", 0),
                threshold=(p.co_state or {}).get("threshold", 20),
                is_power_active=(p.co_state or {}).get("is_power_active", False),
                can_fire=(
                    can_player_fire_now(p, game, players)
                    and can_fire_co_power(p)
                ),
            )
            for p in players
        ],
    )
