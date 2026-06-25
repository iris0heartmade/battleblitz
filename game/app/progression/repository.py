"""
Repository layer for progression data access.

Thin wrappers around SQLAlchemy queries so:
  - Service code doesn't need to know SQL
  - Tests can mock the repository instead of the DB
  - One place to add eager-loading / N+1 fixes later
"""
from __future__ import annotations

import re
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.progression.exceptions import (
    InvalidNickname,
    ProfileAlreadyExists,
    ProfileNotFound,
    UnitAlreadyExists,
    UnitNotFound,
)
from app.progression.models import PlayerProfile, UnitInstance


_NICKNAME_RE = re.compile(r"^[\w一-鿿\-]{1,32}$", re.UNICODE)


def _validate_nickname(nickname: str) -> None:
    """Nickname: 1-32 chars, word/dash/Chinese only."""
    if not _NICKNAME_RE.match(nickname):
        raise InvalidNickname(
            "nickname must be 1-32 chars (letters, digits, underscore, dash, or Chinese)"
        )


# ============================================================
# PlayerProfile
# ============================================================

class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, profile_id: int) -> PlayerProfile:
        profile = await self.session.get(PlayerProfile, profile_id)
        if profile is None:
            raise ProfileNotFound(f"profile {profile_id} not found")
        return profile

    async def get_by_name(self, user_name: str) -> PlayerProfile | None:
        result = await self.session.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == user_name)
        )
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[PlayerProfile]:
        result = await self.session.execute(
            select(PlayerProfile)
            .order_by(PlayerProfile.id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def create(self, user_name: str, *, initial_rating: int | None = None) -> PlayerProfile:
        existing = await self.get_by_name(user_name)
        if existing is not None:
            raise ProfileAlreadyExists(f"user_name {user_name!r} already taken")
        profile = PlayerProfile(
            user_name=user_name,
            rating=initial_rating if initial_rating is not None else 1000,
        )
        self.session.add(profile)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ProfileAlreadyExists(str(exc)) from exc
        return profile


# ============================================================
# UnitInstance
# ============================================================

class UnitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, unit_id: int) -> UnitInstance:
        unit = await self.session.get(UnitInstance, unit_id)
        if unit is None:
            raise UnitNotFound(f"unit {unit_id} not found")
        return unit

    async def list_for_profile(
        self, profile_id: int, limit: int = 100, offset: int = 0
    ) -> Sequence[UnitInstance]:
        result = await self.session.execute(
            select(UnitInstance)
            .where(UnitInstance.profile_id == profile_id)
            .order_by(UnitInstance.id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def create(
        self,
        profile_id: int,
        base_type: str,
        nickname: str,
        personality: str = "tactical",
    ) -> UnitInstance:
        _validate_nickname(nickname)
        unit = UnitInstance(
            profile_id=profile_id,
            base_type=base_type,
            nickname=nickname,
            personality=personality,
            career_stats={"matches": 0, "kills": 0, "deaths": 0, "mvps": 0, "wins": 0},
            equipment={"weapon": None, "armor": None, "accessory": None},
        )
        self.session.add(unit)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # Most likely the (profile_id, nickname) unique constraint
            raise UnitAlreadyExists(
                f"unit nickname {nickname!r} already exists in this profile"
            ) from exc
        return unit

    async def delete(self, unit_id: int) -> None:
        unit = await self.get(unit_id)
        await self.session.delete(unit)
        await self.session.flush()


__all__ = [
    "ProfileRepository",
    "UnitRepository",
]
