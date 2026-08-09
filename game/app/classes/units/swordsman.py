"""Swordsman — 剑士 · 均衡近战."""
from app.classes.units.base import BaseUnitClass


class Swordsman(BaseUnitClass):
    type_id = "swordsman"
    display_cn = "剑士"
    display_en = "Swordsman"
    glyph = "剑"

    base_hp = 45
    base_atk = 18
    base_def = 12
    base_mov = 5

    # Magic stats — physical unit, low magic offense/defense.
    base_matk = 4
    base_mdef = 4
    attack_kind = "physical"

    default_skills = []
    attack_range = 1
    can_move_after_action = False

    strong_against = ["knight"]

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 85, 'atk': 45, 'def': 30, 'matk': 5, 'mdef': 20, 'mov': 0}
