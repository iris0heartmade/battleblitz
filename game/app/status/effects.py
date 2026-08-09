"""Status effect 注册表 + 数据形状工具函数。

Effect 数据形状(每个 dict):
    type: str
    remaining_turns: int        # 剩余大回合;每次 turn_start -1
    applied_turn: int           # 施加时的 game.turn_number
    applied_by: int | None      # 施加者 player_id(可选,审计用)
    params: dict                # type-specific 参数
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class EffectDef:
    """单个 effect 类型的注册表条目。"""
    type_id: str                  # "poison" / "paralyze" / "blind" / "slow" / "silence"
    display_cn: str               # 中文显示名("毒" / "麻痹" 等)
    glyph: str                    # 单字符 emoji/图标(UI 用)
    default_remaining: int        # 默认持续回合数
    # type-specific 默认 params
    default_params: dict = field(default_factory=dict)


# 注册表 — 加新 effect 在这里加一行
EFFECT_DEFS: dict[str, EffectDef] = {
    "poison":   EffectDef("poison",   "毒",   "☠", 3, {"dmg_pct": 0.05}),
    "paralyze": EffectDef("paralyze", "麻痹", "⚡", 2, {"miss_pct": 0.25}),
    "blind":    EffectDef("blind",    "致盲", "◌", 2, {"miss_pct": 0.50}),
    "slow":     EffectDef("slow",     "减速", "❄", 2, {"mov_mult": 0.50}),
    "silence":  EffectDef("silence",  "沉默", "🔇", 1, {}),
}


EFFECT_TYPES = list(EFFECT_DEFS.keys())


def add_effect(
    unit: Any,
    effect_type: str,
    *,
    applied_turn: int,
    applied_by: Optional[int] = None,
    remaining_turns: Optional[int] = None,
    params: Optional[dict] = None,
) -> dict:
    """往 unit.status_effects 加一个 effect dict。返回添加/合并后的 effect。

    如果同 type 已存在,取 max(remaining_turns, 已有);新 params 优先合并到
    旧 params 里;applied_turn / applied_by 用最新值。

    L3 修复:旧实现是 *原地改 caller 持有的 effect dict*,这会让外部提前
    拿走的 `old = find_effect(unit, "poison")` 引用被偷偷改值。现在改成
    构造新 dict 替换 list 里同 type 的位置 — 返回的是新对象,旧引用稳定。
    """
    if effect_type not in EFFECT_DEFS:
        raise ValueError(f"unknown status effect type: {effect_type!r}")
    defn = EFFECT_DEFS[effect_type]
    effects = list(getattr(unit, "status_effects", []) or [])
    # 已有同 type → 构造新 dict 替换,不原地改 caller 引用的旧 dict
    for idx, eff in enumerate(effects):
        if eff.get("type") == effect_type:
            old_params = eff.get("params") or {}
            merged_params = dict(old_params)
            if params:
                merged_params.update({k: v for k, v in params.items() if v is not None})
            new_eff = {
                "type": effect_type,
                "remaining_turns": max(
                    int(eff.get("remaining_turns", 0)),
                    remaining_turns if remaining_turns is not None else defn.default_remaining,
                ),
                "applied_turn": applied_turn,  # 最新覆盖
                "applied_by": applied_by if applied_by is not None else eff.get("applied_by"),
                "params": merged_params,
            }
            effects[idx] = new_eff
            unit.status_effects = effects
            return new_eff
    # 新增
    eff = {
        "type": effect_type,
        "remaining_turns": remaining_turns if remaining_turns is not None else defn.default_remaining,
        "applied_turn": applied_turn,
        "applied_by": applied_by,
        "params": dict(params) if params else dict(defn.default_params),
    }
    effects.append(eff)
    unit.status_effects = effects
    return eff


def remove_effect(unit: Any, effect_type: str) -> bool:
    """从 unit.status_effects 移除指定 type。返回是否实际删除。"""
    effects = list(getattr(unit, "status_effects", []) or [])
    new_effects = [e for e in effects if e.get("type") != effect_type]
    if len(new_effects) != len(effects):
        unit.status_effects = new_effects
        return True
    return False


def find_effect(unit: Any, effect_type: str) -> Optional[dict]:
    """取第一个匹配 type 的 effect dict,无则 None。"""
    for eff in (getattr(unit, "status_effects", []) or []):
        if eff.get("type") == effect_type:
            return eff
    return None


def has_effect(unit: Any, effect_type: str) -> bool:
    return find_effect(unit, effect_type) is not None