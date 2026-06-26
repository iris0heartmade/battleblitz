"""
Game-lifecycle routes: create, join, fetch state, start.
"""
from __future__ import annotations

import logging
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    CASTLES_PER_GAME,
    DEFAULT_PLAYER_COLORS,
    MAX_PLAYERS,
    MIN_PLAYERS,
)
from app.database import get_session
from app.game_logic import (
    castle_positions,
    create_initial_units_with_roster,
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
        unit_composition=body.unit_composition,
    )
    session.add(game)
    await session.flush()
    logger.info(
        "Game created: id=%d name=%r seed=%d max_players=%d map_preset=%s",
        game.id, game.name, seed, body.max_players, body.map_preset,
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

    # Generate map and persist tiles
    grid = generate_map_preset(
        preset_id=getattr(game, "map_preset", None) or "classic",
        seed=game.map_seed,
        num_castles=max(2, min(CASTLES_PER_GAME, len(players))),
    )
    tiles: List[Tile] = [t for row in grid for t in row]
    for t in tiles:
        t.game_id = game_id
    session.add_all(tiles)

    # Create units
    castle_xy = castle_positions(len(players))
    roster = get_roster_for_composition(getattr(game, "unit_composition", None))
    units = create_initial_units_with_roster(game, players, castle_xy, roster)
    for u in units:
        u.player_id = u.player_id  # already set
    session.add_all(units)
    await session.flush()

    # Mark the castle tiles with their owner (seat index -> player id)
    seat_to_player = {p.seat: p for p in players}
    for seat, (cx, cy) in castle_xy.items():
        for t in tiles:
            if t.x == cx and t.y == cy:
                t.owner_id = seat_to_player[seat].id
                break

    # Mark tiles occupied by units
    for u in units:
        for t in tiles:
            if t.x == u.x and t.y == u.y:
                t.occupied_unit_id = u.id
                break

    game.status = "playing"
    game.current_player_index = 0
    # Reset end-turn flags
    for p in players:
        p.has_ended_turn = False

    session.add(
        ActionLog(
            game_id=game_id,
            turn_number=game.turn_number,
            player_id=None,
            action_type="system",
            description=f"游戏开始，玩家： {len(players)} players",
        )
    )

    logger.info(
        "Game started: id=%d players=%d units=%d map_preset=%s seed=%d",
        game_id, len(players), len(units),
        getattr(game, "map_preset", None) or "classic", game.map_seed,
    )
    audit.info(
        "USER_ACTION | user=system | game=%d | action=GAME_START | result=SUCCESS | "
        "players=%d units=%d",
        game_id, len(players), len(units),
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
    session: AsyncSession = Depends(get_session),
) -> List[GameSummaryOut]:
    rows = (await session.execute(select(Game).order_by(Game.id.desc()))).scalars().all()
    return [GameSummaryOut.model_validate(g) for g in rows]


@router.get("/presets", response_model=PresetsResponse)
async def list_presets() -> PresetsResponse:
    """Return available map and unit-composition presets for the create-game form."""
    from app.classes.units import list_compositions
    from app.game_logic import MAP_PRESETS
    return PresetsResponse(
        maps=[
            PresetInfo(id=p["id"], name=p["name"], description=p["description"])
            for p in MAP_PRESETS.values()
        ],
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


# ============================================================
# Helpers
# ============================================================

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
                    UnitOut.model_validate(u)
                    for u in sorted(units_by_player.get(p.id, []), key=lambda x: (x.unit_type, x.id))
                ],
            )
            for p in players
        ],
        current_player_id=current_player_id,
        logs=[ActionLogOut.model_validate(l) for l in logs],
    )