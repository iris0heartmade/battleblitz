"""Hero: Baiyu - rebellious dragon princess and star-rite caster."""
from app.classes.heroes.base import BaseHero


class Baiyu(BaseHero):
    hero_id = "baiyu"
    display_cn = "白予"
    base_class_id = "sage"

    hp_override = 50
    atk_override = 9
    def_override = 9
    matk_override = 36
    mdef_override = 20
    mov_override = 5

    sprite_path = "baiyu.png"
    portrait_path = "portrait_baiyu.png"
    crest_path = "crest_baiyu.png"

    active_skills = ["arcane_strike"]
    passive_skills = []

    dialogue_name = "白予"

    character_growth_rates = {
        "hp": 65,
        "atk": 35,
        "def": 35,
        "matk": 100,
        "mdef": 75,
        "mov": 0,
    }
    personal_growth_modifier = {"matk": 20, "mdef": 10}
