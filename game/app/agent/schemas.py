"""
Pydantic schemas for the LLM agent layer.

Three layers of contracts:
- GameSnapshot:  serialised game state sent to the LLM (fog of war applied)
- LegalAction:   one option the LLM may pick from (pre-validated by engine)
- AgentAction:   the LLM's choice, validated against LegalAction before execution
"""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


# ----------------------------------------------------------------
# Views (what the LLM sees)
# ----------------------------------------------------------------

TerrainZh = Literal["plain", "forest", "mountain", "river", "castle"]
UnitTypeZh = Literal["swordsman", "archer", "knight", "healer"]


class UnitView(BaseModel):
    """One unit as seen by the LLM. Fog-of-war hides stats we don't know."""
    id: int
    type: UnitTypeZh
    name: str = "Unit"
    hp: int = Field(default=0, ge=0, description="Current HP; 0 = dead")
    max_hp: int = Field(default=1, ge=1)
    mp: int = Field(default=0, ge=0, description="Movement points remaining this turn")
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    terrain: TerrainZh = Field(default="plain", description="Terrain of the tile the unit stands on")
    skills: List[str] = Field(default_factory=list)
    morale: int = Field(default=0, ge=0, le=3, description="0..3 stars")
    has_acted: bool = False


class FogUnit(BaseModel):
    """A unit we know exists but can't fully see (position only)."""
    x: int
    y: int


Coord = Tuple[int, int]


class GameSnapshot(BaseModel):
    """The complete state we hand to the LLM."""
    turn: int = Field(ge=1)
    budget_left: int = Field(ge=0, description="Action budget remaining this turn")
    action_count: int = Field(default=0, description="Actions taken so far this turn")

    my_units: List[UnitView]
    visible_enemies: List[UnitView] = Field(default_factory=list)
    fog_enemies: List[FogUnit] = Field(default_factory=list)

    my_castles: List[Coord] = Field(default_factory=list)
    enemy_castles: List[Coord] = Field(default_factory=list)
    unowned_castles: List[Coord] = Field(default_factory=list)

    map_size: int = 15
    map_ascii: str = ""
    map_legend: dict = Field(default_factory=dict)


# ----------------------------------------------------------------
# Legal actions (engine pre-computes)
# ----------------------------------------------------------------

ActionKind = Literal["move", "attack", "skill", "wait", "end_turn"]


class LegalAction(BaseModel):
    """One option the LLM may choose. Pre-validated by the engine."""
    action_id: str = Field(description="Stable id used by the LLM in its reply")
    kind: ActionKind
    unit_id: Optional[int] = None
    params: dict = Field(default_factory=dict)
    description: str = Field(default="", description="Human-readable, e.g. 'Knight 攻击 Swordsman (预计 14 伤害)'")
    dmg_estimate: Optional[int] = Field(default=None, description="For attack/skill only")


# ----------------------------------------------------------------
# Agent output (what the LLM returns)
# ----------------------------------------------------------------

class AgentAction(BaseModel):
    """The LLM's chosen action(s). action_id may be pipe-separated for batch."""
    action_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(default="", description="≤40 Chinese chars, shown to player")

    @model_validator(mode="after")
    def _check_action_id_format(self) -> "AgentAction":
        # Allow alphanumeric, underscore, dash, dot, space, and pipe (|| separator)
        for c in self.action_id:
            if not (c.isalnum() or c in " _-.|"):
                raise ValueError(f"action_id contains invalid chars: {self.action_id!r}")
        return self

    @model_validator(mode="after")
    def _truncate_reason(self) -> "AgentAction":
        # Truncate rather than reject so the LLM's verbose replies still work.
        if len(self.reason) > 120:
            object.__setattr__(self, "reason", self.reason[:120])
        return self


# ----------------------------------------------------------------
# Errors
# ----------------------------------------------------------------

class AgentError(Exception):
    """Base error for the agent layer."""


class ParseError(AgentError):
    """LLM response couldn't be parsed as AgentAction."""


class InvalidActionError(AgentError):
    """LLM returned a syntactically valid action that doesn't match any legal option."""

    def __init__(self, action_id: str, message: str = ""):
        self.action_id = action_id
        super().__init__(message or f"action_id {action_id!r} not in legal actions")
