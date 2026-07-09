"""
Pydantic v2 schemas for request validation and response serialization.

We keep these separate from ORM models so we can evolve the wire format
without touching the DB layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Common base
# ============================================================

class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ============================================================
# Battle config
# ============================================================

TRACK_ID_PATTERN = r"^[a-z0-9_-]{1,64}$"


class BattleBgmConfig(BaseModel):
    track_id: str = Field(pattern=TRACK_ID_PATTERN)
    loop: Optional[bool] = None
    volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    fade_in_ms: Optional[int] = Field(default=None, ge=0, le=10000)
    fade_out_ms: Optional[int] = Field(default=None, ge=0, le=10000)


class BattleAudioConfig(BaseModel):
    bgm: Optional[BattleBgmConfig] = None


class BattleConfig(BaseModel):
    audio: Optional[BattleAudioConfig] = None


# ============================================================
# Game lifecycle
# ============================================================

class CreateGameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    map_seed: Optional[int] = None  # None = random
    # P2.4 — max_players is server-derived from the chosen map's
    # `recommended_players`. The frontend no longer sends it.
    map_preset: Optional[str] = None  # e.g. "classic" / "open_plains" / "mountain_pass"
    map_biome: str = Field(default="grass")  # "grass" | "snow" | "desert"
    # P2.3 — victory condition. "rout" (default) / "seize" / "reach" /
    # "defend". The last two only make sense on mission maps.
    win_condition: str = "rout"
    # P2.3 — when win_condition == "reach", the target tile.
    reach_tile: Optional[Dict[str, int]] = None  # {"x": int, "y": int}
    # P2.3 — when win_condition == "defend", the round count at
    # which the surviving team wins.
    defend_turns: int = 10
    battle_config: Optional[BattleConfig] = None


class JoinGameRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None  # auto-assigned if missing
    # P2.3 — team grouping. None falls back to `color` (1V1 free-for-all
    # behaviour preserved). Multiple players with the same team_id are
    # treated as one logical side for win-condition checks.
    team: Optional[str] = None
    # P2.4 — role of joiner:
    #   "player"    (default) — joins as a regular player with a colour
    #                          and units, counted against capacity.
    #   "spectator" — joins as an audience member. No units are spawned,
    #                 no team. Counts against the spectator cap (NOT
    #                 capacity). Must call end_turn to advance the
    #                 turn cycle but can never execute game actions.
    role: Optional[str] = Field(default=None, pattern="^(player|spectator)$")


class UpdateTeamRequest(BaseModel):
    """Update a player's team in the lobby."""
    team: Optional[str] = Field(None, max_length=32)
    caller_player_id: int  # who is making this request (permission check)


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
    # P2.5 — personality also drives the rules AI. Three graduated
    # tiers: aggressive (most eager) → balanced → conservative
    # (most defensive but still grabs nearby buildings).
    # `trickster` removed until implemented.
    personality: str = Field(
        default="balanced",
        pattern="^(aggressive|balanced|conservative)$",
    )


class PresetInfo(BaseModel):
    id: str
    name: str
    description: str
    biome: Optional[str] = None  # "grass" | "snow" | "desert" (preset's visual theme)
    size: int = 15  # Edge length of the square grid (P0.4+ supports 15–45)
    # P2.4 — recommended player count for this map. Drives the
    # create-game category selector on the frontend and the server's
    # per-room capacity (Game.capacity). Defaults to MAX_PLAYERS=4
    # server-side when absent from the preset JSON.
    recommended_players: Optional[int] = None
    # P2.4 polish — designer-facing free-form notes. Surfaced in the
    # create-game form below the description. May include playstyle
    # hints or "⚠️ 模式已弃用" warnings for legacy reach/defend maps.
    notes: Optional[str] = None


class PresetsResponse(BaseModel):
    maps: List[PresetInfo]


class StartGameRequest(BaseModel):
    """Optional manual trigger; auto-starts when MIN_PLAYERS have joined."""


