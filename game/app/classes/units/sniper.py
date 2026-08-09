"""Sniper - promoted archer with longer reach and steadier output."""
from app.classes.units.base import BaseUnitClass


class Sniper(BaseUnitClass):
    type_id = "sniper"
    display_cn = "狙击手"
    display_en = "Sniper"
    glyph = "狙"

    base_hp = 44
    base_atk = 26
    base_def = 10
    base_mov = 4

    base_matk = 5
    base_mdef = 7
    attack_kind = "physical"

    default_skills = ["snipe"]
    attack_range = 5
    min_attack_range = 2
    can_move_after_action = True
    ignores_line_of_sight = True

    strong_against = ["warlock"]

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 70, 'atk': 60, 'def': 30, 'matk': 15, 'mdef': 25, 'mov': 5}
