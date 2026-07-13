from __future__ import annotations

from dataclasses import dataclass, field

from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate


@dataclass
class HeroCampaignState:
    """Persistent Hero state stored in campaign/profile data."""

    hero_id: str
    class_id: str
    level: int
    exp: int
    base_stats: dict[str, int]
    weapon_ranks: dict[str, int] = field(default_factory=dict)
    learned_skills: list[str] = field(default_factory=list)
    promoted: bool = False
    equipment: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def from_templates(
        cls,
        character: HeroCharacterTemplate,
        hero_class: HeroClassTemplate,
    ) -> "HeroCampaignState":
        merged_stats = dict(character.base_stats)
        for stat, bonus in hero_class.base_modifiers.items():
            merged_stats[stat] = merged_stats.get(stat, 0) + bonus
        return cls(
            hero_id=character.hero_id,
            class_id=hero_class.class_id,
            level=1,
            exp=0,
            base_stats=merged_stats,
            weapon_ranks=dict(character.base_weapon_ranks),
        )
