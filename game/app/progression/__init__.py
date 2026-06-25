"""
Character progression system (角色培养系统) — public API.

Top-level imports:
    from app.progression import (
        ProgressionService, PlayerProfile, UnitInstance,
        xp_to_next, award_exp, promote,
    )
"""
from app.progression.exceptions import (
    InvalidNickname,
    LevelCapReached,
    ProgressionError,
    PromoteRequirementNotMet,
    ProfileAlreadyExists,
    ProfileNotFound,
    TierCapReached,
    UnitAlreadyExists,
    UnitNotFound,
)
from app.progression.leveling import (
    GROWTH_CURVES,
    LevelUpResult,
    TALENT_POINTS_PER_LEVEL,
    TIER_LEVEL_CAP,
    TIER_PROMO_LEVEL_REQ,
    UnitLike,
    XP_CURVE,
    award_exp,
    can_level_up,
    can_promote,
    max_level_for_tier,
    promote,
    stat_at_level,
    xp_to_next,
)
from app.progression.models import (
    EquipmentTemplate,
    MatchRecord,
    PlayerProfile,
    TalentDefinition,
    UnitInstance,
)
from app.progression.service import (
    AwardXpSummary,
    ProgressionService,
    PromoteSummary,
)

__all__ = [
    # Domain
    "PlayerProfile",
    "UnitInstance",
    "EquipmentTemplate",
    "TalentDefinition",
    "MatchRecord",
    "ProgressionService",
    # Pure leveling
    "XP_CURVE",
    "TIER_LEVEL_CAP",
    "TIER_PROMO_LEVEL_REQ",
    "GROWTH_CURVES",
    "TALENT_POINTS_PER_LEVEL",
    "xp_to_next",
    "max_level_for_tier",
    "can_level_up",
    "can_promote",
    "award_exp",
    "promote",
    "stat_at_level",
    "UnitLike",
    "LevelUpResult",
    "AwardXpSummary",
    "PromoteSummary",
    # Errors
    "ProgressionError",
    "ProfileNotFound",
    "UnitNotFound",
    "ProfileAlreadyExists",
    "UnitAlreadyExists",
    "InvalidNickname",
    "LevelCapReached",
    "TierCapReached",
    "PromoteRequirementNotMet",
]
