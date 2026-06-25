"""Double Strike — 连击 · 被动: 攻击两次, 每次 50% 伤害."""
from app.classes.units.skills.base import BaseSkill


class DoubleStrikeSkill(BaseSkill):
    skill_id = "double_strike"
    display_cn = "连击"
    display_en = "Double Strike"
    is_passive = True
    default_users = ["knight"]

    def modify_attack_damage(self, base_damage: int, attacker, defender, terrain_bonus: int):
        # The combat engine checks this skill's presence and splits damage
        # into two hits; this hook signals "I'm active".
        return {"damage": base_damage, "hits": 2}
