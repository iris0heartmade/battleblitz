"""Healer — 治疗师 · 魔法后场支援.

Now classified as a magic-type unit (attack_kind="magic") with
Manhattan 1–2 attack range. Lower MATK than Warlock because it's
not a primary attacker, but matching MDEF so it can survive the
backline against other magic threats.

The `rally` skill was removed in the 2026-06-30 magic-combat refactor —
only `heal` remains.
"""
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

    # Magic stats — magic-type backline support. MATK lower than Warlock
    # (it's not a primary attacker), MDEF matches Warlock so it doesn't
    # get one-shotted by other magic units.
    base_matk = 8
    base_mdef = 12
    attack_kind = "magic"

    default_skills = ["heal"]
    attack_range = 2        # Manhattan 1–2 (sword + archer combined)
    min_attack_range = 0    # can attack adjacent targets
    can_move_after_action = False

    strong_against = []