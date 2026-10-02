"""Bard - 吟游诗人, a hero-only T1 support class."""
from app.classes.units.base import BaseUnitClass


class Bard(BaseUnitClass):
    type_id = "bard"
    display_cn = "吟游诗人"
    display_en = "Bard"
    glyph = "诗"

    base_hp = 36
    base_atk = 4
    base_def = 7
    base_mov = 6

    base_matk = 12
    base_mdef = 13
    attack_kind = "magic"

    default_skills = ["sing"]
    attack_range = 1
    min_attack_range = 0
    can_move_after_action = False

    strong_against = []

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 55, 'atk': 35, 'def': 35, 'matk': 45, 'mdef': 35, 'mov': 0}
