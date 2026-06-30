"""
Pydantic v2 schemas for request validation and response serialization.

We keep these separate from ORM models so we can evolve the wire format
without touching the DB layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Common base
# ============================================================

class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ============================================================
# Game lifecycle
# ============================================================

class CreateGameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    map_seed: Optional[int] = None  # None = random
    max_players: int = Field(default=2, ge=2, le=4)
    map_preset: Optional[str] = None  # e.g. "classic" / "open_plains" / "mountain_pass"
    map_biome: str = Field(default="grass")  # "grass" | "snow" | "desert"
    unit_composition: Optional[str] = None  # e.g. "classic" / "aggressive" / "defensive"


class JoinGameRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None  # auto-assigned if missing


class RejoinGameRequest(BaseModel):
    """Resume an existing player in a game (e.g. after browser refresh)."""
    player_id: int


class RejoinGameResponse(BaseModel):
    game_id: int
    game_status: str
    player: PlayerOut


class AddAIRequest(BaseModel):
    """Body of POST /games/{id}/add-ai. AI name auto-generated if missing."""
    difficulty: str = Field(default="normal", pattern="^(easy|normal|hard)$")
    # "rules" (built-in) or "llm" (LLMAgent). Defaults to "rules" to keep
    # existing behaviour; set to "llm" to opt in to LLM-driven opponent.
    agent_kind: str = Field(default="rules", pattern="^(rules|llm)$")
    # Personality for LLM agents (ignored when agent_kind == "rules").
    personality: str = Field(
        default="balanced",
        pattern="^(aggressive|defensive|balanced|trickster)$",
    )


class PresetInfo(BaseModel):
    id: str
    name: str
    description: str
    biome: Optional[str] = None  # "grass" | "snow" | "desert" (preset's visual theme)
    size: int = 15  # Edge length of the square grid (P0.4+ supports 15–45)


class PresetsResponse(BaseModel):
    maps: List[PresetInfo]
    unit_compositions: List[PresetInfo]


class StartGameRequest(BaseModel):
    """Optional manual trigger; auto-starts when MIN_PLAYERS have joined."""


# ============================================================
# Entity schemas (read)
# ============================================================

class TileOut(APIModel):
    x: int
    y: int
    terrain: str
    owner_id: Optional[int]
    occupied_unit_id: Optional[int]


class UnitOut(APIModel):
    id: int
    player_id: int
    unit_type: str
    name: str
    level: int
    exp: int
    hp: int
    max_hp: int
    atk: int
    def_: int
    matk: int = 0
    mdef: int = 0
    mov: int
    mp: int = 0
    morale: int = 0
    x: int
    y: int
    has_acted: bool
    has_moved: bool = False
    skills: List[str]
    # Class-level combat stats the client needs to render attack range /
    # threat-area overlays without hard-coding values per unit type.
    attack_range: int = 1
    min_attack_range: int = 0


class PlayerOut(APIModel):
    id: int
    user_name: str
    color: str
    is_alive: bool
    has_ended_turn: bool
    seat: int
    is_ai: bool = False
    agent_kind: str = "rules"
    agent_personality: str = "balanced"
    gold: int = 0
    units: List[UnitOut] = []


class ActionLogOut(APIModel):
    id: int
    turn_number: int
    player_id: Optional[int]
    action_type: str
    description: str
    created_at: datetime


class GameSummaryOut(APIModel):
    id: int
    name: str
    status: str
    turn_number: int
    current_player_index: int
    map_seed: int
    map_preset: Optional[str]
    map_biome: str
    phase: str = "player"   # "player" | "ai" | "animating"
    created_at: datetime


class GameStateOut(APIModel):
    """Full game state for a player's dashboard."""
    game: GameSummaryOut
    tiles: List[TileOut]
    players: List[PlayerOut]
    current_player_id: Optional[int]
    logs: List[ActionLogOut] = []


# ============================================================
# Action requests
# ============================================================

class MoveRequest(BaseModel):
    player_id: int
    unit_id: int
    to_x: int = Field(ge=0)
    to_y: int = Field(ge=0)


class AttackRequest(BaseModel):
    player_id: int
    attacker_id: int
    target_id: int


class ClaimRequest(BaseModel):
    """P0.4 — body of POST /games/{id}/claim. Unit must be standing on
    a claim-eligible tile (village / barracks / castle_vault)."""
    player_id: int
    unit_id: int


class ClaimResult(BaseModel):
    ok: bool = True
    started: bool = False        # True if this call started a new session
    completed: bool = False      # True if this call flipped ownership
    new_owner_id: Optional[int] = None
    completes_turn: int = 0
    description: str


class RecruitRequest(BaseModel):
    """P0.4 — body of POST /games/{id}/recruit.

    Spend gold to spawn a new unit on the barracks tile where the
    `unit_id` (the recruiter) is currently standing. The recruiter
    must belong to the player who owns the barracks, and the new
    unit is created with has_acted=True, has_moved=True, mp=0 (it
    cannot act this turn — same as Fire-Emblem's "summon" timing).
    """
    player_id: int
    unit_id: int          # recruiter standing on the barracks
    unit_type: str        # type_id of the new unit (e.g. "swordsman")


class RecruitResult(BaseModel):
    ok: bool = True
    recruiter_unit_id: int
    new_unit_id: int
    new_unit_type: str
    cost: int
    gold_remaining: int
    description: str


class SkillRequest(BaseModel):
    player_id: int
    unit_id: int
    skill: str  # "heal" | "double_strike" (auto on attack) | "snipe" (auto)
    target_id: Optional[int] = None  # for heal: the ally to heal


class WaitRequest(BaseModel):
    player_id: int
    unit_id: int


# ============================================================
# Turn control
# ============================================================

class EndTurnRequest(BaseModel):
    player_id: int


# ============================================================
# Generic responses
# ============================================================

class DamageInfo(BaseModel):
    damage: int
    is_crit: bool
    is_kill: bool
    attacker_unit_id: int
    target_unit_id: int


class MoveResult(BaseModel):
    ok: bool = True
    unit_id: int
    from_x: int
    from_y: int
    to_x: int
    to_y: int
    cost: int
    castle_captured: bool = False
    description: str


class AttackResult(BaseModel):
    ok: bool = True
    hits: List[DamageInfo]
    target_unit_id: int
    target_hp_after: int
    target_def_bonus: int
    attacker_exp_gained: int
    assist_unit_ids: List[int] = []
    counter_damage: int = 0
    attacker_hp_after: int
    description: str


class SkillResult(BaseModel):
    ok: bool = True
    unit_id: int
    skill: str
    target_unit_id: Optional[int]
    restored_hp: int = 0
    description: str


class WaitResult(BaseModel):
    ok: bool = True
    unit_id: int
    description: str


class EndTurnResult(BaseModel):
    ok: bool = True
    next_player_id: Optional[int]
    turn_number: int
    game_status: str
    leveled_units: List[int] = []
    eliminated_players: List[int] = []
    actions_taken: int = 0
    actions_required: int = 2
    description: str