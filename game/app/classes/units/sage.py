"""Sage - promoted warlock with deeper MP and stronger magic output."""
from app.classes.units.base import BaseUnitClass


class Sage(BaseUnitClass):
    type_id = "sage"
    display_cn = "贤者"
    display_en = "Sage"
    glyph = "贤"

    base_hp = 54
    base_atk = 11
    base_def = 13
    base_mov = 4
    mp_pool = 10

    base_matk = 30
    base_mdef = 18
    attack_kind = "magic"

    default_skills = ["arcane_strike"]
    attack_range = 3
    min_attack_range = 0
    can_move_after_action = False

    strong_against = []
