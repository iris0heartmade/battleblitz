"""Paladin - promoted knight with improved mobility and durability."""
from app.classes.units.base import BaseUnitClass


class Paladin(BaseUnitClass):
    type_id = "paladin"
    display_cn = "圣骑士"
    display_en = "Paladin"
    glyph = "圣"

    base_hp = 64
    base_atk = 28
    base_def = 12
    base_mov = 6
    mp_pool = 9

    base_matk = 5
    base_mdef = 7
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["archer"]
