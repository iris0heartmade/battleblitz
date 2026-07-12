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
