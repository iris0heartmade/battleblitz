"""Status effect 引擎 — 钩子函数集中实现。

所有 hook 函数:
- on_turn_start:每个 effect 走自己的逻辑(poison 扣 HP、paralyze 概率不行动 等)
- should_skip_action:paralyze → 概率 skip
- modify_hit_chance:blind → 降命中率
- modify_mov:slow → 降 MOV
- should_block_attack:silence → 阻止 attack / counter
- is_silenced:helper,silence 状态走 status_effects
"""
from __future__ import annotations

import copy
import random
from typing import Any

from sqlalchemy import inspect as _sa_inspect


def _flag_status_effects_modified(unit: Any) -> None:
    """SQLAlchemy 默认的 JSON column 不跟踪 list 内部 dict 的 mutation;
    整体 list 引用替换时,如果 new_effects 里只是原 dict 引用,
    history.has_changes() 也会返回 False,commit 时不会发出 UPDATE。

    对 ORM 单位的 status_effects,显式 flag_modified 强制 SQLAlchemy
    在下一次 flush 时把当前 list 序列化写回 DB。

    非 ORM 对象(SimpleNamespace、Pydantic、纯数据类)没有 SQLAlchemy 状态,
    这里必须跳过 —— 不然 _sa_inspect 会抛 NoInspectionAvailable,
    把 unit_test 路径全打挂。
    """
    try:
        state = _sa_inspect(unit)
    except Exception:  # noqa: BLE001 - 非 ORM 对象就是 no-op
        return
    if state.persistent or state.detached:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(unit, "status_effects")


def tick_effects_at_turn_start(unit: Any, *, game_turn_number: int) -> list[str]:
    """每个 effect 类型在该单位 owner 回合开始时被调用。

    默认行为:remaining_turns -= 1,<=0 时移除。
    type-specific 副作用(扣 HP 等)在 EFFECT_DEFS 里查表后调用。

    Returns: 本回合过期 / 消耗的 effect type 列表(用于 UI 提示)。
    """
    effects = list(getattr(unit, "status_effects", []) or [])
    if not effects:
        return []
    expired: list[str] = []
    new_effects: list[dict] = []
    for eff in effects:
        eff_type = eff.get("type")
        if eff_type == "poison":
            # 持续伤害:扣 max_hp × dmg_pct
            dmg_pct = float(eff.get("params", {}).get("dmg_pct", 0.05))
            max_hp = int(getattr(unit, "max_hp", 1))
            dmg = max(1, round(max_hp * dmg_pct))
            cur_hp = int(getattr(unit, "hp", 0))
            new_hp = max(0, cur_hp - dmg)
            unit.hp = new_hp
        # 默认消耗 1 回合。用 deepcopy 构造新 entry,避免 SQLAlchemy 的
        # JSON column history 把"原 dict 引用在新 list 里"误判为未变化,
        # 导致 commit 时丢更新。
        new_eff = copy.deepcopy(eff)
        new_eff["remaining_turns"] = int(new_eff.get("remaining_turns", 0)) - 1
        if new_eff["remaining_turns"] <= 0:
            expired.append(eff_type)
        else:
            new_effects.append(new_eff)
    unit.status_effects = new_effects
    _flag_status_effects_modified(unit)
    return expired


def should_skip_action(unit: Any, *, rng: random.Random | None = None) -> tuple[bool, str]:
    """返回 (是否跳过本回合行动, 原因)。

    paralyze:miss_pct 概率不能行动(默认 25%)。
    """
    eff = _find_by_type(unit, "paralyze")
    if eff is None:
        return (False, "")
    miss_pct = float(eff.get("params", {}).get("miss_pct", 0.25))
    if rng is None:
        rng = random.Random()
    if rng.random() < miss_pct:
        return (True, f"麻痹({int(miss_pct * 100)}%) → 本回合不能行动")
    return (False, "")


def modify_hit_chance(unit: Any, *, base: float = 1.0) -> float:
    """返回该单位命中率乘子(0.0 ~ 1.0)。blind:miss_pct。

    base = 1.0 表示原本必中,> 1.0 表示加 hit 加成,< 1.0 表示已有减益。
    """
    eff = _find_by_type(unit, "blind")
    if eff is None:
        return base
    miss_pct = float(eff.get("params", {}).get("miss_pct", 0.50))
    return base * (1.0 - miss_pct)


def modify_mov(unit: Any, *, base: int) -> int:
    """返回该单位调整后的 MOV。slow:mov_mult(默认 0.5)。"""
    eff = _find_by_type(unit, "slow")
    if eff is None:
        return base
    mult = float(eff.get("params", {}).get("mov_mult", 0.50))
    return max(1, round(base * mult))


def should_block_attack(unit: Any, *, kind: str) -> tuple[bool, str]:
    """silence 检查:阻止主动攻击("outgoing")或反击("incoming")。

    Returns: (是否阻止, 原因)
    """
    if not is_silenced(unit):
        return (False, "")
    if kind == "outgoing":
        return (True, "被沉默,无法攻击")
    if kind == "incoming":
        return (True, "被沉默,无法反击")
    return (False, "")


def is_silenced(unit: Any) -> bool:
    """读 status_effects 是否有 silence effect。

    只读新字段;旧 silence_until_turn 字段请走 commanders.effects.is_unit_silenced()。
    """
    eff = _find_by_type(unit, "silence")
    return eff is not None


def get_status_summary(unit: Any) -> list[dict]:
    """取单位所有 active status 的展示信息(给 UI)。

    Returns: [{"type": "poison", "display_cn": "毒", "glyph": "☠", "remaining": 2}, ...]
    """
    from app.status.effects import EFFECT_DEFS
    out: list[dict] = []
    for eff in (getattr(unit, "status_effects", []) or []):
        t = eff.get("type")
        defn = EFFECT_DEFS.get(t)
        if defn is None:
            continue
        out.append({
            "type": t,
            "display_cn": defn.display_cn,
            "glyph": defn.glyph,
            "remaining": int(eff.get("remaining_turns", 0)),
        })
    return out


def _find_by_type(unit: Any, effect_type: str):
    """helper:按 type 取 effect dict。"""
    for eff in (getattr(unit, "status_effects", []) or []):
        if eff.get("type") == effect_type:
            return eff
    return None