from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class COState:
    commander_id: str | None = None
    meter: int = 0
    threshold: int = 20
    is_power_active: bool = False
    last_start_turn: int = -1

    def dump(self) -> dict[str, Any]:
        return {
            "commander_id": self.commander_id,
            "meter": self.meter,
            "threshold": self.threshold,
            "is_power_active": self.is_power_active,
            "last_start_turn": self.last_start_turn,
        }

    @classmethod
    def load(cls, data: dict[str, Any] | None) -> "COState":
        if data is None:
            return cls()
        return cls(
            commander_id=data.get("commander_id"),
            meter=data.get("meter", 0),
            threshold=data.get("threshold", 20),
            is_power_active=data.get("is_power_active", False),
            last_start_turn=data.get("last_start_turn", -1),
        )
