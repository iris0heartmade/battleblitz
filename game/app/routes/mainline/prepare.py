"""Pre-battle preparation endpoints (read + 3 mutations).

Endpoints owned here:
  * GET  /mainlines/{mainline_id}/prepare              — :func:`get_mainline_prepare`
  * POST /mainlines/{mainline_id}/prepare/promote      — :func:`promote_mainline_hero`
  * POST /mainlines/{mainline_id}/prepare/equipment    — :func:`equip_mainline_hero`
  * POST /mainlines/{mainline_id}/prepare/complete     — :func:`complete_prepare`

Heavy lifting is delegated to:
  * :func:`_build_prepare_payload` from ``_common``
  * :func:`_ensure_test_mainline_unlocked` from ``_common``
  * :func:`_load_profile` / :func:`_ensure_profile_or_create` from ``_common``
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.hero_domain import (
    EQUIPMENT_SLOTS,
    build_hero_class_template,
    build_initial_campaign_state,
    can_promote_hero,
    equipped_stat_bonuses,
    get_equipment,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)
from app.hero_domain.promotion import HeroPromotionError, promote_hero
from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
)
from app.mainline.schemas import (
    MainlinePrepareEquipmentOut,
    MainlinePrepareEquipmentRequest,
    MainlinePrepareOut,
    MainlinePreparePromoteOut,
    MainlinePreparePromoteRequest,
)
from app.progression import ProgressionService
from app.routes.save import auto_save_checkpoint
from app.save import AutoSaveCheckpointOut, PrepCompleteRequest

from ._common import (
    _build_prepare_payload,
    _ensure_profile_or_create,
    _ensure_test_mainline_unlocked,
    _load_profile,
)

logger = logging.getLogger(__name__)

# Each submodule carries the full ``/mainlines`` prefix so that
# ``router.include_router(...)`` in ``__init__.py`` does not stack
# another prefix on top.
router = APIRouter(prefix="/mainlines", tags=["mainline"])


# ============================================================
# GET /mainlines/{mainline_id}/prepare
# ============================================================


@router.get("/{mainline_id}/prepare", response_model=MainlinePrepareOut)
async def get_mainline_prepare(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlinePrepareOut:
    """Build a read-only pre-battle payload without spawning a Game row."""
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "get_mainline_prepare entry: mainline=%s user=%s",
        mainline_id,
        user_name,
    )
    try:
        mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mainline_prepare not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mainline_prepare invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _ensure_profile_or_create(session, user_name)
    await _ensure_test_mainline_unlocked(session, user_name, mainline_id)
    payload = await _build_prepare_payload(session, profile, mainline_id)
    logger.info(
        "get_mainline_prepare ok: mainline=%s user=%s battle=%s heroes=%d",
        mainline_id,
        user_name,
        payload.battle_id,
        len(payload.heroes),
    )
    return payload


# ============================================================
# POST /mainlines/{mainline_id}/prepare/promote
# ============================================================


@router.post(
    "/{mainline_id}/prepare/promote",
    response_model=MainlinePreparePromoteOut,
)
async def promote_mainline_hero(
    mainline_id: str,
    body: MainlinePreparePromoteRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlinePreparePromoteOut:
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _load_profile(session, body.user_name)
    if getattr(profile, "active_mainline", None) not in (None, mainline_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"profile {body.user_name!r} is active in another mainline",
        )

    hero_ids = {spec.hero_id for spec in ml.starting_units if spec.hero_id}
    if body.hero_id not in hero_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"hero {body.hero_id!r} not found in mainline roster")

    svc = ProgressionService(session)
    stored_state = await svc.get_hero_campaign_state(body.user_name, body.hero_id)
    if stored_state is None:
        stored_state = hero_campaign_state_to_dict(build_initial_campaign_state(body.hero_id))
        await svc.set_hero_campaign_state(body.user_name, body.hero_id, stored_state)
    state = hero_campaign_state_from_dict(stored_state)
    current_class = build_hero_class_template(state.class_id)
    target_class = build_hero_class_template(body.target_class_id)
    inventory = await svc.get_hero_inventory(body.user_name)
    crest_count = int(inventory.get("hero_crest", 0))
    if crest_count <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "hero_crest is required for promotion")
    try:
        promoted_state = promote_hero(state, current_class, target_class)
    except HeroPromotionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    await svc.set_hero_campaign_state(
        body.user_name,
        body.hero_id,
        hero_campaign_state_to_dict(promoted_state),
    )
    updated_inventory = await svc.set_hero_inventory_item(
        body.user_name,
        "hero_crest",
        crest_count - 1,
    )

    return MainlinePreparePromoteOut(
        hero_id=promoted_state.hero_id,
        class_id=promoted_state.class_id,
        level=promoted_state.level,
        promoted=promoted_state.promoted,
        hero_crest_left=int((updated_inventory or {}).get("hero_crest", 0)),
    )


# ============================================================
# POST /mainlines/{mainline_id}/prepare/equipment
# ============================================================


@router.post(
    "/{mainline_id}/prepare/equipment",
    response_model=MainlinePrepareEquipmentOut,
)
async def equip_mainline_hero(
    mainline_id: str,
    body: MainlinePrepareEquipmentRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlinePrepareEquipmentOut:
    """Persist one equipment choice made in the pre-battle preparation view."""
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if body.slot not in EQUIPMENT_SLOTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown equipment slot")
    hero_ids = {spec.hero_id for spec in ml.starting_units if spec.hero_id}
    if body.hero_id not in hero_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"hero {body.hero_id!r} not found in mainline roster")
    profile = await _load_profile(session, body.user_name)
    definition = get_equipment(body.equipment_id)
    if body.equipment_id is not None and (definition is None or definition.slot != body.slot):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "equipment does not match this slot")

    svc = ProgressionService(session)
    inventory = await svc.ensure_hero_equipment_starters(body.user_name)
    if definition is not None and int(inventory.get(definition.item_id, 0)) <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "equipment is not in inventory")
    stored_state = await svc.get_hero_campaign_state(body.user_name, body.hero_id)
    if stored_state is None:
        stored_state = hero_campaign_state_to_dict(build_initial_campaign_state(body.hero_id))
    state = hero_campaign_state_from_dict(stored_state)

    # An inventory item can be equipped by only one hero at a time.
    if definition is not None:
        equipped_elsewhere = 0
        all_states = dict(getattr(profile, "hero_campaign_states", {}) or {})
        for hero_id, raw_state in all_states.items():
            if hero_id != body.hero_id and definition.item_id in (raw_state.get("equipment") or {}).values():
                equipped_elsewhere += 1
        if equipped_elsewhere >= int(inventory.get(definition.item_id, 0)):
            raise HTTPException(status.HTTP_409_CONFLICT, "equipment is already equipped by another hero")
    equipment = dict(state.equipment)
    equipment[body.slot] = body.equipment_id
    state.equipment = equipment
    state.equipment_initialized = True
    await svc.set_hero_campaign_state(body.user_name, body.hero_id, hero_campaign_state_to_dict(state))
    return MainlinePrepareEquipmentOut(
        hero_id=state.hero_id,
        equipment=equipment,
        equipment_bonuses=equipped_stat_bonuses(equipment),
    )


# ============================================================
# POST /mainlines/{mainline_id}/prepare/complete
# ============================================================


@router.post(
    "/{mainline_id}/prepare/complete",
    response_model=AutoSaveCheckpointOut,
)
async def complete_prepare(
    mainline_id: str,
    body: PrepCompleteRequest,
    session: AsyncSession = Depends(get_session),
) -> AutoSaveCheckpointOut:
    """Player signals "I'm done prepping — ready to start".

    Triggers an auto-save with label ``f"{mainline_id}-准备"`` so the
    player can later reload to the post-prep / pre-battle state.
    The FE renders "自动存档中…… 自动存档完毕" on success.

    Pre-conditions (matches the FE8 design v2 §2.6 invariants):
      * profile exists
      * mainline is valid
      * the player may prep an inactive mainline too — the
        auto-save then captures them at the *post-prep / pre-start*
        state of an inactive profile, useful for stash-style flow
    """
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "complete_prepare entry: user=%s mainline=%s",
        body.user_name, mainline_id,
    )
    try:
        mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _load_profile(session, body.user_name)
    # Persist hero_campaign_states for any heroes in this mainline
    # that haven't been initialised yet, so the auto-save captures
    # a complete snapshot rather than a half-empty one.  This is
    # the same initialisation the /start path performs.
    svc = ProgressionService(session)
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
        cursor_index = int(
            (profile.mainline_progress or {}).get("battle_index", 0)
        )
        if not (0 <= cursor_index < len(ml.battles)):
            cursor_index = 0
    except Exception:  # pragma: no cover
        cursor_index = 0

    return await auto_save_checkpoint(
        session,
        profile,
        mainline_id=mainline_id,
        chapter_index=cursor_index,
        label=f"{mainline_id}-准备",
    )
