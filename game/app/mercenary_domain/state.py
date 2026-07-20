from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommanderAllocation:
    total_points: int = 100
    spent_points: int = 0
    unit_type_upgrades: dict[str, dict[str, int]] = field(default_factory=dict)

    def add_upgrade(self, unit_type: str, stat: str, value: int, cost: int) -> None:
        if self.spent_points + cost > self.total_points:
            raise ValueError("points exceeded")
        bucket = self.unit_type_upgrades.setdefault(unit_type, {})
        bucket[stat] = bucket.get(stat, 0) + value
        self.spent_points += cost


@dataclass
class MercenaryRosterState:
    recruited_units: list[dict[str, object]] = field(default_factory=list)
    veteran_progress: dict[str, int] = field(default_factory=dict)
