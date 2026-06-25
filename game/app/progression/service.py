"""
Service layer for progression — business orchestration on top of repos.

A service is a single class that holds the session and the repos it needs,
and exposes intent-named methods (create_profile, award_xp, promote).

Why a class instead of free functions:
  - One session injection point (we use FastAPI's Depends on the API layer)
  - Repos are constructed once, easy to mock in tests
  - Future "match-end hook" can live here: `apply_match_result(profile, snapshot)`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.progression.exceptions import (
    LevelCapReached,
    PromoteRequirementNotMet,
    TierCapReached,
)
from app.progression.leveling import (
    can_promote,
    can_level_up,
    award_exp as _award_exp,
    promote as _promote,
)
from app.progression.models import PlayerProfile, UnitInstance
from app.progression.repository import ProfileRepository, UnitRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AwardXpSummary:
    unit_id: int
    levels_gained: int
    new_level: int
    new_exp: int
    talent_points_awarded: int
    capped: bool


@dataclass(frozen=True)
class PromoteSummary:
    unit_id: int
    old_tier: int
    new_tier: int
    new_level_cap: int


class ProgressionService:
    """Orchestrates profile + unit + leveling operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profiles = ProfileRepository(session)
        self.units = UnitRepository(session)

    # ── Profiles ────────────────────────────────────────────

    async def create_profile(
        self, user_name: str, *, initial_rating: int | None = None
    ) -> PlayerProfile:
        profile = await self.profiles.create(
            user_name, initial_rating=initial_rating
        )
        await self.session.flush()
        logger.info(
            "Profile created: id=%d user=%r rating=%d",
            profile.id, profile.user_name, profile.rating,
        )
        return profile

    async def get_profile(self, profile_id: int) -> PlayerProfile:
        return await self.profiles.get(profile_id)

    async def list_profiles(self, limit: int = 100, offset: int = 0) -> list[PlayerProfile]:
        return list(await self.profiles.list_all(limit=limit, offset=offset))

    # ── Units ───────────────────────────────────────────────

    async def create_unit(
        self,
        profile_id: int,
        base_type: str,
        nickname: str,
        personality: str = "tactical",
    ) -> UnitInstance:
        # Confirm profile exists (will raise ProfileNotFound if not)
        await self.profiles.get(profile_id)
        unit = await self.units.create(
            profile_id=profile_id,
            base_type=base_type,
            nickname=nickname,
            personality=personality,
        )
        await self.session.flush()
        logger.info(
            "Unit created: id=%d profile=%d type=%s nick=%r",
            unit.id, unit.profile_id, unit.base_type, unit.nickname,
        )
        return unit

    async def get_unit(self, unit_id: int) -> UnitInstance:
        return await self.units.get(unit_id)

    async def list_units(self, profile_id: int) -> list[UnitInstance]:
        return list(await self.units.list_for_profile(profile_id))

    # ── Leveling ────────────────────────────────────────────

    async def award_xp(
        self, unit_id: int, amount: int, *, reason: str = "manual"
    ) -> AwardXpSummary:
        unit = await self.units.get(unit_id)
        was_at_cap = not can_level_up(unit)
        old_level = unit.level

        result = _award_exp(unit, amount)
        capped = was_at_cap or not can_level_up(unit) and result.levels_gained == 0

        await self.session.flush()
        logger.info(
            "XP awarded: unit=%d amount=%d reason=%s levels=%d new_lv=%d",
            unit_id, amount, reason, result.levels_gained, result.new_level,
        )
        return AwardXpSummary(
            unit_id=unit_id,
            levels_gained=result.levels_gained,
            new_level=result.new_level,
            new_exp=unit.exp,
            talent_points_awarded=result.talent_points_awarded,
            capped=capped,
        )

    async def promote(
        self, unit_id: int, *, force: bool = False
    ) -> PromoteSummary:
        unit = await self.units.get(unit_id)

        if unit.tier >= 3:
            raise TierCapReached(f"unit {unit_id} is already at max tier (3)")

        if not can_promote(unit) and not force:
            from app.progression.leveling import TIER_PROMO_LEVEL_REQ
            required = TIER_PROMO_LEVEL_REQ.get(unit.tier, 99)
            raise PromoteRequirementNotMet(
                f"unit {unit_id} needs level {required} to promote from tier {unit.tier} "
                f"(currently level {unit.level})"
            )

        old_tier = unit.tier
        if force:
            # Bypass the level check inside _promote (debug/admin only).
            unit.tier += 1
        else:
            _promote(unit)

        from app.progression.leveling import max_level_for_tier
        new_cap = max_level_for_tier(unit.tier)
        await self.session.flush()
        logger.info(
            "Unit promoted: id=%d %d -> %d new_cap=%d force=%s",
            unit_id, old_tier, unit.tier, new_cap, force,
        )
        return PromoteSummary(
            unit_id=unit_id,
            old_tier=old_tier,
            new_tier=unit.tier,
            new_level_cap=new_cap,
        )


__all__ = [
    "ProgressionService",
    "AwardXpSummary",
    "PromoteSummary",
]
