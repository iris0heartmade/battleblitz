from app.hero_domain.free_mode import HeroPresetState, build_standardized_hero_state
from app.hero_domain.legacy_bridge import (
    build_hero_character_template,
    build_hero_class_template,
    build_initial_campaign_state,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)
from app.hero_domain.materialize import HeroBattleState, build_hero_battle_state
from app.hero_domain.promotion import (
    HERO_PROMOTION_LEVEL,
    HeroPromotionError,
    can_promote_hero,
    promote_hero,
)
from app.hero_domain.spawn import build_campaign_spawn_payload
from app.hero_domain.state import HeroCampaignState
from app.hero_domain.equipment import (
    EQUIPMENT_SLOTS,
    STARTER_INVENTORY,
    catalog_payload,
    default_equipment_for_class,
    equipped_stat_bonuses,
    get_equipment,
)
from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate

__all__ = [
    "HERO_PROMOTION_LEVEL",
    "HeroBattleState",
    "HeroCampaignState",
    "EQUIPMENT_SLOTS",
    "STARTER_INVENTORY",
    "catalog_payload",
    "default_equipment_for_class",
    "equipped_stat_bonuses",
    "get_equipment",
    "HeroCharacterTemplate",
    "HeroClassTemplate",
    "HeroPresetState",
    "HeroPromotionError",
    "build_campaign_spawn_payload",
    "build_hero_character_template",
    "build_hero_class_template",
    "build_initial_campaign_state",
    "build_hero_battle_state",
    "build_standardized_hero_state",
    "can_promote_hero",
    "hero_campaign_state_from_dict",
    "hero_campaign_state_to_dict",
    "promote_hero",
]
