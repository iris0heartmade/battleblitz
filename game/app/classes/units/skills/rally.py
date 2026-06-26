"""Rally — 集结 · 相邻友军 +10% ATK."""
from app.classes.units.skills.base import BaseSkill, SkillContext, SkillResult
from app.utils import chebyshev


class RallySkill(BaseSkill):
    skill_id = "rally"
    display_cn = "集结"
    display_en = "Rally"
    is_passive = False
    default_users = ["healer"]

    def can_use(self, ctx: SkillContext) -> bool:
        return any(
            a.id != ctx.user.id and a.hp > 0
            and chebyshev((ctx.user.x, ctx.user.y), (a.x, a.y)) == 1
            for a in (ctx.ally_units or [])
        )

    def describe(self, ctx: SkillContext) -> str:
        return "📯+10%攻"

    async def execute(self, session, ctx: SkillContext, **kwargs) -> SkillResult:
        affected = []
        for a in (ctx.ally_units or []):
            if a.hp <= 0:
                continue
            if chebyshev((ctx.user.x, ctx.user.y), (a.x, a.y)) == 1:
                a.atk = int(round(a.atk * 1.10))
                affected.append(a.id)
        ctx.user.has_acted = True
        ctx.user.mp = 0
        return SkillResult(
            ok=True,
            description=f"{ctx.user.name} 集结 {len(affected)} 名友军 +10%ATK",
            affected_units=affected,
        )
