"""
Hero: 云 (Yun) — the player protagonist of the default mainline.

Derived from the warlock base class (see ``app.classes.units.warlock``)
via the hero registry (NOT Python inheritance — see the spec at
``docs/superpowers/specs/2026-07-09-hero-system.md`` §3).

云 is framed in chapter 1 as a veteran field-mage: a warlock with
slightly sturdier physical defense and a strong MATK, who out-marches
ordinary casters.  All numbers are designer-tuned deltas over the
stock warlock; unlisted fields inherit from ``Warlock`` verbatim.

    warlock (base)   yun (override)   delta
    --------------   --------------   -----
    HP  45            50              +5  (more durable)
    ATK  8            20              +12 (designer plot boost)
    DEF  10           11              +1
    MATK 22           27              +5
    MDEF 12           -- (inherit)    --
    MOV  5            5               0   (2026-08-10: 全部英雄统一 mov=5)
    MP   5            -- (inherit)    --  (5 MP, MOV/MP 合并后 == mov)

Art notes for the designer:
    * ``heroes/yun.png``        — grid sprite (initially the swordsman
      classic sprite, swapped for a custom portrait during the art pass).
    * ``heroes/portrait_yun.png`` — full dialog portrait.
    * ``heroes/crest_yun.png``  — circular dialog avatar.
"""
from dataclasses import dataclass

from app.commanders import CommanderPassive, CommanderPower
from app.classes.heroes.base import BaseHero


@dataclass(frozen=True)
class YunCommanderPassive(CommanderPassive):
    atk_pct: float
    range_delta: int


@dataclass(frozen=True)
class YunCommanderPower(CommanderPower):
    atk_pct: float
    heal_pct: float


class Yun(BaseHero):
    hero_id = "yun"
    display_cn = "云"
    # Inherits every combat framework stat from the warlock.
    base_class_id = "warlock"

    # ── Stat overrides (designer-tuned deltas) ────────────────
    hp_override = 50           # warlock 45 → 50   (more durable)
    atk_override = 20          # warlock  8 → 20   (plot boost)
    def_override = 11          # warlock 10 → 11
    matk_override = 27         # warlock 22 → 27   (veteran caster)
    # mdef_override = -- (inherit 12)
    mov_override = 5           # warlock 5 → 5 (2026-08-10: all heroes uniform mov=5)
    # mp_pool_override = -- (inherit 8)

    # ── Art assets (served from web/assets/heroes/) ───────────
    sprite_path = "yun.png"
    portrait_path = "portrait_yun.png"
    crest_path = "crest_yun.png"

    # ── Skill bindings ─────────────────────────────────────────
    # yun's signature move — a single-target magic attack that
    # scales off MATK.  See
    # ``app/classes/units/skills/arcane_strike.py`` for the damage
    # formula.  Passive slot is reserved for a future "veteran"
    # hook (e.g. +1 ATK on battle start).
    active_skills = ["arcane_strike"]
    passive_skills = []
    is_commander = True
    commander_passive = YunCommanderPassive(id="yun_passive", atk_pct=0.10, range_delta=1)
    commander_power = YunCommanderPower(id="yun_power", atk_pct=0.30, heal_pct=0.50)
    power_threshold = 18

    # ── Dialog binding ─────────────────────────────────────────
    # Scene files reference the speaker as "云" (display_cn), so
    # the dialog system can resolve it without any extra wiring.
    dialogue_name = "云"

    # Independent character growth rates. Heroes do not inherit class
    # growth rates; this table is the growth source of truth.
    character_growth_rates = {
        'hp': 80, 'atk': 35, 'def': 35, 'matk': 90, 'mdef': 50, 'mov': 0,
    }
    # Legacy fallback kept for old fixtures; production policy uses
    # character_growth_rates above.
    personal_growth_modifier = {'matk': 20, 'mdef': 5}
