"""Archer — 弓箭手 · 远程狙击."""
from app.classes.units.base import BaseUnitClass


class Archer(BaseUnitClass):
    type_id = "archer"
    display_cn = "弓箭手"
    display_en = "Archer"
    glyph = "弓"

    base_hp = 35
    base_atk = 20
    base_def = 6
    base_mov = 3

    # Magic stats — physical unit, low magic offense/defense.
    base_matk = 4
    base_mdef = 4
    attack_kind = "physical"

    default_skills = ["snipe"]
    # P2.4 polish — was 2, with min 1 (archer could only hit at
    # exactly distance 2). Way too short for 15x15+ maps. Now
    # 1–4 with min 0 so the archer can both kite and melee.
    attack_range = 4
    min_attack_range = 2
    can_move_after_action = True
    ignores_line_of_sight = True   # 狙击：无视障碍

    strong_against = []   # reserved for future matchup against Warlock

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 65, 'atk': 50, 'def': 20, 'matk': 5, 'mdef': 15, 'mov': 0}
