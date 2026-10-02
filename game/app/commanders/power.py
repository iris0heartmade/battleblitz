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
    # ---- 鸢影·沉默领域 (P+) 预留字段 ----
    # 效果实现尚未完成(详见 heroes/yuanying.py 注释);这里只是把参数固化到 dataclass,
    # 等沉默状态系统就绪后会读这两字段生成领域效果。
    silence_radius: int = 0       # 0 = 关闭;2 = 5×5 方形(中心 ±2)
    silence_duration_turns: int = 0  # 0 = 关闭;1 = 持续 1 个大回合
