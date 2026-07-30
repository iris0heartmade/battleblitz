"""Falcon Knight — 天马骑士(Phase 2 §2 generic T2)。

Pegasus Knight 转职。数值按 FE8 L10 expected 1:1 校准(Falcon Knight L10):
  base_hp 25 / base_atk 9 / base_def 6 / base_mov 6 / 攻击射程 1
  移动力极高(Mov 6 = 全场最快之一)+ 偏 Def/Res + 命中追袭
  天马系族,飞越山岭无 + 1 移动 buff。
"""
from app.classes.units.base import BaseUnitClass


class FalconKnight(BaseUnitClass):
    type_id = "falcon_knight"
    display_cn = "天马骑士"
    display_en = "Falcon Knight"
    glyph = "鹰"

    # 数值 — FE8 L10 1:1(Falcon Knight L10 expected)
    base_hp = 25
    base_atk = 9
    base_def = 6
    base_mov = 6
    mp_pool = 6

    # Magic stats — Pegasi 略偏魔法抗性
    base_matk = 4
    base_mdef = 8

    default_skills = []
    attack_range = 1
    min_attack_range = 0
    can_move_after_action = True  # 飞行 — 打了就跑
    ignores_line_of_sight = False
    attack_kind = "physical"

    strong_against = []  # 暂无克制关系
