"""Healer — 治疗师 · 后勤支援."""
from app.classes.units.base import BaseUnitClass


class Healer(BaseUnitClass):
    type_id = "healer"
    display_cn = "治疗师"
    display_en = "Healer"
    glyph = "疗"

    base_hp = 40
    base_atk = 5
    base_def = 9
    base_mov = 3
    mp_pool = 5

    default_skills = ["heal", "rally"]
    attack_range = 0   # cannot attack at all
    can_move_after_action = False

    strong_against = []
