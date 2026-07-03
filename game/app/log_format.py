"""Chinese action-log formatters.

All in-game action log descriptions are written in Chinese so the player
sees natural-language narratives. Now with compact formatting for better
information density:

  剑士 → (5,7) -3MP
  弓兵 🗡 剑士 -18 (12HP)
  治疗师 ⚕ 骑士 +15
  骑士 ⭐连击
  弓手 ⏸

Each formatter returns the description string. The caller is responsible
for writing it into an ActionLog row via `_log(...)` in routes/actions.py
or similar. Action types are also standardized (move / attack / heal /
skill / wait / end_turn / level_up / eliminated) so the frontend can
color-code them.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple


def fmt_move(unit, path: Sequence[Tuple[int, int]], cost: int) -> str:
    """"剑士 → (5,7) -3MP" """
    if not path:
        return f"{unit.name} ⏸"
    x1, y1 = path[-1]
    return f"{unit.name} → ({x1},{y1}) -{cost}MP"


def fmt_attack(
    attacker,
    target,
    total_dmg: int,
    is_kill: bool,
    target_hp_after: int,
    counter_dmg: int = 0,
    assist: int = 0,
) -> str:
    """"弓兵 🗡 剑士 -18 💀击杀 ↩5" """
    parts = [f"{attacker.name} 🗡 {target.name} -{total_dmg}"]
    if is_kill:
        parts.append(" 💀击杀")
    else:
        parts.append(f" ({target_hp_after}HP)")
    if counter_dmg > 0:
        parts.append(f" ↩{counter_dmg}")
    if assist > 0:
        parts.append(f" +{assist}协力")
    return "".join(parts)


def fmt_wait(unit) -> str:
    return f"{unit.name} ⏸"


def fmt_end_turn(player, acted_count: int) -> str:
    return f"{player.user_name} 结束 ({acted_count}动)"


def fmt_level_up(unit, new_level: int) -> str:
    return f"{unit.name} ⬆ Lv.{new_level}"


def fmt_eliminated(player) -> str:
    return f"{player.user_name} 💀淘汰"


