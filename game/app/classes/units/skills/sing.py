"""Sing - 吟诗: refresh an adjacent allied unit that already acted."""
from __future__ import annotations

from app.classes.units import get_or_none as get_unit_class
from app.classes.units.skills.base import BaseSkill, SkillContext, SkillResult


class SingSkill(BaseSkill):
    skill_id = "sing"
    display_cn = "吟诗"
    display_en = "Sing"
    is_passive = False
    default_users = ["bard"]

    def can_use(self, ctx: SkillContext) -> bool:
        if ctx.target is None:
            return False
        if ctx.target is ctx.user:
            return False
        if ctx.target.id is not None and ctx.target.id == ctx.user.id:
            return False
        if ctx.target.player_id != ctx.user.player_id:
            return False
        if ctx.target.hp <= 0:
            return False
        if not (ctx.target.has_acted or ctx.target.has_moved):
            return False
        return max(abs(ctx.user.x - ctx.target.x), abs(ctx.user.y - ctx.target.y)) == 1

    def describe(self, ctx: SkillContext) -> str:
        if ctx.target is None:
            return self.display_cn
        return f"{self.display_cn} -> {ctx.target.name[:4]}"

    async def execute(self, session, ctx: SkillContext, **kwargs) -> SkillResult:
        target = ctx.target
        target.has_acted = False
        target.has_moved = False
        profile = get_unit_class(target.unit_type)
        if profile is not None:
            target.mp = profile.base_mov
            target.mov = profile.base_mov
        ctx.user.has_acted = True
        ctx.user.mp = 0
        return SkillResult(
            ok=True,
            description=f"{ctx.user.name} 吟诗鼓舞 {target.name}, 使其可以再次行动",
            affected_units=[target.id],
        )
