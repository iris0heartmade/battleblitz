"""Snipe — 狙击 · 被动 +1 攻击射程."""
from app.classes.units.skills.base import BaseSkill


class SnipeSkill(BaseSkill):
    skill_id = "snipe"
    display_cn = "狙击"
    display_en = "Snipe"
    is_passive = True
    default_users = ["archer"]

    def modify_attack_range(self, base_range: int, user) -> int:
        return base_range + 1
