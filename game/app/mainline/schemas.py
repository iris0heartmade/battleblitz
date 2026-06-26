"""
Pydantic v2 schemas for mainline (campaign) data files.

These are the wire format for `game/mainlines/*.json`. We keep them
separate from `app.schemas` because mainlines are content (designer-
facing) rather than request/response payloads.

A mainline file MUST satisfy `Mainline`. `loader.load_mainline`
re-validates on every cache miss; in-process cache holds the parsed
object.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================
# Valid enums (kept in sync with classes/units/*.py type_id)
# ============================================================

VALID_CLASS_IDS: tuple[str, ...] = ("swordsman", "archer", "knight", "healer")

WinCondition = Literal["rout", "seize", "defend", "boss"]


def _class_id_pattern() -> str:
    return f"^({'|'.join(VALID_CLASS_IDS)})$"


# ============================================================
# Building blocks
# ============================================================

class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class UnitSpec(APIModel):
    """A starting unit for the mainline.

    `class_id` must match a `classes/units/*.py` `type_id` so the
    mainline engine can spawn the right unit subclass.
    `name` is an optional role nickname (e.g. "云"). If omitted the
    engine uses the class's default display name.
    """
    class_id: str = Field(pattern=_class_id_pattern())
    level: int = Field(default=1, ge=1, le=99)
    name: Optional[str] = Field(default=None, max_length=32)


class BattleSpec(APIModel):
    """One battle inside a mainline.

    `ally_composition` / `enemy_composition` map `class_id -> count`.
    The engine spawns units at the team-colored castles of the
    appropriate preset.

    `pre_battle_dialogue` / `post_battle_dialogue` are keys into the
    parent `Mainline.dialogues` map (not paths). They let the same
    battle be re-used across mainlines with different framing.
    """
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    map_preset: str = Field(min_length=1, max_length=64)
    map_seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    win_condition: WinCondition = "rout"
    ally_composition: dict[str, int] = Field(default_factory=dict)
    enemy_composition: dict[str, int] = Field(default_factory=dict)
    pre_battle_dialogue: Optional[str] = None
    post_battle_dialogue: Optional[str] = None

    @model_validator(mode="after")
    def _validate_compositions(self) -> "BattleSpec":
        for cid in (*self.ally_composition, *self.enemy_composition):
            if cid not in VALID_CLASS_IDS:
                raise ValueError(
                    f"unknown class_id {cid!r} in composition; "
                    f"valid: {VALID_CLASS_IDS}"
                )
        for cid, n in {**self.ally_composition, **self.enemy_composition}.items():
            if n < 1 or n > 16:
                raise ValueError(
                    f"unit count for {cid!r} must be 1..16, got {n}"
                )
        if not self.ally_composition:
            raise ValueError("ally_composition cannot be empty")
        if not self.enemy_composition:
            raise ValueError("enemy_composition cannot be empty")
        return self


class MainlineRewards(APIModel):
    """Granted to the player when they finish the last battle."""
    gold: int = Field(default=0, ge=0, le=1_000_000)
    unlock_class: Optional[str] = Field(default=None, pattern=_class_id_pattern())
    exp_per_unit: int = Field(default=0, ge=0, le=10_000)


class Mainline(APIModel):
    """A campaign: a sequence of battles with dialogue framing.

    `dialogues` is a key->path map. Keys are referenced by
    `BattleSpec.pre_battle_dialogue` / `post_battle_dialogue`. Paths
    are relative to `game/` (e.g. "stories/chapter_01/intro.json").

    `art_assets` is opaque to the engine — V1 the frontend ignores it;
    V2 it will surface portraits, BGM, cover art without changing
    this schema.
    """
    id: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    title: str = Field(min_length=1, max_length=128)
    synopsis: str = Field(max_length=2048, default="")
    cover_art: Optional[str] = None
    required_classes: list[str] = Field(min_length=1)
    starting_units: list[UnitSpec] = Field(min_length=1, max_length=8)
    dialogues: dict[str, str] = Field(default_factory=dict)
    battles: list[BattleSpec] = Field(min_length=1, max_length=32)
    rewards_on_clear: MainlineRewards = Field(default_factory=MainlineRewards)
    art_assets: dict = Field(default_factory=dict)

    @property
    def battle_count(self) -> int:
        """Number of battles in this mainline.

        Placeholder on the full Mainline model — returns 0. Real count
        is denormalized on MainlineSummary.battle_count (built by
        `list_mainlines`) for cheap list-endpoint serialization. Use
        `len(self.battles)` for the authoritative count.
        """
        return 0

    @model_validator(mode="after")
    def _validate_classes(self) -> "Mainline":
        for cid in self.required_classes:
            if cid not in VALID_CLASS_IDS:
                raise ValueError(
                    f"required_classes contains unknown class_id {cid!r}; "
                    f"valid: {VALID_CLASS_IDS}"
                )
        for cid in self.starting_units:
            if cid.class_id not in VALID_CLASS_IDS:
                raise ValueError(
                    f"starting_units contains unknown class_id {cid.class_id!r}"
                )
        # Each BattleSpec.dialogue key must exist in self.dialogues
        for b in self.battles:
            for key_name, key_val in (
                ("pre_battle_dialogue", b.pre_battle_dialogue),
                ("post_battle_dialogue", b.post_battle_dialogue),
            ):
                if key_val is None:
                    continue
                if key_val not in self.dialogues:
                    raise ValueError(
                        f"battle {b.id!r} references missing dialogue "
                        f"key {key_val!r} in {key_name}"
                    )
        # battle ids must be unique within the mainline
        ids = [b.id for b in self.battles]
        if len(set(ids)) != len(ids):
            from collections import Counter
            dupes = [k for k, v in Counter(ids).items() if v > 1]
            raise ValueError(f"duplicate battle ids: {dupes}")
        return self


# ============================================================
# Lightweight summary (for /mainlines list endpoint)
# ============================================================

class MainlineSummary(APIModel):
    id: str
    title: str
    synopsis: str
    cover_art: Optional[str]
    required_classes: list[str]
    battle_count: int


# ============================================================
# Route-level models (Step 3)
# ============================================================
#
# These models are the HTTP request/response payloads for the
# `/mainlines` router. They sit alongside the content-format models
# (`Mainline`, `BattleSpec`, ...) above because they are NOT derived
# from the on-disk JSON — they're the orchestrator's wire format.

from pydantic import BaseModel as _PydanticBaseModel, Field as _Field  # noqa: E402


class BattlePreview(_PydanticBaseModel):
    """Compact view of a battle for the lobby list."""
    id: str
    title: str
    win_condition: str
    map_preset: str


class MainlineDetailOut(_PydanticBaseModel):
    """Full mainline detail returned by `GET /mainlines/{id}`."""
    id: str
    title: str
    synopsis: str
    cover_art: Optional[str] = None
    required_classes: list[str]
    battle_count: int
    battles: list[BattlePreview]
    dialogue_keys: list[str]


class MainlineStartRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/start` body.

    Agent A's progression service uses ``user_name`` (not numeric
    ``profile_id``), so we accept it directly here for compatibility.
    """
    user_name: str = _Field(min_length=1, max_length=64)
    # V1 optional: skip the opening dialogue and go straight to battle.
    skip_intro: bool = False


