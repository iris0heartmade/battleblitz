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

    # Independent character growth rates. Heroes do not inherit class
    # growth rates; this table is the growth source of truth.
    character_growth_rates = {
        'hp': 75, 'atk': 35, 'def': 35, 'matk': 55, 'mdef': 65, 'mov': 0,
    }
    # Legacy fallback kept for old fixtures; production policy uses
    # character_growth_rates above.
    personal_growth_modifier = {'matk': 10, 'mdef': 5}
