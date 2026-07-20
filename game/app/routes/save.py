"""
Save / Suspend API endpoints.

Endpoints:
  * GET  /saves?user_name=...                — list 3 manual + auto + suspend
  * POST /saves/save                          — manual save to slot 0/1/2
  * POST /saves/load                          — restore from manual or auto
  * POST /saves/erase                         — delete a slot (cascade suspend)
  * POST /games/{id}/suspend                  — capture mid-battle suspend

Auto-save checkpoints (the system writes these, no endpoint):
  * After /advance returns "victory"   → "xx章-结束"
  * After /mainlines/{id}/prepare/complete → "xx章-准备"

The latter is exposed as a public endpoint because the player
explicitly signals "I'm done prepping" by clicking the Ready button.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.progression.models import PlayerProfile
from app.save import SaveService
from app.save.models import GameSaveSlot, SaveSlotKind, SuspendPoint, SuspendState
from app.save.schemas import (
    AutoSaveCheckpointOut,
    GameSaveSlotOut,
    LoadSuspendOut,
    LoadSuspendRequest,
    SaveEraseOut,
    SaveEraseRequest,
    SaveListOut,
    SaveLoadOut,
    SaveLoadRequest,
    SaveManualOut,
    SaveManualRequest,
    SuspendOut,
    SuspendRequest,
    SuspendStateOut,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(tags=["save"])


def _as_utc(value: datetime) -> datetime:
    """Restore SQLite's dropped timezone information for API responses."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ============================================================
# Helpers
# ============================================================


async def _load_profile(session: AsyncSession, user_name: str) -> PlayerProfile:
    """Resolve ``user_name`` to a profile or raise 404.

    Mirrors mainline's strict loader: a typo'd user_name must
    surface as 404, never silently create a wrong profile.
    """
    profile = (await session.execute(
        select(PlayerProfile).where(PlayerProfile.user_name == user_name)
    )).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"profile {user_name!r} not found",
        )
    return profile


def _slot_to_out(slot: Optional[GameSaveSlot]) -> Optional[GameSaveSlotOut]:
    if slot is None:
        return None
    return GameSaveSlotOut(
        id=slot.id,
        kind=slot.kind.value,
        slot_index=slot.slot_index,
        mainline_id=slot.mainline_id,
        chapter_index=slot.chapter_index,
        label=slot.label or "",
        saved_at=_as_utc(slot.saved_at),
        has_snapshot=bool(slot.snapshot),
    )


def _suspend_to_out(sus: Optional[SuspendState]) -> Optional[SuspendStateOut]:
    if sus is None:
        return None
    return SuspendStateOut(
        user_name=sus.user_name,
        game_id=sus.game_id,
        mainline_id=sus.mainline_id,
        battle_id=sus.battle_id,
        suspend_point=sus.suspend_point.value,
        saved_at=_as_utc(sus.saved_at),
    )


# ============================================================
# GET /saves
# ============================================================


