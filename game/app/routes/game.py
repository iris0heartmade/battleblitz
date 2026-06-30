"""
Game-lifecycle routes: create, join, fetch state, start.

`start_game` is a thin wrapper around the module-level
`_start_battle_internal()` helper so that other modules (notably the
mainline routes) can spawn battles without going through the public
`POST /games/{id}/start` endpoint and its player-count guard.
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    CASTLES_PER_GAME,
    DEFAULT_PLAYER_COLORS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    TERRAIN_CASTLE,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_PLAIN,
    TERRAIN_RIVER,
)
from app.database import get_session
from app.game_logic import (
    castle_positions,
    generate_map_preset,
    get_roster_for_composition,
    build_ai_player,
)
from app.models import ActionLog, Game, Player, Tile, Unit
from app.schemas import (
    AddAIRequest,
    CreateGameRequest,
    GameStateOut,
    GameSummaryOut,
    JoinGameRequest,
    PlayerOut,
    PresetInfo,
    PresetsResponse,
    RejoinGameRequest,
    RejoinGameResponse,
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


async def _ensure_started_or_400(game: Game) -> None:
    if game.status not in ("waiting", "playing"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "游戏已结束")


# ============================================================
# Module-level helper used by /games/{id}/start AND by mainline routes
# ============================================================

_CHAR_TO_TERRAIN = {
    "P": TERRAIN_PLAIN,
    "F": TERRAIN_FOREST,
    "M": TERRAIN_MOUNTAIN,
    "R": TERRAIN_RIVER,
    "C": TERRAIN_CASTLE,
}


def _char_to_terrain(ch: str) -> str:
    """Map a single ASCII char (P/F/M/R/C) to its terrain string id."""
    return _CHAR_TO_TERRAIN.get(ch, TERRAIN_PLAIN)

async def _start_battle_internal(
    session: AsyncSession,
    game: Game,
    players: List[Player],
    *,
    map_preset: Optional[str] = None,
    map_seed: Optional[int] = None,
    roster: Optional[Dict[str, int]] = None,
    rosters_by_seat: Optional[Dict[int, Dict[str, int]]] = None,
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
        roster: Caller-supplied unit roster; if ``None``, derives from
            ``game.unit_composition`` via ``get_roster_for_composition``.
            Applied to EVERY player when ``rosters_by_seat`` is None.
        rosters_by_seat: Optional per-seat roster override map, e.g.
            ``{0: {"swordsman": 3, "archer": 1}, 1: {"knight": 4}}``.
            When provided, takes precedence over ``roster``.
    """
    game_id = game.id

    preset_id = map_preset or getattr(game, "map_preset", None) or "classic"
    seed = map_seed if map_seed is not None else game.map_seed

    # Custom maps (from /editor/maps) are referenced as "custom:<id>" in the
    # preset field. Load their layout + initial_units directly instead of
    # running the procedural generator.
    custom_layout: Optional[List[str]] = None
    custom_units: Optional[List[Dict[str, Any]]] = None
    custom_map_biome: Optional[str] = None
    if preset_id.startswith("custom:"):
        from app.routes.editor import _read_map
        custom_id = preset_id[len("custom:"):]
        data = _read_map(custom_id)
        custom_layout = data["layout"]
        custom_units = data.get("initial_units", [])
        # Use custom map's biome if game doesn't have one explicitly set
        custom_map_biome = data.get("biome", "grass")
        # Tile grid is sized by the custom map; bypass procedural generator
        from app.config import TERRAIN_PLAIN as _T_PLAIN
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
    else:
        grid = generate_map_preset(
            preset_id=preset_id,
            seed=seed,
            num_castles=max(2, min(CASTLES_PER_GAME, len(players))),
        )

    # If game.map_biome wasn't set but custom map has one, sync it
    if custom_map_biome and not getattr(game, "map_biome", None):
        game.map_biome = custom_map_biome

    tiles: List[Tile] = [t for row in grid for t in row]
    for t in tiles:
        t.game_id = game_id
    session.add_all(tiles)

    castle_xy = castle_positions(len(players))
    default_roster = get_roster_for_composition(
        getattr(game, "unit_composition", None)
    )
    units: List[Unit] = []
    for player in players:
        per_player_roster: Dict[str, int]
        if rosters_by_seat is not None and player.seat in rosters_by_seat:
            per_player_roster = rosters_by_seat[player.seat]
        elif roster is not None:
            per_player_roster = roster
        else:
            per_player_roster = default_roster
        # Compute castle position for this seat
        seat_xy = castle_xy.get(player.seat)
        if seat_xy is None:
            continue
        # Reuse the original helper but per-player; create_initial_units_with_roster
        # applies the SAME roster to every player, so we call it once per
        # player with the right roster by fabricating a tiny single-player
        # pseudo-game (cheaper than duplicating the helper).
        # IMPORTANT: unit_index must be GLOBAL per player, not per-unit-type,
        # otherwise different unit types get the same spawn offset and overlap.
        unit_index = 0
        for unit_type, count in per_player_roster.items():
            from app.game_logic import _spawn_xy_for_castle, _unit_name
            from app.classes.units import get_or_none as _get_unit_or_none

            uc = _get_unit_or_none(unit_type)
            if uc is None:
                continue
            for _ in range(int(count)):
                x, y = _spawn_xy_for_castle(seat_xy, unit_index)
                units.append(Unit(
                    player_id=player.id,
                    unit_type=unit_type,
                    name=_unit_name(unit_type, unit_index),
                    level=1, exp=0,
                    hp=uc.base_hp, max_hp=uc.base_hp,
                    atk=uc.base_atk, def_=uc.base_def,
                    matk=uc.base_matk, mdef=uc.base_mdef,
                    mov=uc.mp_pool, mp=uc.mp_pool,
                    morale=0, x=x, y=y,
                    has_acted=False, has_moved=False,
                    skills=list(uc.default_skills),
                ))
                unit_index += 1
    if units:
        session.add_all(units)
    await session.flush()

    # Spawn units from custom map's initial_units (editor's design-time placement).
    # Each unit is matched to a player by its `color` field.
    if custom_units:
        from app.classes.units import get_or_none as _get_unit_or_none
        color_to_player = {p.color: p for p in players if p.color}
        for cu in custom_units:
            uc = _get_unit_or_none(cu["type"])
            if uc is None:
                continue
            target_player = color_to_player.get(cu["color"])
            if target_player is None:
                continue
            # Per-player unit index for naming
            existing_count = sum(1 for u in units if u.player_id == target_player.id)
            units.append(Unit(
                player_id=target_player.id,
                unit_type=cu["type"],
                name=_unit_name(cu["type"], existing_count),
                level=int(cu.get("level", 1)),
                exp=0,
                hp=uc.base_hp, max_hp=uc.base_hp,
                atk=uc.base_atk, def_=uc.base_def,
                matk=uc.base_matk, mdef=uc.base_mdef,
                mov=uc.mp_pool, mp=uc.mp_pool,
                morale=0, x=int(cu["x"]), y=int(cu["y"]),
                has_acted=False, has_moved=False,
                skills=list(uc.default_skills),
            ))
        if units:
            session.add_all(units)
        await session.flush()

    seat_to_player = {p.seat: p for p in players}
    for seat, (cx, cy) in castle_xy.items():
        for t in tiles:
            if t.x == cx and t.y == cy:
                t.owner_id = seat_to_player[seat].id
                break

    for u in units:
        for t in tiles:
            if t.x == u.x and t.y == u.y:
                t.occupied_unit_id = u.id
                break

    game.status = "playing"
    game.current_player_index = 0
    for p in players:
        p.has_ended_turn = False





