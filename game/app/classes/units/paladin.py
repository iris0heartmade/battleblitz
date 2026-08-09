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

    base_matk = 5
    base_mdef = 7
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["archer"]

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 85, 'atk': 50, 'def': 40, 'matk': 15, 'mdef': 30, 'mov': 8}
