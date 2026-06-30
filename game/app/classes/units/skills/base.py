"""
Abstract base class for unit skills (active & passive).

Each skill is a single .py file that declares its identity and implements
three hooks:  can_use, describe, execute.

Passive skills (is_passive=True) are auto-triggered by the combat engine
and should override `modify_attack_range` / `modify_damage` etc. instead
of `execute`.

To add a new skill:
  1. Create `game/app/classes/units/skills/backstab.py`
  2. Subclass `BaseSkill`, fill all attributes + hooks
  3. The registry auto-discovers it.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models import Unit


# ── Result types ──────────────────────────────────────────

@dataclass
class SkillContext:
    """Snapshot passed to can_use / describe / execute so skills don't
    need to re-query the DB."""
    user: Unit
    target: Optional[Unit] = None
    terrain_bonus: int = 0           # defender's tile def bonus (attack skills)
    ally_units: List[Unit] = None    # for heal / aoe skills
    enemy_units: List[Unit] = None

    def __post_init__(self):
        if self.ally_units is None:
            self.ally_units = []
        if self.enemy_units is None:
            self.enemy_units = []


@dataclass
class SkillResult:
    """What the engine writes back to the API response."""
    ok: bool = True
    description: str = ""
    restored_hp: int = 0
    affected_units: List[int] = None

    def __post_init__(self):
        if self.affected_units is None:
            self.affected_units = []


# ── Base class ────────────────────────────────────────────

class BaseSkill(ABC):

    # ── Identity ───────────────────────────────────────────
    skill_id: ClassVar[str]               # "heal"
    display_cn: ClassVar[str]             # "治愈"
    display_en: ClassVar[str] = ""        # "Heal"
    is_passive: ClassVar[bool] = False    # True = auto-triggered, no action cost
    default_users: ClassVar[List[str]]    # ["healer"] — which classes start with it

    # ── Hooks ──────────────────────────────────────────────

    def can_use(self, ctx: SkillContext) -> bool:
        """Override to add conditions (cooldown, range, HP threshold, etc.)."""
        return True

    def describe(self, ctx: SkillContext) -> str:
        """Short description shown in legal-actions list."""
        return self.display_cn

    async def execute(
        self,
        session: AsyncSession,
        ctx: SkillContext,
        **kwargs: Any,
    ) -> SkillResult:
        """Perform the skill.  Return a SkillResult to feed back to the client."""
        return SkillResult()

    # ── Passive hooks (override if is_passive) ─────────────

    def modify_attack_range(self, base_range: int, user: Unit) -> int:
        """Called during range calculation.  Return adjusted range."""
        return base_range

    def modify_attack_damage(
        self,
        base_damage: int,
        attacker: Unit,
        defender: Unit,
        _terrain_bonus: int,  # noqa: ARG002 — hook contract, reserved for future terrain-aware skills
    ) -> Dict[str, Any]:
        """Called during damage calculation.  Return {'damage': int, 'hits': int, ...}."""
        return {"damage": base_damage, "hits": 1}

    def modify_mp_after_action(self, mp: int, user: Unit) -> int:
        """Called after an action to adjust remaining MP."""
        return mp