@router.post("", response_model=GameSummaryOut, status_code=status.HTTP_201_CREATED)
async def create_game(
    body: CreateGameRequest,
    session: AsyncSession = Depends(get_session),
) -> GameSummaryOut:
    seed = body.map_seed if body.map_seed is not None else random.randint(0, 2**31 - 1)
    game = Game(
        name=body.name,
        status="waiting",
        turn_number=1,
        current_player_index=0,
        map_seed=seed,
        map_preset=body.map_preset,
        map_biome=body.map_biome,
        unit_composition=body.unit_composition,
    )
    session.add(game)
    await session.flush()
    logger.info(
        "Game created: id=%d name=%r seed=%d max_players=%d map_preset=%s biome=%s",
        game.id, game.name, seed, body.max_players, body.map_preset, body.map_biome,
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
    if len(existing) >= MAX_PLAYERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "房间已满")

    if any(p.user_name == body.user_name for p in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "此游戏中用户名已被占用")

    used_colors = [p.color for p in existing]
    color = body.color if body.color and body.color not in used_colors else _next_color(used_colors)
    seat = len(existing)

    player = Player(
        game_id=game_id,
        user_name=body.user_name,
        color=color,
        seat=seat,
    )
    session.add(player)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
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
        units=[],
    )


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
    if len(players) < MIN_PLAYERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"need at least {MIN_PLAYERS} players (currently {len(players)})",
        )

    await _start_battle_internal(session, game, players)

    # Re-query tiles/units via _build_state (avoids lazy loads on
    # detached players after the session commits). Capture the unit
    # count here for the log line.
    roster_total = sum(get_roster_for_composition(
        getattr(game, "unit_composition", None)
    ).values())

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
    from app.classes.units import list_compositions
    from app.game_logic import MAP_PRESETS
    from app.routes.editor import _CUSTOM_DIR, _list_custom_maps
    maps: List[PresetInfo] = [
        PresetInfo(
            id=p["id"], name=p["name"], description=p["description"],
            biome=p.get("biome", "grass"),
            size=int(p.get("size", 15)),
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
        ))
    return PresetsResponse(
        maps=maps,
        unit_compositions=[
            PresetInfo(id=c["id"], name=c["name"], description=c["description"])
            for c in list_compositions()
        ],
    )


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
    if len(players) >= MAX_PLAYERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "房间已满")
    used_colors = [p.color for p in players]
    color = _next_color(used_colors)
    seat = max((p.seat for p in players), default=-1) + 1
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
    # Re-number remaining seats so they're contiguous
    remaining = (
        await session.execute(
            select(Player).where(Player.game_id == game_id).order_by(Player.seat)
        )
    ).scalars().all()
    for new_seat, p in enumerate(remaining):
        if p.seat != new_seat:
            p.seat = new_seat
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
    return {
        **unit.__dict__,
        "attack_range": profile.attack_range,
        "min_attack_range": profile.min_attack_range,
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

    # Current player = first alive player whose seat >= current_player_index, else wrap.
    current_player_id = None
    if players:
        alive_seats = sorted(p.seat for p in players if p.is_alive)
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
    )