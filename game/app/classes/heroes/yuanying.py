"""
Hero: 鸢影 (Yuanying) — 沉默的暗影术士

base class: warlock(魔法输出 + 中等 HP)
CO 设计:沉默领域 5×5

Power 行为(用户需求):
  1. 指定区域中心,5×5 方形(中心 ±2)
  2. 区域内所有**非同 team 的魔法单位**(attack_kind == "magic")
  3. 这些单位**无法攻击 + 无法反击**,持续 1 个大回合(下次自己的回合开始时解除)

实现进度:
  - 基础注册 (本文件):已就绪,数据形状 / passive / power 字段固化
  - 沉默状态持久化层 (后续 commit):在 attack / counter-attack 路径检查 is_silenced,
    turn_start 时清空标记,silence 区域选取逻辑在 routes/commanders.py 触发

stat overrides(基于 warlock base: HP=45, ATK=8, DEF=10, MATK=22, MDEF=12, MOV=5, MP=5):

    warlock (base)   yuanying (override)   delta
    --------------   ------------------   -----
    HP  45            48                   +3  (略耐打)
    ATK 8             9                    +1  (微)
    DEF 10            11                   +1
    MATK 22           28                   +6  (核心:沉默依赖持续施法)
    MDEF 12           14                   +2
    MOV 5             -- (inherit 5)       --  (warlock 5,2026-08-09 平衡)
    MP  5             -- (inherit 5)       --  (MOV/MP 合并后 == mov)
"""
from dataclasses import dataclass

from app.commanders import CommanderPassive, CommanderPower
from app.classes.heroes.base import BaseHero


@dataclass(frozen=True)
class YuanyingCommanderPassive(CommanderPassive):
    matk_pct: float
    range_delta: int


@dataclass(frozen=True)
class YuanyingCommanderPower(CommanderPower):
    """沉默领域:5×5 范围内的非同 team 魔法单位,1 大回合无法攻击/反击。

    silence_radius=2 → 5×5 方形区域(中心 ±2)
    silence_duration_turns=1 → 持续 1 个大回合(下次自己的回合开始时解除)
    """
    silence_radius: int
    silence_duration_turns: int


class Yuanying(BaseHero):
    hero_id = "yuanying"
    display_cn = "鸢影"
    base_class_id = "warlock"

    # ── Stat overrides (designer-tuned deltas) ────────────────
    hp_override = 48
    atk_override = 9
    def_override = 11
    matk_override = 28
    mdef_override = 14
    # mov_override / mp_pool_override: 继承 warlock (5 / 5,见模块 docstring)

    # ── Art assets (served from web/assets/heroes/) ───────────
    # NOTE: sprite_path / crest_path 资产**尚未生成**;游戏启动时若资产缺失会
    # 用默认占位。生成后把文件名填入即可,无需改其他代码。
    sprite_path = "yuanying.png"             # 待生成(棋盘上的格子精灵)
    portrait_path = "portrait_yuanying.png"   # 已存在(2026-07-31 入库,1.8MB)
    crest_path = "crest_yuanying.png"         # 待生成(对话头像)

    # ── Skill bindings ─────────────────────────────────────────
    # 暂留空 — 沉默领域本身由 commander_power 触发,不需要 unit-level skill。
    # 后续若有"小沉默"(单体的瞬时沉默),可加 active_skills = ["silence"]。
    active_skills: list[str] = []
    passive_skills: list[str] = []

    is_commander = True

    # ── Passive: 全队魔法加 10% + 射程 +1 ─────────────────────
    commander_passive = YuanyingCommanderPassive(
        id="yuanying_passive",
        matk_pct=0.10,
        range_delta=1,
    )

    # ── Power: 沉默领域 5×5 + 全队 MATK +20% ──────────────────
    # threshold = 16(中间值,介于 anna=14 与 yun=18 之间)
    # cost = 6(沿用 co-power 全局默认)
    commander_power = YuanyingCommanderPower(
        id="yuanying_power",
        matk_pct=0.20,            # 同时给全队 +20% 魔攻(配合沉默提升总输出)
        silence_radius=2,         # 5×5 方形(中心 ±2)
        silence_duration_turns=1, # 1 个大回合
    )
    power_threshold = 16

    # ── Dialog binding ─────────────────────────────────────────
    dialogue_name = "鸢影"

    # Personal growth modifier on top of the base class's growth rates.
    # See RolledGrowthPolicy and spec §8.2.
    personal_growth_modifier = {'hp': 5, 'matk': 10, 'mdef': 5}
