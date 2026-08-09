"""Warlock — 术士 · 魔法近战（剑士 + 弓手射程的魔法版）.

Magic-type melee/ranged hybrid (Manhattan 1–2 range). Mirrors the
Swordsman in role and HP/MOV, but its damage type is magic:

  - High MATK (22) and MDEF (12) — primary magic offense/defense.
  - Low ATK (8) and DEF (10) — can't fall back on physical damage and
    is vulnerable to physical attackers.
  - The damage formula's natural split (attack_kind picks ATK vs
    MATK on the attacker, and the defender always blocks with the
    matching stat) means Swordsman→Warlock and Warlock→Swordsman
    are both high-damage cross-archetype matchups — the "natural
    counter" the user wanted.

No skills yet (matching Swordsman's `[]`). `strong_against` is left
empty because the natural counter via stat layout is sufficient.

As of 2026-08-02, warlocks default to `["poison_burst"]` (Poison Burst,
2 MP / Manhattan 1–2 / 3-turn poison).  `arcane_strike` remains a
hero-only skill (declared in hero `active_skills`).
"""
from app.classes.units.base import BaseUnitClass


class Warlock(BaseUnitClass):
    type_id = "warlock"
    display_cn = "术士"
    display_en = "Warlock"
    glyph = "咒"

    base_hp = 45
    base_atk = 8          # low — magic damage comes from MATK
    base_def = 10         # slightly lower than Swordsman
    base_mov = 8

    # Magic stats — magic-type attacker.
    base_matk = 22
    base_mdef = 12
    attack_kind = "magic"

    default_skills = ["poison_burst"]
    attack_range = 2        # Manhattan 1–2 (sword + archer combined)
    min_attack_range = 0    # can attack adjacent targets
    can_move_after_action = False

    strong_against = []     # natural counter via stats

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 60, 'atk': 5, 'def': 15, 'matk': 55, 'mdef': 25, 'mov': 0}
