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
    active_mainline: Optional[str] = None
    mainline_progress: dict = Field(default_factory=dict)
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


# ============================================================
# Mainline progress (Step 2)
# ============================================================
#
# JSON contract for `PlayerProfile.mainline_progress`:
#   {
#     "battle_index": int,    # 0-based; == len(battles) => cleared
#     "scene_id": str,        # key into Mainline.dialogues
#     "started_at": str|None  # ISO-8601 UTC; None iff no active mainline
#   }
#
# Kept in sync with the JSON column default on `PlayerProfile` and with
# the helpers in `service.ProgressionService` (set_active_mainline /
# advance_mainline_progress / clear_mainline_progress).

_MAINLINE_ID_RE = r"^[a-z0-9_]{3,64}$"


class MainlineProgress(BaseModel):
    """In-campaign cursor for a player profile.

    Pure data — no methods. The Pydantic model is the single source of
    truth for the wire/DB JSON contract; the service layer serialises
    to a dict before assigning to the ORM column.
    """
    battle_index: int = Field(ge=0, le=10_000, description="0-based battle cursor")
    scene_id: str = Field(min_length=1, max_length=64)
    started_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp of the campaign start, or None",
        max_length=64,
    )


class StartMainlineRequest(BaseModel):
    """`POST /profile/{user_name}/mainline/start` — begin a new campaign.

    `force=True` lets a player abandon any in-progress mainline and
    start a new one in a single call (debug / "new game+" use).
    """
    mainline_id: str = Field(pattern=_MAINLINE_ID_RE)
    force: bool = Field(default=False, description="Reset any active mainline first")


class AdvanceMainlineRequest(BaseModel):
    """`POST /profile/{user_name}/mainline/advance` — move the cursor.

    Two operations are supported, both server-side validated:
      * If `scene_id` is given: the dialogue cursor is moved to that
        key (which must exist in `Mainline.dialogues`).
      * If `next_battle` is True: `battle_index` is incremented by 1.
        Both fields can be combined — set the new dialogue for the
        upcoming battle *and* advance the battle index in one call.

    The server also detects the "just finished the last battle" case
    (battle_index == len(battles)) and automatically clears
    `active_mainline` after writing the final progress row.
    """
    scene_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    next_battle: bool = Field(default=False)


class AbandonMainlineRequest(BaseModel):
    """`POST /profile/{user_name}/mainline/abandon` — drop any active mainline.

    Currently no fields — request body is optional. Kept as its own
    model so the schema can grow (e.g. a `reason` field for telemetry).
    """
    pass


__all__ = [
    "APIModel",
    # Profiles
    "CreateProfileRequest",
    "PlayerProfileOut",
    # Units
    "VALID_BASE_TYPES",
    "VALID_PERSONALITIES",
    "CreateUnitRequest",
    "AwardXpRequest",
    "PromoteRequest",
    "UnitInstanceOut",
    # Operation results
    "AwardXpResult",
    "PromoteResult",
    # Mainline (Step 2)
    "MainlineProgress",
    "StartMainlineRequest",
    "AdvanceMainlineRequest",
    "AbandonMainlineRequest",
]
