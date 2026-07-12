"""Commander selection, listing, and CO Power endpoints.

The application currently has no login/session middleware.  Consistent with
the existing APIs, callers therefore provide ``user_name`` or ``player_id``.
These identifiers are authorization handles, not strong authentication.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.classes.heroes import get as get_hero
from app.commanders.actions import can_player_fire_now
from app.commanders.effects import can_fire_co_power, fire_co_power
from app.commanders.registry import get_power_threshold
from app.database import get_session
from app.game_locks import game_write_guard
from app.mainline.loader import MainlineNotFound, load_mainline
from app.models import Game, Player
from app.progression.models import PlayerProfile

router = APIRouter(tags=["commanders"])


class _StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectMainlineCommanderIn(_StrictBody):
    user_name: Optional[str] = None
    commander_id: Optional[str] = None


class SelectBattleCommanderIn(_StrictBody):
    player_id: int
    commander_id: Optional[str] = None


class FireCOPowerIn(_StrictBody):
    player_id: int


def _commander(hero_id: str):
    try:
        hero = get_hero(hero_id)
    except KeyError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown hero: {hero_id}")
    if not getattr(hero, "is_commander", False):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{hero_id} is not a commander")
    return hero


@router.get("/players/me/commanders")
async def get_unlocked_commanders(
    user_name: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if not user_name:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_name required; authentication is not configured")
    profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == user_name))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return {
        "user_name": user_name,
        "unlocked_commanders": list(profile.unlocked_commanders or []),
        "mainline_commanders": dict(profile.mainline_commanders or {}),
    }


@router.post("/mainlines/{mainline_id}/select-commander")
async def select_mainline_commander(
    mainline_id: str,
    body: SelectMainlineCommanderIn,
    session: AsyncSession = Depends(get_session),
):
    if not body.user_name:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_name required; authentication is not configured")
    if body.commander_id is not None:
        _commander(body.commander_id)
    try:
        mainline = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == body.user_name))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    spawned_game_id = await session.scalar(
        select(Game.id).join(Player).where(
            Player.user_name == body.user_name,
            Player.is_ai.is_(False),
            Game.name.startswith(f"mainline:{mainline_id}:"),
            Game.status.in_(("waiting", "playing")),
        ).limit(1)
    )
    if profile.active_mainline is not None or spawned_game_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "commander selection is closed after mainline start")
    eligible = set(profile.unlocked_commanders or []) & {
        unit.hero_id for unit in mainline.starting_units if unit.hero_id
    }
    if body.commander_id is not None and body.commander_id not in eligible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "commander is not in unlocked starting-unit pool")

    choices = dict(profile.mainline_commanders or {})
    choices[mainline_id] = body.commander_id
    profile.mainline_commanders = choices
    await session.commit()
    return {"mainline_id": mainline_id, "commander_id": body.commander_id}


@router.post("/games/{game_id}/select-commander")
async def select_battle_commander(game_id: int, body: SelectBattleCommanderIn):
    raise HTTPException(status.HTTP_409_CONFLICT, "commander locked during battle")


@router.post("/games/{game_id}/co-power")
async def fire_co_power_endpoint(
    game_id: int,
    body: FireCOPowerIn,
    _write_guard: None = Depends(game_write_guard),
    session: AsyncSession = Depends(get_session),
):
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    players = (await session.scalars(
        select(Player).options(selectinload(Player.units)).where(Player.game_id == game_id)
    )).all()
    alive_seats = sorted(p.seat for p in players if p.is_alive or p.is_spectator)
    expected_seat = next(
        (seat for seat in alive_seats if seat >= game.current_player_index),
        alive_seats[0] if alive_seats else None,
    )
    player = next((p for p in players if p.seat == expected_seat), None)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "current player not found")
    if body.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "player_id is not the current player")
    if not can_player_fire_now(player, game, players):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not this player's active turn")
    if not can_fire_co_power(player):
        if player.commander_id is None:
            detail = "no commander selected"
        elif (player.co_state or {}).get("is_power_active"):
            detail = "power already active"
        else:
            detail = "meter not full or commander has no power"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)
    fire_co_power(player)
    await session.commit()
    return {"game_id": game_id, "player_id": player.id, "commander_id": player.commander_id, "meter": 0}
