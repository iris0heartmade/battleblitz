"""Berserker — 狂战士(Phase 2 §2 generic T2)。

Warrior 转职。数值按 FE8 L10 expected 1:1 校准(Berserker L10):
  base_hp 30 / base_atk 14 / base_def 5 / base_mov 4 / 攻击射程 1
  极端 Atk + 中等 Def — 玻璃大炮型近战。
"""
from app.classes.units.base import BaseUnitClass


class Berserker(BaseUnitClass):
    type_id = "berserker"
    display_cn = "狂战士"
    display_en = "Berserker"
    glyph = "狂"

    # 数值 — FE8 L10 1:1(Berserker L10 expected)
    base_hp = 48
    base_atk = 28
    base_def = 8
    base_mov = 4
    mp_pool = 5

    # Magic stats — physical, low magic vuln
    base_matk = 4
    base_mdef = 5

    default_skills = []
    attack_range = 1
    min_attack_range = 0
    can_move_after_action = False  # 持斧不动弹
    ignores_line_of_sight = False
    attack_kind = "physical"

    strong_against = []
