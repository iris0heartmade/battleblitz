from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommanderPassive:
    id: str
    hp_pct: float = 0.0
    atk_pct: float = 0.0
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    mov_delta: int = 0
    range_delta: int = 0
