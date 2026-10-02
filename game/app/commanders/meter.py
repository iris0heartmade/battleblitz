"""CO power star meter.

新机制:
- 全队每获得一颗士气星(杀敌时通过 award_morale 钩入)累加到 stars_earned_total
- 达到 threshold cap 后不再增加
- 放 power 时固定扣 power_cost 颗星(默认 6)
- 每回合不重置累计,放完才扣
- 不可为负数(放 power 前 can_fire 校验 stars >= power_cost)
"""
from __future__ import annotations

from typing import Any


def _ensure_co_state(player: Any) -> dict[str, Any]:
    """Ensure co_state dict has all required fields with sane defaults.

    容错旧档案 / 外部构造的 co_state(可能缺新字段)。修改 player.co_state 原地补齐。
    """
    state = getattr(player, "co_state", None)
    if state is None:
        state = {}
        player.co_state = state
    if "commander_id" not in state:
        state["commander_id"] = getattr(player, "commander_id", None)
    if "threshold" not in state:
        state["threshold"] = 20
    if "stars_earned_total" not in state:
        state["stars_earned_total"] = 0
    if "power_cost" not in state:
        state["power_cost"] = 6
    # 旧字段兜底(过渡期保留)
    state.setdefault("meter", 0)
    state.setdefault("is_power_active", False)
    state.setdefault("last_start_turn", -1)
    return state


def record_morale_star(player: Any, count: int = 1) -> int:
    """累加 stars_earned_total,达到 threshold cap 后停止增加。

    Returns:
        实际增加量(= 0 表示已达 cap 或无指挥官)。
    """
    if getattr(player, "commander_id", None) is None:
        return 0
    state = _ensure_co_state(player)
    cap = int(state.get("threshold", 20))
    cur = int(state.get("stars_earned_total", 0))
    if cur >= cap:
        return 0
    delta = min(int(count), cap - cur)
    state["stars_earned_total"] = cur + delta
    # SQLAlchemy:JSON 字段需要 flag_modified 才会被 commit
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(player, "co_state")
    except Exception:
        # 非 ORM 对象(SimpleNamespace 测试用例)忽略
        pass
    return delta


def consume_power_stars(player: Any) -> int:
    """从 stars_earned_total 扣除 power_cost 颗星。

    Returns:
        扣除后剩余星数。

    Raises:
        ValueError: stars_earned_total < power_cost

    注意(不变式):此函数**只**扣 player.co_state.stars_earned_total,
    不会反向影响任何 unit.morale。单位的士气星(0..MORALE_MAX)
    与 CO 累积槽是单向的"添加"关系:
        unit.morale +1   ->   stars_earned_total +1
        consume_power_stars   ->   (只减累积槽,不动单位 morale)
    """
    state = _ensure_co_state(player)
    cost = int(state.get("power_cost", 6))
    cur = int(state.get("stars_earned_total", 0))
    if cur < cost:
        raise ValueError(
            f"insufficient stars to fire CO power "
            f"(have {cur}, need {cost})"
        )
    state["stars_earned_total"] = cur - cost
    # SQLAlchemy:JSON 字段需要 flag_modified
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(player, "co_state")
    except Exception:
        pass
    return state["stars_earned_total"]


__all__ = [
    "_ensure_co_state",
    "record_morale_star",
    "consume_power_stars",
]
