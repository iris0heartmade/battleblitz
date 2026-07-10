"""
Hero: Anna - a healer heroine for the default mainline.

Anna uses the healer base class and keeps the existing ``heal`` skill.
Her stat overrides make her a sturdier named support unit without adding
new combat rules.
"""
from dataclasses import dataclass

from app.commanders import CommanderPassive, CommanderPower
from app.classes.heroes.base import BaseHero


@dataclass(frozen=True)
class AnnaCommanderPassive(CommanderPassive):
    def_pct: float
    mdef_pct: float


@dataclass(frozen=True)
class AnnaCommanderPower(CommanderPower):
    def_pct: float
    mdef_pct: float
    heal_pct: float


class Anna(BaseHero):
    hero_id = "anna"
    display_cn = "安娜"
    base_class_id = "healer"

    hp_override = 46
    def_override = 10
    matk_override = 12
    mdef_override = 14
    mov_override = 3
    mp_pool_override = 6

    sprite_path = "anna.png"
    portrait_path = "portrait_anna.png"
    crest_path = "crest_anna.png"

    active_skills = ["heal"]
    passive_skills = []
    is_commander = True
    commander_passive = AnnaCommanderPassive(id="anna_passive", def_pct=0.15, mdef_pct=0.10)
    commander_power = AnnaCommanderPower(id="anna_power", def_pct=0.30, mdef_pct=0.30, heal_pct=0.80)
    power_threshold = 18

    dialogue_name = "安娜"
