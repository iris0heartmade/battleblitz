"""
Pydantic v2 request/response models for the progression API.

Keep these in sync with the ORM models, but separate so we can evolve
the wire format without touching the DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ============================================================
# PlayerProfile
# ============================================================

class CreateProfileRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=64)
    # Optional: start with a custom rating (for testing / migrations)
    initial_rating: Optional[int] = Field(default=None, ge=0, le=5000)


class PlayerProfileOut(APIModel):
    id: int
    user_name: str
    gold: int
    unlock_points: int
    unlocked_classes: list[str]
    unlocked_cosmetics: dict
    current_season: int
    rating: int
    created_at: datetime
    updated_at: datetime


# ============================================================
# UnitInstance
# ============================================================

VALID_BASE_TYPES = ("swordsman", "archer", "knight", "healer")
VALID_PERSONALITIES = ("brave", "coward", "tactical", "loyal")


class CreateUnitRequest(BaseModel):
    base_type: str = Field(pattern=f"^({'|'.join(VALID_BASE_TYPES)})$")
    nickname: str = Field(min_length=1, max_length=32)
    personality: str = Field(default="tactical",
                             pattern=f"^({'|'.join(VALID_PERSONALITIES)})$")


class AwardXpRequest(BaseModel):
    amount: int = Field(ge=1, le=100_000, description="EXP to award")
    reason: str = Field(default="manual", max_length=64)


class PromoteRequest(BaseModel):
    force: bool = Field(default=False, description="Bypass level check (debug only)")


class UnitInstanceOut(APIModel):
    id: int
    profile_id: int
    base_type: str
    nickname: str
    tier: int
    level: int
    exp: int
    personality: str
    talent_points: int
    talents: dict
    equipment: dict
    career_stats: dict
    created_at: datetime
    updated_at: datetime


# ============================================================
# Operation results
# ============================================================

class AwardXpResult(BaseModel):
    unit_id: int
    levels_gained: int
    new_level: int
    new_exp: int
    talent_points_awarded: int
    capped: bool = False
    reason: str


class PromoteResult(BaseModel):
    unit_id: int
    old_tier: int
    new_tier: int
    new_level_cap: int
