"""Poison Burst — 剧毒迸发 · 单体施毒.

Active skill: applies a 3-turn poison status effect to a single enemy
within Manhattan distance 1–2. Costs 2 MP (vs. the standard ``mp = 0``
post-action convention) — other skills still empty the MP pool, but
poison_burst is a partial-MP drain so warlocks can chain it with
arcane_strike if MP allows.

Mechanics:
- Drain: ``ctx.user.mp -= MP_COST`` (does not reset to 0).
- Hook: ``status_effects`` → ``poison`` for 3 large turns (handled by
  the universal status framework; ``add_effect`` is idempotent).
- This is the first skill in the project that writes to
  ``Unit.status_effects`` from a SkillContext — the door is now open
  for ``silence_burst``, ``blind``, ``paralyze`` etc. to follow.

Default users: ``warlock`` (their magic career + 8 MP pool + range 2
fits the skill footprint). Other unit classes must declare
``poison_burst`` explicitly via heroes' ``active_skills``.
"""
from __future__ import annotations

from app.classes.units.skills.base import BaseSkill, SkillContext, SkillResult


class PoisonBurstSkill(BaseSkill):
    MP_COST = 2
    CAST_RANGE = 2          # Manhattan 1–2 (matches warlock attack_range)
    POISON_TURNS = 3        # default_remaining for poison EFFECT_DEFS already 3, but pinned here
    skill_id = "poison_burst"
    display_cn = "剧毒迸发"
    display_en = "Poison Burst"
    is_passive = False
    default_users: list[str] = ["warlock"]

    def can_use(self, ctx: SkillContext) -> bool:
        if ctx.target is None:
            return False
        # Hostile only.
        if ctx.target.player_id == ctx.user.player_id:
            return False
        # Skip dead targets.
        if getattr(ctx.target, "hp", 0) <= 0:
            return False
        # Range check (Manhattan).
        dist = abs(ctx.user.x - ctx.target.x) + abs(ctx.user.y - ctx.target.y)
        if not (1 <= dist <= self.CAST_RANGE):
            return False
        # MP check.
        if int(getattr(ctx.user, "mp", 0)) < self.MP_COST:
            return False
        return True

    def describe(self, ctx: SkillContext) -> str:
        if ctx.target is None:
            return f"☠{self.display_cn}"
        return f"☠{self.display_cn} → {ctx.target.name[:4]} 毒{self.POISON_TURNS}回合"

    async def execute(self, session, ctx: SkillContext, **kwargs) -> SkillResult:
        # Late import keeps the skill file import-safe even if status
        # package is half-loaded during a collection edge case.
        from app.status import add_effect

        target = ctx.target
        eff = add_effect(
            target,
            "poison",
            applied_turn=ctx.game_turn_number,
            applied_by=ctx.user.player_id,
            remaining_turns=self.POISON_TURNS,
        )
        # Partial-MP drain — distinct from heal/arcane_strike which
        # empty the MP pool entirely on action.
        ctx.user.mp = max(0, int(ctx.user.mp) - self.MP_COST)
        ctx.user.has_acted = True
        dmg_pct = float(eff.get("params", {}).get("dmg_pct", 0.05))
        return SkillResult(
            ok=True,
            description=(
                f"{ctx.user.name} 施放 {self.display_cn}, "
                f"{target.name} 中毒 {self.POISON_TURNS} 回合 "
                f"({int(dmg_pct * 100)}% HP/回合)"
            ),
            affected_units=[target.id],
        )