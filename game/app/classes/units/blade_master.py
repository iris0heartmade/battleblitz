"""Blade Master - promoted swordsman with stronger duel presence."""
from app.classes.units.base import BaseUnitClass


class BladeMaster(BaseUnitClass):
    type_id = "blade_master"
    display_cn = "剑圣"
    display_en = "Blade Master"
    glyph = "圣"

    base_hp = 54
    base_atk = 25
    base_def = 15
    base_mov = 4
    mp_pool = 6

    base_matk = 6
    base_mdef = 8
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["knight"]
