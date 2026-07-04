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
from typing import Dict, List, Optional

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
    LobbyInfoOut,
    PlayerOut,
    PresetInfo,
    PresetsResponse,
    RejoinGameRequest,
    RejoinGameResponse,
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
            num_castles=max(2, min(MAX_CASTLES, len(players))),
        )

    # If game.map_biome wasn't set but custom map has one, sync it
    if custom_map_biome and not getattr(game, "map_biome", None):
        game.map_biome = custom_map_biome

    tiles: List[Tile] = [t for row in grid for t in row]
    for t in tiles:
        t.game_id = game_id
    session.add_all(tiles)

    # P2.4 — spectators don't occupy a castle and don't get units.
    # Their seats are above MAX_PLAYERS so castle_positions(seat) is
    # never even asked for them; skip the loop entirely so the
    # spectator's `seat` doesn't accidentally fall into castle_xy.
    real_players = [p for p in players if not p.is_spectator]
    map_size = len(grid)
    castle_xy = castle_positions(len(real_players), map_size)
    default_roster = get_roster_for_composition(
        getattr(game, "unit_composition", None)
    )
    units: List[Unit] = []
    for player in real_players:
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
                x, y = _spawn_xy_for_castle(seat_xy, unit_index, map_size)
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
        unit_composition=body.unit_composition,
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
        color = _next_color(used_colors) if not body.color or body.color in used_colors \
                else body.color

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
        seat = len([p for p in existing if not p.is_spectator])

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
    host = next((p for p in all_players if p.seat == 0), None)

    # The caller identifies themselves in the request body.
    # (In a LAN game without real auth, the frontend gates the UI;
    #  this check is a safety net, not a fortress.)
    caller = next((p for p in all_players if p.id == body.caller_player_id), None)
    if caller is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法识别请求者")

    # Permission check
    is_host = caller.seat == 0
    is_self = caller.id == target.id
    if not (is_host or is_self):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有房主可以修改其他玩家的队伍")

    target.team_id = body.team if body.team else None
    await session.flush()

    return {"ok": True, "player_id": player_id, "team": target.team_id}


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

    await _start_battle_internal(session, game, players)

    # P0.4 — collect income for the first player at game start so turn 1
    # income is granted based on initial building ownership.
    from app.routes.turns import _collect_income_for_player
    first_player = next(p for p in players if p.seat == 0)
    await _collect_income_for_player(session, game, first_player)

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
    from app.classes.units import list_compositions
    from app.game_logic import MAP_PRESETS
    from app.routes.editor import _CUSTOM_DIR, _list_custom_maps
    maps: List[PresetInfo] = [
        PresetInfo(
            id=p["id"], name=p["name"], description=p["description"],
            biome=p.get("biome", "grass"),
            size=int(p.get("size", 15)),
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
        alive_seats = sorted(p.seat for p in players if p.is_alive or p.is_spectator)
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
    )