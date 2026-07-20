"""Saint - promoted healer with stronger support and serviceable magic."""
from app.classes.units.base import BaseUnitClass


class Saint(BaseUnitClass):
    type_id = "saint"
    display_cn = "圣者"
    display_en = "Saint"
    glyph = "圣"

    base_hp = 48
    base_atk = 7
    base_def = 12
    base_mov = 4
    mp_pool = 8

    base_matk = 16
    base_mdef = 18
    attack_kind = "magic"

    default_skills = ["heal"]
    attack_range = 3
    min_attack_range = 0
    can_move_after_action = False

    strong_against = []
