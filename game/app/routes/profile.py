"""
Profile-centric routes — keyed by `user_name` rather than numeric id.

This is the public-facing API used by the game client (and Step 3's
mainline engine). The existing `app.progression.api` is keyed by the
internal `profile_id` and is mostly used by tests + admin tooling;
the new routes here are the ones the front-end calls.

Endpoints
---------
  GET  /profile/{user_name}                       Fetch a profile
  POST /profile/{user_name}/mainline/start        Begin a campaign
  POST /profile/{user_name}/mainline/advance      Move the campaign cursor
  POST /profile/{user_name}/mainline/abandon      Drop the active campaign

Mounted under no extra prefix in `app/main.py` (so the final URLs are
`/profile/...`, not `/progression/profile/...`).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.progression.exceptions import (
    InvalidMainlineProgress,
    MainlineAlreadyActive,
    MainlineIdNotFound,
    NoActiveMainline,
    ProfileNotFound,
)
from app.progression.schemas import (
    AbandonMainlineRequest,
    AdvanceMainlineRequest,
    MainlineProgress,
    PlayerProfileOut,
    StartMainlineRequest,
)
from app.progression.service import ProgressionService

logger = logging.getLogger(__name__)
# USER_ACTION audit lines per §15 of the logging standard
audit = logging.getLogger("audit.user")

router = APIRouter(tags=["profile"])


# ============================================================
# Dependency
# ============================================================

async def _service(session: AsyncSession = Depends(get_session)) -> ProgressionService:
    return ProgressionService(session)


# ============================================================
# Response envelope (shared shape for all mainline endpoints)
# ============================================================
#
# Keeping a uniform shape across start/advance/abandon means the
# front-end can reuse one renderer. `cleared` is True only after the
# player finishes the last battle or after an explicit abandon.

class MainlineStatusOut(BaseModel):
    user_name: str
    active_mainline: Optional[str] = None
    mainline_progress: MainlineProgress
    cleared: bool = False

    class Config:
        from_attributes = True


# ============================================================
# GET /profile/{user_name}
# ============================================================

@router.get(
    "/profile/{user_name}",
    response_model=PlayerProfileOut,
    responses={404: {"description": "Profile not found"}},
)
async def get_profile_by_name(
    user_name: str,
    svc: ProgressionService = Depends(_service),
) -> PlayerProfileOut:
    """Fetch a profile by its `user_name`.

    Returns 404 with the existing `ProfileNotFound` message if no row
    matches. The response includes the mainline fields
    (`active_mainline`, `mainline_progress`) so the client can resume
    an in-progress campaign on page load.
    """
    logger.debug("get_profile entry: user_name=%s", user_name)
    profile = await svc.profiles.get_by_name(user_name)
    if profile is None:
        logger.warning("get_profile not found: user_name=%s", user_name)
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"profile {user_name!r} not found")
    logger.info(
        "get_profile ok: user=%s active_mainline=%s battle_index=%d",
        user_name, profile.active_mainline,
        (profile.mainline_progress or {}).get("battle_index", 0),
    )
    return PlayerProfileOut.model_validate(profile)


# ============================================================
# POST /profile/{user_name}/mainline/start
# ============================================================

@router.post(
    "/profile/{user_name}/mainline/start",
    response_model=MainlineStatusOut,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Profile or mainline not found"},
        409: {"description": "A mainline is already active"},
    },
)
async def start_mainline(
    user_name: str,
    body: StartMainlineRequest,
    svc: ProgressionService = Depends(_service),
) -> MainlineStatusOut:
    """Begin a new campaign.

    Returns the freshly-initialised cursor (battle_index=0, the mainline's
    "intro" scene). If the profile already has an active mainline the
    caller can pass `force=true` to abandon the current one and start
    the new campaign in a single call.
    """
    logger.debug(
        "profile.mainline_start entry: user_name=%s mainline_id=%s force=%s",
        user_name, body.mainline_id, body.force,
    )
    try:
        summary = await svc.set_active_mainline(
            user_name,
            body.mainline_id,
            force=body.force,
        )
    except ProfileNotFound as exc:
        logger.warning("profile.mainline_start profile missing: user=%s", user_name)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineIdNotFound as exc:
        logger.warning("profile.mainline_start mainline missing: user=%s mainline=%s",
                       user_name, body.mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineAlreadyActive as exc:
        logger.warning("profile.mainline_start already active: user=%s mainline=%s",
                       user_name, body.mainline_id)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    logger.info(
        "profile.mainline_start ok: user=%s mainline=%s battle_index=%d scene=%s",
        user_name, summary.active_mainline,
        (summary.mainline_progress or {}).get("battle_index", 0),
        (summary.mainline_progress or {}).get("scene_id", "intro"),
    )
    audit.info(
        "USER_ACTION | user=%s | action=PROFILE_MAINLINE_START | mainline=%s | "
        "result=SUCCESS",
        user_name, body.mainline_id,
    )
    return MainlineStatusOut(
        user_name=summary.user_name,
        active_mainline=summary.active_mainline,
        mainline_progress=MainlineProgress.model_validate(summary.mainline_progress),
        cleared=summary.cleared,
    )


# ============================================================
# POST /profile/{user_name}/mainline/advance
# ============================================================

@router.post(
    "/profile/{user_name}/mainline/advance",
    response_model=MainlineStatusOut,
    responses={
        404: {"description": "Profile not found"},
        409: {"description": "No active mainline"},
        422: {"description": "Invalid scene_id (not in mainline.dialogues)"},
    },
)
async def advance_mainline(
    user_name: str,
    body: AdvanceMainlineRequest,
    svc: ProgressionService = Depends(_service),
) -> MainlineStatusOut:
    """Move the campaign cursor forward.

    The request can set a new `scene_id` (validated against the
    mainline's dialogue keys) and/or increment `battle_index`. When
    the cursor walks past the last battle the mainline is auto-cleared
    and `cleared=true` in the response.
    """
    logger.debug(
        "profile.mainline_advance entry: user_name=%s scene_id=%s next_battle=%s",
        user_name, body.scene_id, body.next_battle,
    )
    try:
        summary = await svc.advance_mainline_progress(
            user_name,
            scene_id=body.scene_id,
            next_battle=body.next_battle,
        )
    except ProfileNotFound as exc:
        logger.warning("profile.mainline_advance profile missing: user=%s", user_name)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except NoActiveMainline as exc:
        logger.warning("profile.mainline_advance no active: user=%s", user_name)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except InvalidMainlineProgress as exc:
        logger.exception("profile.mainline_advance invalid: user=%s", user_name)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    logger.info(
        "profile.mainline_advance ok: user=%s active=%s battle_index=%d cleared=%s",
        user_name, summary.active_mainline,
        (summary.mainline_progress or {}).get("battle_index", 0),
        summary.cleared,
    )
    audit.info(
        "USER_ACTION | user=%s | action=PROFILE_MAINLINE_ADVANCE | active=%s | "
        "cleared=%s | result=SUCCESS",
        user_name, summary.active_mainline, summary.cleared,
    )
    return MainlineStatusOut(
        user_name=summary.user_name,
        active_mainline=summary.active_mainline,
        mainline_progress=MainlineProgress.model_validate(summary.mainline_progress),
        cleared=summary.cleared,
    )


# ============================================================
# POST /profile/{user_name}/mainline/abandon
# ============================================================

@router.post(
    "/profile/{user_name}/mainline/abandon",
    response_model=MainlineStatusOut,
    responses={404: {"description": "Profile not found"}},
)
async def abandon_mainline(
    user_name: str,
    _body: Optional[AbandonMainlineRequest] = None,
    svc: ProgressionService = Depends(_service),
) -> MainlineStatusOut:
    """Drop the active campaign without completing it.

    Idempotent: returns 200 with the cleared payload even if there was
    no active mainline. Only 404s when the profile itself is unknown.
    """
    logger.debug("profile.mainline_abandon entry: user_name=%s", user_name)
    try:
        summary = await svc.abandon_mainline(user_name)
    except ProfileNotFound as exc:
        logger.warning("profile.mainline_abandon profile missing: user=%s", user_name)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    logger.info(
        "profile.mainline_abandon ok: user=%s cleared=%s",
        user_name, summary.cleared,
    )
    audit.info(
        "USER_ACTION | user=%s | action=PROFILE_MAINLINE_ABANDON | cleared=%s | "
        "result=SUCCESS",
        user_name, summary.cleared,
    )
    return MainlineStatusOut(
        user_name=summary.user_name,
        active_mainline=summary.active_mainline,
        mainline_progress=MainlineProgress.model_validate(
            summary.mainline_progress or {
                "battle_index": 0,
                "scene_id": "intro",
                "started_at": None,
            }
        ),
        cleared=summary.cleared,
    )


__all__ = ["router"]