# ============================================================
# Entity schemas (read)
# ============================================================

class TileOut(APIModel):
    x: int
    y: int
    terrain: str
    # P2.4 — when terrain == "castle", `subtype` may be one of
    # castle_floor / castle_wall / castle_door / castle_throne /
    # castle_stairs / castle_vault. Used by the frontend renderer
    # to pick the correct tile asset.
    subtype: Optional[str] = None
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
    # Hero binding (P2.6+). When set, the client should use the
    # hero's bespoke art (sprite / portrait / crest) instead of the
    # generic base-class asset. The hero's stat overrides have
    # already been baked into the atk/def/matk/mdef/mov fields
    # above by the spawn helper.
    hero_id: Optional[str] = None


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
    # P2.3 — team grouping. May equal `color` for 1V1 free-for-all
    # (the front-end treats them identically in that case).
    team: Optional[str] = None
    # P2.4 — spectator flag. True if this Player is a read-only audience
    # member (no units, must confirm turn but can't act).
    is_spectator: bool = False
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
    phase: str = "player"   # "player" | "ai" | "spectator" | "animating"
    # P2.3 — victory-condition metadata. The front-end reads these
    # to render the right victory banner copy.
    win_condition: str = "rout"
    win_reason: Optional[str] = None
    # P2.4 — per-room capacity (max players + AI). Derived from the
    # chosen map's `recommended_players` at create-time and stored on
    # Game.capacity. Drives the lobby's add-AI button gate and the
    # "room full" check on join.
    capacity: int = 4
    battle_config: Dict = Field(default_factory=dict)
    created_at: datetime


class PendingClaimOut(APIModel):
    """P2.4 polish — one in-flight claim on a claimable tile.

    The client renders a "X turns remaining" progress indicator on
    the tile using `turns_remaining` + `total_turns` (so a 2/2
    bar fills up as the claim nears completion).
    """
    tile_id: int
    tile_x: int
    tile_y: int
    started_turn: int
    completes_turn: int
    turns_remaining: int
    total_turns: int
    target_player_id: int


class GameStateOut(APIModel):
    """Full game state for a player's dashboard."""
    game: GameSummaryOut
    tiles: List[TileOut]
    players: List[PlayerOut]
    current_player_id: Optional[int]
    logs: List[ActionLogOut] = []
    # P2.4 polish — list of in-flight claim sessions.
    pending_claims: List[PendingClaimOut] = []


class LobbyTeamOut(APIModel):
    """P2.3 — summary of a single team in the lobby. Lets the
    front-end render 'join the red team' dropdowns without
    having to compute aggregates client-side."""
    team: str
    player_count: int
    color: Optional[str] = None  # representative color (most common)
    is_full: bool = False  # True if game is at max_players and this team is full
    # If max_players per team is enforced (e.g. 2 per side in 2v2), this
    # is the soft cap. We don't currently enforce it server-side
    # but expose it so the UI can grey out 'Join' buttons.
    capacity: int = 0  # 0 = no cap (free-for-all)


class LobbyInfoOut(APIModel):
    """P2.3 — minimal lobby view. Returned by GET /games/{id}/lobby
    so the front-end can show 'Red team: 2/2, Blue team: 1/2' etc.
    """
    game_id: int
    status: str
    max_players: int
    player_count: int
    teams: List[LobbyTeamOut]
    win_condition: str = "rout"
    win_reason: Optional[str] = None


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

    Spend gold to spawn a new unit on a barracks tile owned by the
    player. The barracks MUST be empty (no unit standing on it) —
    units can't squat on a barracks and recruit, they have to move
    off first. This keeps barracks as "shared production facilities"
    rather than a unit's personal anchor.
    """
    player_id: int
    tile_x: int                      # X coord of the empty barracks
    tile_y: int                      # Y coord of the empty barracks
    unit_type: str                   # type_id of the new unit (e.g. "swordsman")


class RecruitResult(BaseModel):
    ok: bool = True
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
