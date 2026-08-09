"""Hero: Youko - 洋子, the bard heroine."""
from app.classes.heroes.base import BaseHero


class Youko(BaseHero):
    hero_id = "youko"
    display_cn = "洋子"
    base_class_id = "bard"

    hp_override = 40
    def_override = 8
    matk_override = 12
    mdef_override = 15
    mov_override = 5

    sprite_path = "youko.png"
    portrait_path = "portrait_youko.png"
    crest_path = "crest_youko.png"

    active_skills = ["sing"]
    passive_skills = []

    dialogue_name = "洋子"

    # Personal growth modifier on top of the base class's growth rates.
    # See RolledGrowthPolicy and spec §8.2.
    personal_growth_modifier = {'matk': 10, 'mdef': 5}
