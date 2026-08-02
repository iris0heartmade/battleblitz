"""Status effect 通用框架 (P+)

设计目标:
- 单个 Unit 同时挂多个 effect(poison + paralyze + slow 不互斥)
- 每个 effect 走统一的 hook 入口(turn_start / attack / move)
- 加新 effect 只需写一个数据类 + 钩子函数,不需改 schema

数据形状:
    Unit.status_effects: list[dict]
        每个 dict:
            type: str            # 注册表里的 key
            remaining_turns: int # 剩余大回合(每次 turn_start 减 1,<=0 时过期)
            applied_turn: int    # 施加时的 game.turn_number(审计/排序)
            applied_by: int|None # 施加者 player_id(可选)
            params: dict         # type-specific 参数

钩子时机:
- on_turn_start(unit, game_turn_number) -> list[str]
    返回该回合被消耗的 effect types(用于 UI 提示)
- should_skip_action(unit, rng) -> bool
    paralyze 等:概率不能行动(钩子层,不依赖 engine 的 attack 路径)
- modify_hit_chance(unit, base) -> float
    blind 等:返回命中率乘子
- modify_mov(unit, base) -> int
    slow 等:返回调整后 MOV
- should_block_attack(unit, kind) -> bool
    silence 等:阻止主动攻击("outgoing")或反击("incoming")

跨语言对照:
- godot 端读 UnitOut.status_effects 渲染图标 / tooltip
"""
from app.status.effects import (
    EffectDef,
    EFFECT_DEFS,
    EFFECT_TYPES,
    add_effect,
    remove_effect,
    find_effect,
    has_effect,
)
from app.status.engine import (
    tick_effects_at_turn_start,
    should_skip_action,
    modify_hit_chance,
    modify_mov,
    should_block_attack,
    is_silenced,
    get_status_summary,
)

__all__ = [
    "EffectDef",
    "EFFECT_DEFS",
    "EFFECT_TYPES",
    "add_effect",
    "remove_effect",
    "find_effect",
    "has_effect",
    "tick_effects_at_turn_start",
    "should_skip_action",
    "modify_hit_chance",
    "modify_mov",
    "should_block_attack",
    "is_silenced",
    "get_status_summary",
]