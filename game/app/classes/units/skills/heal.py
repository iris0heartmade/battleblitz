"""Heal — 治愈 · 相邻友军 +20 HP."""
from app.classes.units.skills.base import BaseSkill, SkillContext, SkillResult


class HealSkill(BaseSkill):
    skill_id = "heal"
    display_cn = "治愈"
    display_en = "Heal"
    is_passive = False
    default_users = ["healer"]

    HEAL_AMOUNT = 20

    def can_use(self, ctx: SkillContext) -> bool:
        if ctx.target is None:
            return False
        if ctx.target.player_id != ctx.user.player_id:
            return False
        if ctx.target.hp >= ctx.target.max_hp:
            return False
        return max(abs(ctx.user.x - ctx.target.x), abs(ctx.user.y - ctx.target.y)) == 1

    def describe(self, ctx: SkillContext) -> str:
        deficit = min(self.HEAL_AMOUNT, ctx.target.max_hp - ctx.target.hp) if ctx.target else self.HEAL_AMOUNT
        return f"💚+{deficit} {ctx.target.name[:4] if ctx.target else '?'}"

    async def execute(self, session, ctx: SkillContext, **kwargs) -> SkillResult:
        target = ctx.target
        deficit = target.max_hp - target.hp
        restored = min(self.HEAL_AMOUNT, deficit)
        target.hp += restored
        ctx.user.has_acted = True
        ctx.user.mp = 0
        return SkillResult(
            ok=True,
            description=f"{ctx.user.name} 治愈 {target.name} +{restored}HP",
            restored_hp=restored,
            affected_units=[target.id],
        )
