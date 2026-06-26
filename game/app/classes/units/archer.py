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
    mp_pool = 5

    default_skills = ["snipe"]
    attack_range = 2
    min_attack_range = 1   # Fire-Emblem style: must keep distance, no melee
    can_move_after_action = True

    strong_against = []   # reserved for future "mage"
