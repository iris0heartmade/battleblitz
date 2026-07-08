"""Arcane Strike — 奥术冲击 · 单体魔法攻击.

Active skill: deals magic damage to a single target within Manhattan
distance 1–2.  Damage formula follows the spec from
``docs/superpowers/specs/2026-07-09-hero-system.md``:

    damage = max(1, attacker.matk * 1.2 - defender.mdef)

V1 has no default class users — this skill is currently exclusive to
heroes that declare it in their ``active_skills`` list (e.g. yun
the warlock protagonist).  The combat engine fires it through the
standard ``POST /skill`` path; see ``app.routes.actions``.
"""
from __future__ import annotations

from app.classes.units.skills.base import BaseSkill, SkillContext, SkillResult


class ArcaneStrikeSkill(BaseSkill):
    # Magic damage multiplier applied to the caster's MATK.  Tuned
    # slightly above the standard MATK-vs-MDEF matchup so the skill
    # feels like a "signature move" rather than a plain attack.
    MATK_MULTIPLIER = 1.2
    # Manhattan distance the skill can reach (1 = adjacent, 2 = warlock
    # reach).  Matches the warlock's attack_range so casting feels
    # consistent with the base class's combat footprint.
    CAST_RANGE = 2
    # Floor damage so even tanky targets tick down at least 1 HP.  The
    # same floor appears in the standard damage formula; keeping it
    # here makes the skill non-useless against high-MDEF enemies.
    MIN_DAMAGE = 1
    skill_id = "arcane_strike"
    display_cn = "奥术冲击"
    display_en = "Arcane Strike"
    is_passive = False
    # No class starts with this skill by default.  Heroes that want
    # it must declare it in their ``active_skills`` list — the
    # classic example is yun, the chapter-1 warlock protagonist.
    default_users: list[str] = []

    def can_use(self, ctx: SkillContext) -> bool:
        # No target = can't use.
        if ctx.target is None:
            return False
        # Can't target allies — the skill is hostile.
        if ctx.target.player_id == ctx.user.player_id:
            return False
        # Range check (Manhattan).
        dist = abs(ctx.user.x - ctx.target.x) + abs(ctx.user.y - ctx.target.y)
        return 1 <= dist <= self.CAST_RANGE

    def describe(self, ctx: SkillContext) -> str:
        if ctx.target is None:
            return f"🔮{self.display_cn}"
        # Show the would-be damage so the player can decide.
        preview = max(
            self.MIN_DAMAGE,
            int(ctx.user.matk * self.MATK_MULTIPLIER) - ctx.target.mdef,
        )
        return f"🔮{self.display_cn} → {ctx.target.name[:4]} -{preview}HP"

    async def execute(self, session, ctx: SkillContext, **kwargs) -> SkillResult:
        target = ctx.target
        # Magic damage formula — see header docstring.
        raw = int(ctx.user.matk * self.MATK_MULTIPLIER) - target.mdef
        damage = max(self.MIN_DAMAGE, raw)
        target.hp = max(0, target.hp - damage)
        # Mirror the heal skill's post-action bookkeeping: the user
        # has consumed their turn and emptied their MP pool.  The
        # engine resets MP at the start of the next turn.
        ctx.user.has_acted = True
        ctx.user.mp = 0
        return SkillResult(
            ok=True,
            description=(
                f"{ctx.user.name} 施放 {self.display_cn}, "
                f"对 {target.name} 造成 {damage} 点魔法伤害"
            ),
            affected_units=[target.id],
        )
