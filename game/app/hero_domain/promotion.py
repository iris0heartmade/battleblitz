from __future__ import annotations

from dataclasses import replace
from typing import Callable

from app.hero_domain.state import HeroCampaignState
from app.hero_domain.templates import HeroClassTemplate

HERO_PROMOTION_LEVEL = 20


class HeroPromotionError(ValueError):
    """Raised when a Hero promotion request is invalid."""


def can_promote_hero(
    state: HeroCampaignState,
    hero_class: HeroClassTemplate,
    *,
    min_level: int = HERO_PROMOTION_LEVEL,
) -> bool:
    if state.promoted:
        return False
    if hero_class.tier >= 2:
        return False
    if state.level < min_level:
        return False
    return bool(hero_class.promotion_options)


def promote_hero(
    state: HeroCampaignState,
    current_class: HeroClassTemplate,
    target_class: HeroClassTemplate,
    *,
    min_level: int = HERO_PROMOTION_LEVEL,
) -> HeroCampaignState:
    if not can_promote_hero(state, current_class, min_level=min_level):
        raise HeroPromotionError(
            f"hero {state.hero_id!r} is not eligible to promote from {current_class.class_id!r}"
        )
    if target_class.class_id not in current_class.promotion_options:
        raise HeroPromotionError(
            f"class {target_class.class_id!r} is not a promotion option for {current_class.class_id!r}"
        )

    promoted_stats = dict(state.base_stats)
    for stat, bonus in target_class.promotion_bonuses.items():
        promoted_stats[stat] = promoted_stats.get(stat, 0) + bonus
        cap = target_class.caps.get(stat)
        if cap is not None:
            promoted_stats[stat] = min(promoted_stats[stat], cap)

    return replace(
        state,
        class_id=target_class.class_id,
        level=1,
        exp=0,
        base_stats=promoted_stats,
        promoted=True,
    )


def is_promoted_class(
    class_id: str,
    class_lookup: Callable[[str], HeroClassTemplate],
) -> bool:
    return class_lookup(class_id).tier >= 2
