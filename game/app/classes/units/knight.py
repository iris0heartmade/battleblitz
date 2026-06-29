"""Knight — 骑士 · 高机动双连击."""
from app.classes.units.base import BaseUnitClass


class Knight(BaseUnitClass):
    type_id = "knight"
    display_cn = "骑士"
    display_en = "Knight"
    glyph = "骑"

    base_hp = 55
    base_atk = 22
    base_def = 8
    base_mov = 5
    mp_pool = 8

    # Magic stats — physical unit, low magic offense/defense.
    base_matk = 4
    base_mdef = 4
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["archer"]
