"""Warrior — 斧战士(Phase 2 §2 generic T1)。

新增 T1 兵种。数值按 FE8 L10 expected 1:1 校准(Fighter L10):
  base_hp 28 / base_atk 10 / base_def 3 / base_mov 3 / 攻击射程 1
  Atk 高 / Def 低 / Mov 慢 — 重击型,适合近身输出。
  Berserker 是它的 T2 转职。
"""
from app.classes.units.base import BaseUnitClass


class Warrior(BaseUnitClass):
    type_id = "warrior"
    display_cn = "斧战士"
    display_en = "Warrior"
    glyph = "斧"

    # 数值 — FE8 L10 1:1(Fighter L10 expected)
    base_hp = 28
    base_atk = 10
    base_def = 3
    base_mov = 4

    # Magic stats — physical unit
    base_matk = 4
    base_mdef = 4

    default_skills = []
    attack_range = 1
    min_attack_range = 0
    can_move_after_action = False
    ignores_line_of_sight = False
    attack_kind = "physical"

    strong_against = []  # 暂无克制关系(斧克剑,剑系刚平衡)

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 80, 'atk': 50, 'def': 35, 'matk': 35, 'mdef': 35, 'mov': 0}
