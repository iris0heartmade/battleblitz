from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class COState:
    commander_id: str | None = None
    # 新机制下 `threshold` 含义:全队累计士气星上限(替代旧"power 触发阈值")
    threshold: int = 20
    # 全队累计获得的士气星(含已消耗),单调递增,到达 threshold 不再增加
    stars_earned_total: int = 0
    # 每次 power 扣减的固定星数(默认 6)
    power_cost: int = 6
    # 旧机制字段(过渡期保留,新代码不再写)
    meter: int = 0
    is_power_active: bool = False
    last_start_turn: int = -1

    def dump(self) -> dict[str, Any]:
        return {
            "commander_id": self.commander_id,
            "threshold": self.threshold,
            "stars_earned_total": self.stars_earned_total,
            "power_cost": self.power_cost,
            "meter": self.meter,
            "is_power_active": self.is_power_active,
            "last_start_turn": self.last_start_turn,
        }

    @classmethod
    def load(cls, data: dict[str, Any] | None) -> "COState":
        if data is None:
            return cls()
        return cls(
            commander_id=data.get("commander_id"),
            threshold=data.get("threshold", 20),
            stars_earned_total=data.get("stars_earned_total", 0),
            power_cost=data.get("power_cost", 6),
            meter=data.get("meter", 0),
            is_power_active=data.get("is_power_active", False),
            last_start_turn=data.get("last_start_turn", -1),
        )
