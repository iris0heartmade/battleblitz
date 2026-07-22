"""Lancer — 轻装枪骑(Phase 2 §2 generic T1).

新增 T1 兵种。数值按 FE8 L10 expected 1:1 校准(Cavalier F L10):
  base_hp 27 / base_atk 8 / base_def 7 / base_mov 5 / 攻击射程 1
  移动力高 / Spd 高 — 轻骑兵定位,介于 Knight(重装)和 Paladin(精装)
  之间,适合前锋穿插。
"""
from app.classes.units.base import BaseUnitClass


class Lancer(BaseUnitClass):
    type_id = "lancer"
    display_cn = "枪兵"
    display_en = "Lancer"
    glyph = "枪"

    # 数值 — FE8 L10 1:1(Cavalier F L10 expected)
    base_hp = 27
    base_atk = 8
    base_def = 7
    base_mov = 5
    mp_pool = 6

    # Magic stats — physical unit, modest magic defense
    base_matk = 4
    base_mdef = 5

    default_skills = []
    attack_range = 1
    min_attack_range = 0
    can_move_after_action = True  # 轻骑兵 — 打了就跑
    ignores_line_of_sight = False
    attack_kind = "physical"

    strong_against = ["knight"]  # 枪克重装
