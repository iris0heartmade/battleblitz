"""
FastAPI routes for the progression system.

Endpoints:
  POST   /profiles                        Create a player profile
  GET    /profiles                        List profiles
  GET    /profiles/{id}                   Get one profile
  POST   /profiles/{id}/units             Create a unit (hero)
  GET    /profiles/{id}/units             List a profile's units
  GET    /units/{id}                      Get one unit
  POST   /units/{id}/xp                   Award EXP (testing/admin)
  POST   /units/{id}/promote              Promote to next tier
  DELETE /units/{id}                      Delete a unit (admin/debug)

These are mounted under the same prefix as other game routes:
    app.include_router(progression_api.router, prefix="/progression")
so the final URLs are /progression/profiles, etc.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.progression.exceptions import (
    InvalidNickname,
    LevelCapReached,
    ProfileAlreadyExists,
    ProfileNotFound,
    PromoteRequirementNotMet,
    TierCapReached,
    UnitAlreadyExists,
    UnitNotFound,
)
from app.progression.schemas import (
    AwardXpRequest,
    AwardXpResult,
    CreateProfileRequest,
    CreateUnitRequest,
    PlayerProfileOut,
    PromoteRequest,
    PromoteResult,
    UnitInstanceOut,
)
from app.progression.service import ProgressionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["progression"])


# ============================================================
# Dependency: build a ProgressionService per request
# ============================================================

async def _service(session: AsyncSession = Depends(get_session)) -> ProgressionService:
    return ProgressionService(session)


# ============================================================
# PlayerProfile
# ============================================================

@router.post(
    "/profiles",
    response_model=PlayerProfileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    body: CreateProfileRequest,
    svc: ProgressionService = Depends(_service),
) -> PlayerProfileOut:
    try:
        profile = await svc.create_profile(body.user_name, initial_rating=body.initial_rating)
    except ProfileAlreadyExists as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return PlayerProfileOut.model_validate(profile)


@router.get("/profiles", response_model=list[PlayerProfileOut])
async def list_profiles(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc: ProgressionService = Depends(_service),
) -> list[PlayerProfileOut]:
    profiles = await svc.list_profiles(limit=limit, offset=offset)
    return [PlayerProfileOut.model_validate(p) for p in profiles]


@router.get("/profiles/{profile_id}", response_model=PlayerProfileOut)
async def get_profile(
    profile_id: int,
    svc: ProgressionService = Depends(_service),
) -> PlayerProfileOut:
    try:
        profile = await svc.get_profile(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return PlayerProfileOut.model_validate(profile)


# ============================================================
# UnitInstance
# ============================================================

@router.post(
    "/profiles/{profile_id}/units",
    response_model=UnitInstanceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_unit(
    profile_id: int,
    body: CreateUnitRequest,
    svc: ProgressionService = Depends(_service),
) -> UnitInstanceOut:
    try:
        unit = await svc.create_unit(
            profile_id=profile_id,
            base_type=body.base_type,
            nickname=body.nickname,
            personality=body.personality,
        )
    except ProfileNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except UnitAlreadyExists as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except InvalidNickname as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return UnitInstanceOut.model_validate(unit)


@router.get("/profiles/{profile_id}/units", response_model=list[UnitInstanceOut])
async def list_units(
    profile_id: int,
    svc: ProgressionService = Depends(_service),
) -> list[UnitInstanceOut]:
    # Confirm profile exists (so we 404 instead of returning [])
    await svc.get_profile(profile_id)
    units = await svc.list_units(profile_id)
    return [UnitInstanceOut.model_validate(u) for u in units]


@router.get("/units/{unit_id}", response_model=UnitInstanceOut)
async def get_unit(
    unit_id: int,
    svc: ProgressionService = Depends(_service),
) -> UnitInstanceOut:
    try:
        unit = await svc.get_unit(unit_id)
    except UnitNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return UnitInstanceOut.model_validate(unit)


# ============================================================
# Leveling operations
# ============================================================

@router.post("/units/{unit_id}/xp", response_model=AwardXpResult)
async def award_xp(
    unit_id: int,
    body: AwardXpRequest,
    svc: ProgressionService = Depends(_service),
) -> AwardXpResult:
    try:
        summary = await svc.award_xp(unit_id, body.amount, reason=body.reason)
    except UnitNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return AwardXpResult(
        unit_id=summary.unit_id,
        levels_gained=summary.levels_gained,
        new_level=summary.new_level,
        new_exp=summary.new_exp,
        talent_points_awarded=summary.talent_points_awarded,
        capped=summary.capped,
        reason=body.reason,
    )


@router.post("/units/{unit_id}/promote", response_model=PromoteResult)
async def promote_unit(
    unit_id: int,
    body: PromoteRequest,
    svc: ProgressionService = Depends(_service),
) -> PromoteResult:
    try:
        summary = await svc.promote(unit_id, force=body.force)
    except UnitNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except TierCapReached as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except PromoteRequirementNotMet as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return PromoteResult(
        unit_id=summary.unit_id,
        old_tier=summary.old_tier,
        new_tier=summary.new_tier,
        new_level_cap=summary.new_level_cap,
    )


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: int,
    svc: ProgressionService = Depends(_service),
) -> None:
    try:
        unit = await svc.get_unit(unit_id)
        await svc.units.delete(unit_id)
    except UnitNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    logger.info("Unit deleted: id=%d", unit_id)
