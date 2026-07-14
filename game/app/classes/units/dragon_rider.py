"""Dragon Rider - an original wyvern-mounted mobile melee class."""

from app.classes.units.base import BaseUnitClass


class DragonRider(BaseUnitClass):
    """Fast cavalry-equivalent class for future terrain-mobility profiles."""

    type_id = "dragon_rider"
    display_cn = "飞龙骑士"
    display_en = "Dragon Rider"
    glyph = "龙"

    # More durable than a knight, but with deliberately lower attack so the
    # future flying terrain profile is the class's primary advantage.
    base_hp = 60
    base_atk = 20
    base_def = 10
    base_mov = 5
    mp_pool = 8

    base_matk = 3
    base_mdef = 6
    attack_kind = "physical"

    default_skills = ["double_strike"]
    attack_range = 1
    can_move_after_action = True

    strong_against = ["archer"]
