"""Hero: Lin Yilan - no-magic chief tactician."""
from app.classes.heroes.base import BaseHero


class LinYilan(BaseHero):
    hero_id = "lin_yilan"
    display_cn = "林依澜"
    base_class_id = "bard"

    hp_override = 44
    atk_override = 8
    def_override = 10
    matk_override = 6
    mdef_override = 16
    mov_override = 5

    sprite_path = "lin_yilan.png"
    portrait_path = "portrait_lin_yilan.png"
    crest_path = "crest_lin_yilan.png"

    active_skills = ["sing"]
    passive_skills = ["terrain_tactician"]

    dialogue_name = "林依澜"

    character_growth_rates = {
        "hp": 75,
        "atk": 35,
        "def": 45,
        "matk": 35,
        "mdef": 70,
        "mov": 0,
    }
    personal_growth_modifier = {"def": 5, "mdef": 10}