@router.get("/saves", response_model=SaveListOut)
async def list_saves(
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> SaveListOut:
    """List the user's save slots: 3 manual + 1 auto + 1 suspend."""
    # Use 404 if profile missing (FE should never call this for a
    # typo'd user — but if it does, we want a clear error).
    await _load_profile(session, user_name)
    svc = SaveService(session)
    manual, auto, suspend = await svc.list_saves(user_name)
    return SaveListOut(
        user_name=user_name,
        manual_slots=[_slot_to_out(s) for s in manual],
        auto_slot=_slot_to_out(auto),
        suspend=_suspend_to_out(suspend),
    )


# ============================================================
# POST /saves/save
# ============================================================


@router.post("/saves/save", response_model=SaveManualOut)
async def save_manual(
    body: SaveManualRequest,
    session: AsyncSession = Depends(get_session),
) -> SaveManualOut:
    """Player-driven save to slot 0/1/2."""
    profile = await _load_profile(session, body.user_name)
    svc = SaveService(session)
    slot = await svc.save_manual(
        profile,
        slot_index=body.slot_index,
        mainline_id=body.mainline_id,
        chapter_index=body.chapter_index,
        label=body.label,
    )
    logger.info(
        "save_manual ok: user=%s slot=%d mainline=%s",
        body.user_name, body.slot_index, body.mainline_id,
    )
    return SaveManualOut(ok=True, slot=_slot_to_out(slot))  # type: ignore[arg-type]


# ============================================================
# POST /saves/load
# ============================================================


@router.post("/saves/load", response_model=SaveLoadOut)
async def load_save(
    body: SaveLoadRequest,
    session: AsyncSession = Depends(get_session),
) -> SaveLoadOut:
    """Restore profile + cursor from a save slot.

    Side effects:
      * profile fields overwritten
      * suspend cascade-cleared (FE8 invariant)
      * if a manual save was loaded, the auto-save slot is wiped
    """
    profile = await _load_profile(session, body.user_name)
    # Snapshot auto-cleared BEFORE load (so we can return the flag)
    svc = SaveService(session)
    auto_before = (await svc.list_saves(body.user_name))[1]
    will_clear_auto = (
        body.kind == "manual" and auto_before is not None
    )
    try:
        slot = await svc.load(
            profile, kind=SaveSlotKind(body.kind), slot_index=body.slot_index,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        )
    logger.info(
        "save_load ok: user=%s kind=%s slot=%d mainline=%s",
        body.user_name, body.kind, body.slot_index, slot.mainline_id,
    )
    return SaveLoadOut(
        ok=True,
        mainline_id=slot.mainline_id,
        chapter_index=slot.chapter_index,
        label=slot.label or "",
        auto_cleared=will_clear_auto,
    )


# ============================================================
# POST /saves/load_suspend — resume from a mid-battle interrupt
# ============================================================


@router.post("/saves/load_suspend", response_model=LoadSuspendOut)
async def load_suspend(
    body: LoadSuspendRequest,
    session: AsyncSession = Depends(get_session),
) -> LoadSuspendOut:
    """Read the user's suspend slot so the FE can resume mid-battle.

    Pairs with:
      * ``POST /games/{id}/suspend``   — manual suspend
      * WS onclose auto-suspend         — disconnect captures

    The endpoint:
      1. Looks up the SuspendState (404 if absent)
      2. Force-aborts any OTHER in-flight games the user has, so
         the suspend's game becomes the player's "current" one
         (matches the FE8 invariant)
      3. Returns the suspend meta (game_id, mainline_id, battle_id)
         so the FE can fetch ``/games/{id}/state`` and render

    Note: the SuspendState row is **NOT** cleared here.  The
    client may want to re-fetch state and bounce without
    committing to the suspend yet.  The row is cleared when the
    player finishes a battle (via the regular advance path) or
    loads a different save.
    """
    await _load_profile(session, body.user_name)
    svc = SaveService(session)
    try:
        sus = await svc.load_suspend(body.user_name)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        )
    # Abort OTHER in-flight games so the suspend's game becomes
    # the player's "current" one.  We do this in two phases so
    # we can count "other" games separately from the suspend's
    # own game (which we may need to restore to "playing" if it
    # was still in-flight when the suspend was captured).
    from app.models import Game as _Game, Player as _Player
    from sqlalchemy import select as _select
    # Phase 1: list the in-flight games for the user.  We need
    # the IDs BEFORE we flip any status, so we can subtract the
    # suspend's own game from the count.
    in_flight = (await session.execute(
        _select(_Game.id).join(_Player, _Player.game_id == _Game.id).where(
            _Game.status == "playing",
            _Player.user_name == body.user_name,
            _Player.is_ai == False,  # noqa: E712
            _Player.is_spectator == False,  # noqa: E712
        )
    )).scalars().all()
    in_flight_set = set(in_flight)
    suspend_in_in_flight = sus.game_id in in_flight_set
    # Phase 2: abort them all.
    aborted_total = await svc._abort_in_flight_games(  # noqa: SLF001
        body.user_name
    )
    # Phase 3: if the suspend's own game was in the original
    # in-flight set, restore it to "playing" so the resume can
    # proceed.  This makes load_suspend idempotent: even if the
    # player calls it twice in a row, the suspend's game ends
    # up in "playing" state.
    if suspend_in_in_flight:
        sus_game_row = (await session.execute(
            _select(_Game).where(_Game.id == sus.game_id)
        )).scalar_one()
        sus_game_row.status = "playing"
        aborted_other = max(aborted_total - 1, 0)
    else:
        aborted_other = aborted_total
    logger.info(
        "save_load_suspend: user=%s game_id=%s mainline=%s "
        "aborted_total=%d aborted_other=%d suspend_in_flight=%s",
        body.user_name, sus.game_id, sus.mainline_id,
        aborted_total, aborted_other, suspend_in_in_flight,
    )
    return LoadSuspendOut(
        ok=True,
        user_name=body.user_name,
        game_id=sus.game_id,
        mainline_id=sus.mainline_id,
        battle_id=sus.battle_id,
        suspend_point=sus.suspend_point.value,
        saved_at=_as_utc(sus.saved_at),
        aborted_game_count=aborted_other,
    )


