"""Dragon Rider - an original wyvern-mounted mobile melee class."""

from app.classes.units.base import BaseUnitClass


class DragonRider(BaseUnitClass):
    """Tier-1 flying melee class with mobility as its primary advantage."""

    type_id = "dragon_rider"
    display_cn = "飞龙骑士"
    display_en = "Dragon Rider"
    glyph = "龙"

    # Kept below promoted cavalry bodies; flying terrain access is the hook.
    base_hp = 42
    base_atk = 16
    base_def = 7
    base_mov = 7

    base_matk = 3
    base_mdef = 6
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["archer"]

    # Data only: movement.py applies these rules for player, AI, and UI.
    # Flying units may cross walls/gates, but they must not stop on them.
    terrain_movement = {
        "mountain": {"can_traverse": True, "can_end_on": True, "cost_override_x2": 2},
        "snow_peak": {"can_traverse": True, "can_end_on": True, "cost_override_x2": 2},
        "river": {"can_traverse": True, "can_end_on": True, "cost_override_x2": 2},
        "castle_wall": {"can_traverse": True, "can_end_on": False, "cost_override_x2": 2},
        "gate": {"can_traverse": True, "can_end_on": False, "cost_override_x2": 2},
    }

    # Per-stat growth rates (%).  See app.progression.policies.RolledGrowthPolicy.
    class_growth_rates = {'hp': 80, 'atk': 50, 'def': 25, 'matk': 5, 'mdef': 15, 'mov': 5}