class MainlineStartOut(_PydanticBaseModel):
    """Response after starting a mainline (or advancing to next battle)."""
    game_id: int
    player_id: int           # human's Player.id in the new game
    mainline_id: str
    battle_id: str           # e.g. "battle_01"
    battle_index: int
    total_battles: int
    state: str               # "dialogue" or "battle"
    pre_battle_dialogue_url: Optional[str] = None
    pre_battle_dialogue_key: Optional[str] = None


class MainlineAdvanceRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/advance` body."""
    user_name: str = _Field(min_length=1, max_length=64)
    game_id: int = _Field(ge=1)


class MainlineAdvanceOut(_PydanticBaseModel):
    """Response after advancing. `state` is either "dialogue" (post-battle
    scene to play next) or "victory" (campaign cleared)."""
    state: str
    mainline_id: str
    battle_index: int
    total_battles: int
    post_battle_dialogue_url: Optional[str] = None
    post_battle_dialogue_key: Optional[str] = None
    rewards: Optional[MainlineRewards] = None


class MainlineNextBattleRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/next-battle` body."""
    user_name: str = _Field(min_length=1, max_length=64)


class MainlineNextBattleOut(MainlineStartOut):
    """Identical shape to MainlineStartOut but for battle_idx > 0."""


class MainlineAbandonRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/abandon` body."""
    user_name: str = _Field(min_length=1, max_length=64)


class MainlineAbandonOut(_PydanticBaseModel):
    ok: bool = True
    mainline_id: Optional[str] = None
    abandoned_at: Optional[str] = None


class MainlineStepOut(_PydanticBaseModel):
    """Returned by `MainlineEngine.next_step()`.

    The frontend uses this to decide whether to show dialogue, the
    game board, or a victory screen.
    """
    state: str               # "menu"|"dialogue"|"battle"|"victory"|"abandoned"
    dialogue_url: Optional[str] = None
    dialogue_key: Optional[str] = None
    battle_id: Optional[str] = None
    battle_index: Optional[int] = None
    total_battles: int
    rewards: Optional[MainlineRewards] = None


__all__ = [
    "VALID_CLASS_IDS",
    "WinCondition",
    "UnitSpec",
    "BattleSpec",
    "MainlineRewards",
    "Mainline",
    "MainlineSummary",
    # Route-level (Step 3)
    "BattlePreview",
    "MainlineDetailOut",
    "MainlineStartRequest",
    "MainlineStartOut",
    "MainlineAdvanceRequest",
    "MainlineAdvanceOut",
    "MainlineNextBattleRequest",
    "MainlineNextBattleOut",
    "MainlineAbandonRequest",
    "MainlineAbandonOut",
    "MainlineStepOut",
]