# ============================================================
# POST /saves/erase
# ============================================================


@router.post("/saves/erase", response_model=SaveEraseOut)
async def erase_save(
    body: SaveEraseRequest,
    session: AsyncSession = Depends(get_session),
) -> SaveEraseOut:
    """Delete a save slot.  Cascades to suspend if a Game save was removed."""
    await _load_profile(session, body.user_name)
    svc = SaveService(session)
    suspend_before = (await svc.list_saves(body.user_name))[2]
    erased = await svc.erase(
        body.user_name,
        kind=SaveSlotKind(body.kind),
        slot_index=body.slot_index,
    )
    if not erased:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no {body.kind} save slot {body.slot_index} for "
                f"user {body.user_name!r}"
            ),
        )
    suspend_after = (await svc.list_saves(body.user_name))[2]
    return SaveEraseOut(
        ok=True,
        erased=True,
        suspend_cleared=(suspend_before is not None and suspend_after is None),
    )


# ============================================================
# POST /games/{game_id}/suspend
# ============================================================


@router.post("/games/{game_id}/suspend", response_model=SuspendOut)
async def capture_suspend(
    game_id: int,
    body: SuspendRequest,
    session: AsyncSession = Depends(get_session),
) -> SuspendOut:
    """Capture the live Game state into the user's suspend slot.

    The caller passes the current GameStateOut in the snapshot —
    this endpoint is the write half of the "I closed my browser
    and want to come back" flow.  Pair with /saves/load for the
    manual-load half.
    """
    # Game must exist and be live
    from app.models import Game
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"game {game_id} not found",
        )
    if game.status != "playing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"game {game_id} status is {game.status!r}, not 'playing'",
        )
    # Snapshot is provided by the caller (typically the front-end's
    # last /games/{id}/state response).  Body field kept implicit
    # because we don't have it in the schema — if absent, store an
    # empty placeholder and rely on resume to refetch state.
    # (Most callers will hit the WS-close path which calls a
    # dedicated function that captures the actual state.)
    svc = SaveService(session)
    from app.models import Player
    human = (await session.execute(
        select(Player).where(
            Player.game_id == game_id, Player.is_ai == False,  # noqa: E712
            Player.is_spectator == False,  # noqa: E712
            Player.user_name == body.user_name,
        )
    )).scalars().first()
    if human is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no human player {body.user_name!r} in game {game_id}",
        )
    await svc.capture_suspend(
        user_name=body.user_name,
        game_id=game_id,
        mainline_id=(game.name or "").split(":")[1]
        if (game.name or "").startswith("mainline:")
        else "",
        battle_id=(game.name or "").split(":")[-1]
        if (game.name or "").startswith("mainline:")
        else "",
        suspend_point=SuspendPoint.MANUAL,
        game_state={},  # populated on resume from /games/{id}/state
    )
    return SuspendOut(ok=True, saved_at=datetime.now(timezone.utc))


# ============================================================
# Public helper: auto-save from mainline flow
# ============================================================


async def auto_save_checkpoint(
    session: AsyncSession,
    profile: PlayerProfile,
    mainline_id: str,
    chapter_index: int,
    label: str,
) -> AutoSaveCheckpointOut:
    """Public entry point used by /advance and /prepare/complete.

    Called by:
      * routes/mainline.py::MainlineEngine.advance()   — when state
        transitions to "victory" or "next-battle" — label
        ``f"{mainline_id}-结束"``.
      * routes/mainline.py::prepare_complete()          — when the
        player signals "I'm ready" — label
        ``f"{mainline_id}-准备"``.

    Returns the AutoSaveCheckpointOut so callers can surface the
    "自动存档中…… 自动存档完毕" toast.
    """
    svc = SaveService(session)
    slot = await svc.save_auto(
        profile=profile,
        mainline_id=mainline_id,
        chapter_index=chapter_index,
        label=label,
    )
    auto_kind = (
        "chapter_end" if label.endswith("-结束") else
        "prep_complete" if label.endswith("-准备") else
        "unknown"
    )
    logger.info(
        "auto_save ok: user=%s label=%r mainline=%s chapter_index=%d",
        profile.user_name, label, mainline_id, chapter_index,
    )
    return AutoSaveCheckpointOut(
        ok=True,
        label=label,
        auto_kind=auto_kind,
        saved_at=slot.saved_at,
    )


__all__ = [
    "router",
    "auto_save_checkpoint",
]
