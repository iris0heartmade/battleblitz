from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MercenaryTemplate:
    unit_type: str
    base_stats: dict[str, int]
    recruit_cost: int
    default_skills: list[str] = field(default_factory=list)


@dataclass
class ChapterBalanceConfig:
    enemy_modifiers: dict[str, int] = field(
        default_factory=lambda: {
            "attack": 0,
            "defense": 0,
            "income": 0,
            "move": 0,
            "vision": 0,
        }
    )
    max_recruit_count: int = 5
    starting_fund: int = 1000
