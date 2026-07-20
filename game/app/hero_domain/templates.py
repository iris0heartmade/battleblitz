from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HeroCharacterTemplate:
    """FE-style persistent character identity."""

    hero_id: str
    default_class_id: str
    base_stats: dict[str, int]
    growth_rates: dict[str, int]
    base_weapon_ranks: dict[str, int] = field(default_factory=dict)
    promotion_routes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HeroClassTemplate:
    """FE-style class template."""

    class_id: str
    tier: int
    base_modifiers: dict[str, int]
    caps: dict[str, int]
    promotion_options: list[str] = field(default_factory=list)
    promotion_bonuses: dict[str, int] = field(default_factory=dict)
