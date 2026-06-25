"""
Game-lifecycle routes: create, join, fetch state, start.
"""
from __future__ import annotations

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

router = APIRouter(prefix="/games", tags=["game"])


def _next_color(used_colors: List[str]) -> str:
    for c in DEFAULT_PLAYER_COLORS:
        if c not in used_colors:
            return c
    raise HTTPException(status.HTTP_409_CONFLICT, "no colors available")


async def _ensure_started_or_400(game: Game) -> None:
    if game.status not in ("waiting", "playing"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "game is finished")


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
    return GameSummaryOut.model_validate(game)


@router.post("/{game_id}/join", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join_game(
    game_id: int,
    body: JoinGameRequest,
    session: AsyncSession = Depends(get_session),
) -> PlayerOut:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "game already started")

    existing = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()
    if len(existing) >= MAX_PLAYERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "game is full")

    if any(p.user_name == body.user_name for p in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "user_name already taken in this game")

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
        raise HTTPException(status.HTTP_409_CONFLICT, "could not join (constraint violation)")

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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    player = await session.get(Player, body.player_id)
    if player is None or player.game_id != game_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player not in this game")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    if game.status == "playing":
        # Idempotent: return current state
        return await _build_state(session, game)
    if game.status == "finished":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "game already finished")

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
            description=f"Game started with {len(players)} players",
        )
    )

    return await _build_state(session, game)


@router.get("/{game_id}/state", response_model=GameStateOut)
async def get_game_state(
    game_id: int,
    session: AsyncSession = Depends(get_session),
) -> GameStateOut:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
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
    from app.game_logic import MAP_PRESETS, UNIT_COMPOSITIONS
    return PresetsResponse(
        maps=[
            PresetInfo(id=p["id"], name=p["name"], description=p["description"])
            for p in MAP_PRESETS.values()
        ],
        unit_compositions=[
            PresetInfo(id=p["id"], name=p["name"], description=p["description"])
            for p in UNIT_COMPOSITIONS.values()
        ],
    )


@router.post("/{game_id}/add-ai", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def add_ai_player(
    game_id: int,
    body: AddAIRequest,
    session: AsyncSession = Depends(get_session),
) -> PlayerOut:
    """Add an AI-controlled player to a waiting game."""
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "game already started")
    players = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()
    if len(players) >= MAX_PLAYERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "game is full")
    used_colors = [p.color for p in players]
    color = _next_color(used_colors)
    seat = max((p.seat for p in players), default=-1) + 1
    # Generate a unique AI name
    ai_count = sum(1 for p in players if p.is_ai)
    ai_name = f"电脑-{ai_count + 1}-{body.difficulty}"
    if any(p.user_name == ai_name for p in players):
        ai_name = f"电脑-{ai_count + 1}-{body.difficulty}-{seat}"
    ai = build_ai_player(game, seat=seat, color=color, name=ai_name)
    session.add(ai)
    await session.flush()
    return PlayerOut(
        id=ai.id, user_name=ai.user_name, color=ai.color,
        is_alive=ai.is_alive, has_ended_turn=ai.has_ended_turn,
        seat=ai.seat, is_ai=ai.is_ai, units=[],
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    if game.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "game already started")
    player = await session.get(Player, player_id)
    if player is None or player.game_id != game_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player not in this game")
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