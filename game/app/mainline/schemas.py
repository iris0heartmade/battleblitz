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

from app.schemas import BattleConfig


# ============================================================
# Valid enums (kept in sync with classes/units/*.py type_id)
# ============================================================

VALID_CLASS_IDS: tuple[str, ...] = (
    "swordsman", "archer", "knight", "warlock", "healer",
)

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

    Hero binding (P2.6+):
    * ``hero_id``  — references a hero in ``app.classes.heroes``.
      When set, the spawn helper applies the hero's stat overrides
      and art assets; ``class_id`` becomes the hero's
      ``base_class_id`` (still required for combat framework
      validation, even when the hero overrides every stat).
    * ``color`` / ``x`` / ``y`` — explicit spawn placement. When
      all three are present, the mainline engine matches this
      unit to the map's ``initial_units`` entry with the same
      ``color`` (or, if multiple match, the same ``(x, y)``) and
      applies the hero binding on top. Without these the hero
      spawns on the default base-class roster for its color.
    """
    class_id: str = Field(pattern=_class_id_pattern())
    level: int = Field(default=1, ge=1, le=99)
    name: Optional[str] = Field(default=None, max_length=32)
    # Hero binding. Optional — when None, this is a vanilla base-class unit.
    hero_id: Optional[str] = Field(default=None, max_length=64)
    # Explicit spawn placement (used by the hero override path).
    color: Optional[str] = Field(default=None, max_length=16)
    x: Optional[int] = Field(default=None, ge=0, le=999)
    y: Optional[int] = Field(default=None, ge=0, le=999)

    @model_validator(mode="after")
    def _check_hero_id(self) -> "UnitSpec":
        """If ``hero_id`` is set, it must resolve to a registered hero,
        and the hero's ``base_class_id`` must match this spec's
        ``class_id`` (a swordsman hero cannot be declared as a knight
        spec)."""
        if self.hero_id is None:
            return self
        # Lazy import to avoid a circular import at module load time
        # (game_logic imports from app.* in places).
        from app.classes.heroes import get_or_none

        profile = get_or_none(self.hero_id)
        if profile is None:
            raise ValueError(
                f"hero_id {self.hero_id!r} not found in app.classes.heroes registry"
            )
        if profile.base_class_id != self.class_id:
            raise ValueError(
                f"hero_id {self.hero_id!r} is a {profile.base_class_id!r} "
                f"hero but this spec declares class_id={self.class_id!r}"
            )
        return self


class BattleSpec(APIModel):
    """One battle inside a mainline.

    P2.6 — data-driven: the map's own ``initial_units`` array defines
    what units each color starts with. ``teams`` only says which
    colors belong to which side (``ally`` vs ``enemy``). The spawn
    loop in ``_start_battle_internal`` matches each map-side unit to
    a player by ``color`` and assigns it to the right seat.

    ``pre_battle_dialogue`` / ``post_battle_dialogue`` are keys into
    the parent ``Mainline.dialogues`` map (not paths). They let the
    same battle be re-used across mainlines with different framing.
    """
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    map_id: str = Field(min_length=1, max_length=64)
    map_seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    win_condition: WinCondition = "rout"
    teams: dict[str, list[str]] = Field(default_factory=dict)
    notes: Optional[str] = None
    battle_config: Optional[BattleConfig] = None
    pre_battle_dialogue: Optional[str] = None
    post_battle_dialogue: Optional[str] = None

    @model_validator(mode="after")
    def _check_team_colors(self) -> "BattleSpec":
        """Every color listed in ``teams`` must exist in the map's
        ``initial_units`` (otherwise no unit will spawn for that
        team)."""
        # Lazy import to avoid circular import at module load time
        # (game_logic imports from app.* in places).
        from app.game_logic import MAP_PRESETS

        map_data = MAP_PRESETS.get(self.map_id)
        if map_data is None:
            raise ValueError(f"map_id {self.map_id!r} not found in MAP_PRESETS")
        all_colors = {c for team in self.teams.values() for c in team}
        map_colors = {u["color"] for u in map_data.get("initial_units", [])}
        missing = all_colors - map_colors
        if missing:
            raise ValueError(
                f"team colors {sorted(missing)} have no units in map "
                f"{self.map_id!r} (available: {sorted(map_colors)})"
            )
        return self

    @model_validator(mode="after")
    def _check_bgm_track(self) -> "BattleSpec":
        """If ``battle_config.audio.bgm.track_id`` is set, it must be
        registered in ``game/config/battle_audio.json``.

        Authoring-time check — a mistyped track_id in a mainline JSON
        should fail at load_mainline, not silently slip through and
        produce a silent no-audio battle. Pydantic wraps ValueError
        into ValidationError, which the loader translates into
        MainlineValidationError (422 to the client).
        """
        if self.battle_config is None or self.battle_config.audio is None:
            return self
        bgm = self.battle_config.audio.bgm
        if bgm is None or not bgm.track_id:
            return self
        # Lazy import: keep mainline schemas importable without
        # pulling in the audio config loader at module load time.
        from app.battle_config import load_battle_audio_config

        tracks = (load_battle_audio_config().get("tracks") or {})
        if bgm.track_id not in tracks:
            available = sorted(tracks.keys())
            raise ValueError(
                f"battle_config.audio.bgm.track_id {bgm.track_id!r} "
                f"is not registered in battle_audio.json "
                f"(available: {available})"
            )
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


class BattleBgmMeta(_PydanticBaseModel):
    """Catalogue metadata for a battle's BGM, surfaced to the front-end.

    Intentionally excludes parameter overrides (volume / fade / loop)
    — those are server-controlled and re-merged by ``expand_battle_config``
    before the client sees the final config. The catalogue metadata is
    safe to expose so lobby detail panels and mainline headers can
    show "BGM: <title> (<category>)" without a second API round-trip.

    All four fields are optional because a track entry may declare
    only some of them — title is the most common, ``notes`` is the
    most likely to be omitted.
    """
    track_id: str
    title: Optional[str] = None
    category: Optional[str] = None
    file: Optional[str] = None
    notes: Optional[str] = None


class BattlePreview(_PydanticBaseModel):
    """Compact view of a battle for the lobby list."""
    id: str
    title: str
    win_condition: str
    map_id: str
    # P2.9 — optional BGM catalogue metadata. None when the battle
    # has no battle_config, or when battle_config.audio.bgm.track_id
    # is unset / not registered. Frontend renders "BGM: <title>"
    # from this block; never fall back to expanding the full
    # battle_config on the client.
    bgm: Optional[BattleBgmMeta] = None


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
    battle_config: Optional[BattleConfig] = None
    pre_battle_dialogue_url: Optional[str] = None
    pre_battle_dialogue_key: Optional[str] = None
    # P2.9 — BGM catalogue metadata for the just-spawned battle, so
    # the front-end can show "BGM: <title> (<category>)" in the
    # mainline header without a second round-trip. None when the
    # battle has no BGM or the track_id isn't registered.
    bgm_meta: Optional[BattleBgmMeta] = None


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
    "BattleBgmMeta",
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
