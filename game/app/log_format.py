"""Chinese action-log formatters.

All in-game action log descriptions are written in Chinese so the player
sees natural-language narratives like:

  剑士 从 (3,5) 移动到 (5,7)，消耗 3 MP
  弓兵 对 剑士 发动攻击，造成 18 点伤害 [击杀]
  治疗师 治疗 骑士，恢复 15 点 HP
  骑士 发动「连击」
  弓手 原地待命

Each formatter returns the description string. The caller is responsible
for writing it into an ActionLog row via `_log(...)` in routes/actions.py
or similar. Action types are also standardized (move / attack / heal /
skill / wait / end_turn / level_up / eliminated) so the frontend can
color-code them.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple


def fmt_move(unit, path: Sequence[Tuple[int, int]], cost: int) -> str:
    """"剑士 从 (3,5) 移动到 (5,7)，消耗 3 MP" """
    if not path:
        return f"{unit.name} 原地待命"
    x0, y0 = path[0]
    x1, y1 = path[-1]
    return f"{unit.name} 从 ({x0},{y0}) 移动到 ({x1},{y1})，消耗 {cost} MP"


def fmt_attack(
    attacker,
    target,
    total_dmg: int,
    is_kill: bool,
    target_hp_after: int,
    counter_dmg: int = 0,
    assist: int = 0,
) -> str:
    """"弓兵 对 剑士 发动攻击，造成 18 点伤害 [击杀] → 反击 5" """
    parts = [f"{attacker.name} 对 {target.name} 发动攻击"]
    parts.append(f"，造成 {total_dmg} 点伤害")
    if is_kill:
        parts.append(" [击杀]")
    else:
        parts.append(f"（{target.name} 剩余 {target_hp_after} HP）")
    if counter_dmg > 0:
        parts.append(f" → {target.name} 反击 {counter_dmg} 点伤害")
    if assist > 0:
        parts.append(f"（{assist} 名友军协力）")
    return "".join(parts)


def fmt_wait(unit) -> str:
    return f"{unit.name} 原地待命"


def fmt_end_turn(player, acted_count: int) -> str:
    return f"{player.user_name} 结束回合（使用了 {acted_count} 次行动）"


def fmt_level_up(unit, new_level: int) -> str:
    return f"{unit.name} 升到了 Lv.{new_level}！"


def fmt_eliminated(player) -> str:
    return f"{player.user_name} 已被淘汰！"


