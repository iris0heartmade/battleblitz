"""Mercenary (commander-points) endpoints — dual-track phase 3.

Endpoints owned here:
  * GET  /mainlines/{mainline_id}/mercenary/config  — :func:`get_mercenary_config`
  * POST /mainlines/{mainline_id}/mercenary/allocate — :func:`allocate_mercenary_points`

Plus three private helpers used here and by ``battle_lifecycle``:
  * :func:`_build_mercenary_policy` — load mainline JSON rules
  * :func:`_load_allocation_from_profile` — read persisted allocation
  * :func:`_save_allocation_to_profile` — write persisted allocation
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
)
from app.mainline.schemas import (
    ChapterBalanceConfigOut,
    CommanderAllocationOut,
    MainlineMercenaryAllocateOut,
    MainlineMercenaryAllocateRequest,
    MainlineMercenaryConfigOut,
)

from ._common import _ensure_profile_or_create, _load_profile

if TYPE_CHECKING:
    from app.mercenary_domain import CommanderAllocation

logger = logging.getLogger(__name__)

# Each submodule carries the full ``/mainlines`` prefix.
router = APIRouter(prefix="/mainlines", tags=["mainline"])


# ============================================================
# Mercenary policy + allocation helpers
# ============================================================


def _build_mercenary_policy(ml):
    """Build the server-authoritative allocation policy from mainline JSON."""
    from app.mercenary_domain import (
        ChapterBalanceConfig,
        DEFAULT_UPGRADE_RULES,
        MercenaryAllocationRules,
        UpgradeRule,
    )

    config = ml.mercenary_balance
    balance = ChapterBalanceConfig(starting_fund=int(config.starting_fund))
    configured_rules = {
        stat: UpgradeRule(
            point_cost=int(rule.point_cost), max_bonus=int(rule.max_bonus),
        )
        for stat, rule in config.stat_rules.items()
    }
    return balance, MercenaryAllocationRules(
        stat_rules=configured_rules or dict(DEFAULT_UPGRADE_RULES),
        allowed_unit_types=(
            frozenset(config.allowed_unit_types)
            if config.allowed_unit_types is not None
            else None
        ),
    )


def _load_allocation_from_profile(
    profile,
) -> "CommanderAllocation":
    """Read ``profile.mercenary_roster_state`` into a fresh
    ``CommanderAllocation`` (or a default if absent).

    The chapter determines which part of this shared commander allocation
    can be spent; no client-controlled value participates in pricing.
    """
    from app.mercenary_domain import CommanderAllocation
    stored = dict(getattr(profile, "mercenary_roster_state", {}) or {})
    alloc_payload = dict(stored.get("allocation") or {})
    allocation = CommanderAllocation(
        total_points=int(alloc_payload.get("total_points", 100)),
        spent_points=int(alloc_payload.get("spent_points", 0)),
        unit_type_upgrades={
            str(ut): dict(stats)
            for ut, stats in (alloc_payload.get("unit_type_upgrades") or {}).items()
        },
    )
    return allocation


async def _save_allocation_to_profile(
    session: AsyncSession,
    profile,
    allocation: "CommanderAllocation",
) -> None:
    """Write the allocation back into the JSON column on the profile.

    The dataclass ``unit_type_upgrades`` keys must round-trip as
    ``str``; SQLAlchemy's JSON type may coerce them, so we re-wrap
    here.
    """
    stored = dict(getattr(profile, "mercenary_roster_state", {}) or {})
    stored["allocation"] = {
        "total_points": int(allocation.total_points),
        "spent_points": int(allocation.spent_points),
        "unit_type_upgrades": {
            str(ut): {str(stat): int(value) for stat, value in stats.items()}
            for ut, stats in allocation.unit_type_upgrades.items()
        },
    }
    profile.mercenary_roster_state = stored
    await session.flush()


# ============================================================
# GET /mainlines/{mainline_id}/mercenary/config
# ============================================================


@router.get(
    "/{mainline_id}/mercenary/config",
    response_model=MainlineMercenaryConfigOut,
)
async def get_mercenary_config(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlineMercenaryConfigOut:
    """Return the chapter's balance config + the player's allocation.

    Auto-creates the profile on miss (mirrors ``/start``) so a fresh
    player can open the panel without a 404 round-trip.
    """
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "get_mercenary_config entry: mainline=%s user=%s",
        mainline_id, user_name,
    )
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mercenary_config not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mercenary_config invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _ensure_profile_or_create(session, user_name)
    allocation = _load_allocation_from_profile(profile)
    allocation.total_points = int(ml.mercenary_balance.total_points)
    balance, rules = _build_mercenary_policy(ml)
    return MainlineMercenaryConfigOut(
        mainline_id=mainline_id,
        balance=ChapterBalanceConfigOut(
            enemy_modifiers=dict(balance.enemy_modifiers),
            max_recruit_count=int(balance.max_recruit_count),
            starting_fund=int(balance.starting_fund),
            total_points=int(ml.mercenary_balance.total_points),
            allowed_unit_types=sorted(rules.available_unit_types()),
            stat_rules={
                stat: {
                    "point_cost": int(rule.point_cost),
                    "max_bonus": int(rule.max_bonus),
                }
                for stat, rule in rules.stat_rules.items()
            },
        ),
        allocation=CommanderAllocationOut(
            total_points=int(allocation.total_points),
            spent_points=int(allocation.spent_points),
            unit_type_upgrades={
                str(ut): {str(stat): int(value) for stat, value in stats.items()}
                for ut, stats in allocation.unit_type_upgrades.items()
            },
        ),
        mercenary_points=int(allocation.total_points - allocation.spent_points),
    )


# ============================================================
# POST /mainlines/{mainline_id}/mercenary/allocate
# ============================================================


@router.post(
    "/{mainline_id}/mercenary/allocate",
    response_model=MainlineMercenaryAllocateOut,
)
async def allocate_mercenary_points(
    mainline_id: str,
    body: MainlineMercenaryAllocateRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineMercenaryAllocateOut:
    """Spend mercenary points on a per-unit-type stat upgrade.

    Validates the point cost against the player's remaining budget,
    writes the upgrade into the profile's
    ``mercenary_roster_state.allocation``, and returns the new state.

    This is the dual-track "pre-battle" panel; the *application* of
    these upgrades to spawned ``Unit`` rows is a follow-up wiring
    step (Task #1 phase 2).
    """
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "allocate_mercenary_points entry: mainline=%s user=%s unit_type=%s stat=%s",
        mainline_id, body.user_name, body.unit_type, body.stat,
    )
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning(
            "allocate_mercenary_points not found: mainline=%s", mainline_id,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception(
            "allocate_mercenary_points invalid: mainline=%s", mainline_id,
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    # Strict 404: a typo'd user_name must not auto-create a wrong
    # profile (mirrors /advance, /abandon).
    profile = await _load_profile(session, body.user_name)
    allocation = _load_allocation_from_profile(profile)
    allocation.total_points = int(ml.mercenary_balance.total_points)
    _balance, rules = _build_mercenary_policy(ml)

    try:
        from app.mercenary_domain import apply_commander_upgrade
        receipt = apply_commander_upgrade(
            allocation,
            unit_type=body.unit_type,
            stat=body.stat,
            value=body.value,
            rules=rules,
        )
    except ValueError as exc:
        logger.warning(
            "allocate_mercenary_points rejected: user=%s reason=%s",
            body.user_name, exc,
        )
        status_code = (
            status.HTTP_409_CONFLICT
            if "points exceeded" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code, str(exc))

    await _save_allocation_to_profile(session, profile, allocation)
    logger.info(
        "allocate_mercenary_points ok: user=%s unit_type=%s stat=%s "
        "value=%d cost=%d spent=%d",
        body.user_name, body.unit_type, body.stat,
        body.value, receipt.cost, allocation.spent_points,
    )
    return MainlineMercenaryAllocateOut(
        ok=True,
        spent_points=int(allocation.spent_points),
        remaining_points=int(
            allocation.total_points - allocation.spent_points
        ),
        unit_type_upgrades={
            str(ut): {str(stat): int(value) for stat, value in stats.items()}
            for ut, stats in allocation.unit_type_upgrades.items()
        },
    )
