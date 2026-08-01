from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommanderPower:
    id: str
    atk_pct: float = 0.0
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    range_delta: int = 0
    heal_pct: float = 0.0
    extra_mov: int = 0
    # 固定消耗:激活 power 时从 stars_earned_total 扣减的星数。默认 6。
    cost: int = 6
