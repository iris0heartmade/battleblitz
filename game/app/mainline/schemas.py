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
# Valid unit identifiers are discovered from classes/units/*.py. Content
# schemas must not need a code edit whenever a new data-defined class lands.
# ============================================================

CLASS_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


def valid_class_ids() -> set[str]:
    from app.classes.units import type_ids
    return set(type_ids())


# Backward-compatible export for callers that only need a startup snapshot.
VALID_CLASS_IDS: tuple[str, ...] = tuple(sorted(valid_class_ids()))
VALID_MERCENARY_UPGRADE_STATS = frozenset({"hp", "atk", "def", "matk", "mdef", "mov"})

WinCondition = Literal["rout", "seize", "defend", "boss"]


def _class_id_pattern() -> str:
    return CLASS_ID_PATTERN


# ============================================================
# Building blocks
# ============================================================

class APIModel(BaseModel):
    # extra="allow" 让 chapter JSON 的可魔改字段（如 waves/traps/tags/
    # difficulty_modifiers/battle_talks/...）不会被静默丢弃。
    # 字段会被 Pydantic 保留在 `model_extra` 里，由 mainline engine
    # 后续读取。
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        extra="allow",
    )


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


class SpawnUnitMatch(APIModel):
    color: str = Field(min_length=1, max_length=16)
    x: int = Field(ge=0, le=999)
    y: int = Field(ge=0, le=999)


class SpawnUnit(APIModel):
    x: int = Field(ge=0, le=999)
    y: int = Field(ge=0, le=999)
    type: str = Field(pattern=_class_id_pattern())
    color: str = Field(min_length=1, max_length=16)
    level: int = Field(default=1, ge=1, le=99)
    # Test fixtures: explicitly set the spawned Unit's starting HP. When
    # set, the engine overrides both ``hp`` and ``max_hp`` so the unit
    # spawns wounded. ``None`` (default) keeps the class's ``base_hp``.
    hp: Optional[int] = Field(default=None, ge=1, le=999)


class SpawnReplacementUnit(APIModel):
    type: str = Field(pattern=_class_id_pattern())
    color: str = Field(min_length=1, max_length=16)
    level: int = Field(default=1, ge=1, le=99)
    x: Optional[int] = Field(default=None, ge=0, le=999)
    y: Optional[int] = Field(default=None, ge=0, le=999)
    # See ``SpawnUnit.hp`` — same semantics on replacement units.
    hp: Optional[int] = Field(default=None, ge=1, le=999)


class SpawnReplaceSpec(APIModel):
    match: SpawnUnitMatch
    unit: SpawnReplacementUnit


class SpawnOverrides(APIModel):
    remove: list[SpawnUnitMatch] = Field(default_factory=list)
    replace: list[SpawnReplaceSpec] = Field(default_factory=list)
    add: list[SpawnUnit] = Field(default_factory=list)


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
    spawn_overrides: Optional[SpawnOverrides] = None
    pre_battle_dialogue: Optional[str] = None
    post_battle_dialogue: Optional[str] = None
    unlocks_commander: Optional[str] = Field(
        default=None, description="Commander hero_id unlocked after victory"
    )
    enemy_commander: Optional[str] = Field(
        default=None, description="Commander hero_id used by the enemy"
    )

    @model_validator(mode="after")
    def _check_commander_fields(self) -> "BattleSpec":
        from app.classes.heroes import get_or_none

        for field_name in ("unlocks_commander", "enemy_commander"):
            hero_id = getattr(self, field_name)
            if hero_id is None:
                continue
            hero = get_or_none(hero_id)
            if hero is None:
                raise ValueError(
                    f"{field_name}={hero_id!r} not found in heroes registry"
                )
            if not hero.is_commander:
                raise ValueError(
                    f"{field_name}={hero_id!r} is not a commander"
                )
        return self

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
        from app.mainline.spawn_overrides import (
            SpawnOverrideError,
            apply_spawn_overrides,
        )

        try:
            final_units = apply_spawn_overrides(
                list(map_data.get("initial_units", [])),
                self.spawn_overrides.model_dump(exclude_none=True)
                if self.spawn_overrides is not None
                else None,
            )
        except SpawnOverrideError as exc:
            raise ValueError(str(exc)) from exc
        map_colors = {u["color"] for u in final_units}
        missing = all_colors - map_colors
        if missing:
            raise ValueError(
                f"team colors {sorted(missing)} have no units in map "
                f"{self.map_id!r} after spawn_overrides "
                f"(available: {sorted(map_colors)})"
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


class MercenaryUpgradeRuleSpec(APIModel):
    """Authorable point cost and cap for one mercenary stat."""

    point_cost: int = Field(ge=1, le=100)
    max_bonus: int = Field(ge=1, le=100)


class MainlineMercenaryBalance(APIModel):
    """Declarative campaign-side rules for generic, non-hero units.

    Hero progression remains in the hero campaign state.  These values are
    intentionally scoped to the mainline's expendable mercenary roster.
    """

    total_points: int = Field(default=100, ge=0, le=10_000)
    starting_fund: int = Field(default=1000, ge=0, le=1_000_000)
    allowed_unit_types: Optional[list[str]] = None
    stat_rules: dict[str, MercenaryUpgradeRuleSpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_mercenary_unit_types(self) -> "MainlineMercenaryBalance":
        if self.allowed_unit_types is not None:
            known = valid_class_ids()
            unknown = sorted(set(self.allowed_unit_types) - known)
            if unknown:
                raise ValueError(
                    f"mercenary_balance.allowed_unit_types contains unknown class_ids {unknown!r}"
                )
        unknown_stats = sorted(set(self.stat_rules) - VALID_MERCENARY_UPGRADE_STATS)
        if unknown_stats:
            raise ValueError(
                f"mercenary_balance.stat_rules contains unsupported stats {unknown_stats!r}"
            )
        return self


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
    mercenary_balance: MainlineMercenaryBalance = Field(
        default_factory=MainlineMercenaryBalance
    )
    # Optional campaign link. Completion remains an explicit player choice;
    # this only tells the client which chapter can be entered next.
    next_mainline_id: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]{3,64}$")
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
        known = valid_class_ids()
        for cid in self.required_classes:
            if cid not in known:
                raise ValueError(
                    f"required_classes contains unknown class_id {cid!r}; "
                    f"valid: {sorted(known)}"
                )
        for cid in self.starting_units:
            if cid.class_id not in known:
                raise ValueError(
                    f"starting_units contains unknown class_id {cid.class_id!r}"
                )
        for battle in self.battles:
            if battle.spawn_overrides is None:
                continue
            spawn_types = [
                *(entry.type for entry in battle.spawn_overrides.add),
                *(entry.unit.type for entry in battle.spawn_overrides.replace),
            ]
            for class_id in spawn_types:
                if class_id not in known:
                    raise ValueError(
                        f"battle {battle.id!r} contains unknown class_id {class_id!r}"
                    )
        if self.rewards_on_clear.unlock_class and self.rewards_on_clear.unlock_class not in known:
            raise ValueError(
                f"rewards_on_clear.unlock_class is unknown: {self.rewards_on_clear.unlock_class!r}"
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


class MainlinePrepareHeroOut(_PydanticBaseModel):
    hero_id: str
    name: str
    class_id: str
    level: int
    exp: int
    promoted: bool
    can_promote: bool
    promotion_options: list[str]
    learned_skills: list[str]
    base_stats: dict
    equipment: dict
    equipment_bonuses: dict = {}


class MainlinePrepareUnitOut(_PydanticBaseModel):
    class_id: str
    level: int
    name: Optional[str] = None
    hero_id: Optional[str] = None
    color: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None


class MainlinePrepareOut(_PydanticBaseModel):
    mainline_id: str
    # True when the profile already has this campaign active.  The client
    # must then resume the persisted cursor instead of starting battle zero.
    is_active: bool = False
    title: str
    synopsis: str
    battle_index: int
    total_battles: int
    battle_id: str
    battle_title: str
    win_condition: str
    required_classes: list[str]
    pre_battle_dialogue_key: Optional[str] = None
    post_battle_dialogue_key: Optional[str] = None
    bgm_meta: Optional[BattleBgmMeta] = None
    inventory: dict[str, int]
    equipment_catalog: list[dict] = []
    heroes: list[MainlinePrepareHeroOut]
    roster_units: list[MainlinePrepareUnitOut]
    rewards_on_clear: MainlineRewards


class MainlineStartRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/start` body.

    Agent A's progression service uses ``user_name`` (not numeric
    ``profile_id``), so we accept it directly here for compatibility.
    """
    user_name: str = _Field(min_length=1, max_length=64)
    # V1 optional: skip the opening dialogue and go straight to battle.
    skip_intro: bool = False
    disabled_unit_indices: list[int] = _Field(default_factory=list)
    # When True, allow restarting the SAME mainline (e.g. after
    # loading a save).  Any in-flight game for the user is
    # force-aborted before the new battle spawns.  Defaults to
    # False so the existing "another mainline is active" 409
    # behaviour is preserved.
    force: bool = False


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
    victory_dialogue_url: Optional[str] = None
    victory_dialogue_key: Optional[str] = None
    # Present only when the completed chapter declares a linked successor.
    next_mainline_id: Optional[str] = None
    next_mainline_title: Optional[str] = None
    # Auto-save checkpoint written at chapter end.  None if the
    # advance did not produce an auto-save (e.g. mid-battle advance
    # that just bumped the cursor).  The FE renders
    # "自动存档中…… 自动存档完毕" when this is non-null.
    auto_save: Optional[dict] = None


class MainlineNextBattleRequest(_PydanticBaseModel):
    """`POST /mainlines/{id}/next-battle` body."""
    user_name: str = _Field(min_length=1, max_length=64)
    disabled_unit_indices: list[int] = _Field(default_factory=list)


class MainlinePreparePromoteRequest(_PydanticBaseModel):
    user_name: str = _Field(min_length=1, max_length=64)
    hero_id: str = _Field(min_length=1, max_length=64)
    target_class_id: str = _Field(min_length=1, max_length=64)


class MainlinePreparePromoteOut(_PydanticBaseModel):
    ok: bool = True
    hero_id: str
    class_id: str
    level: int
    promoted: bool
    hero_crest_left: int


class MainlinePrepareEquipmentRequest(_PydanticBaseModel):
    user_name: str
    hero_id: str
    slot: str
    equipment_id: Optional[str] = None


class MainlinePrepareEquipmentOut(_PydanticBaseModel):
    hero_id: str
    equipment: dict
    equipment_bonuses: dict


class MainlineShopPurchaseRequest(_PydanticBaseModel):
    user_name: str = _Field(min_length=1, max_length=64)
    item_id: str = _Field(min_length=1, max_length=64)
    quantity: int = _Field(default=1, ge=1, le=99)


class MainlineShopPurchaseOut(_PydanticBaseModel):
    item_id: str
    quantity: int
    inventory_count: int
    gold_remaining: int


class MainlineShopOut(_PydanticBaseModel):
    mainline_id: str
    gold: int
    items: list[dict]


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


# ============================================================
# Mercenary domain wire formats
# ============================================================


class ChapterBalanceConfigOut(_PydanticBaseModel):
    """Chapter-wide enemy / resource modifiers for mercenary battles.

    Mirrors ``app.mercenary_domain.ChapterBalanceConfig`` — kept as a
    separate Pydantic model so the wire format is stable even if the
    in-memory dataclass gains private fields.
    """
    enemy_modifiers: dict[str, int]
    max_recruit_count: int
    starting_fund: int
    total_points: int
    allowed_unit_types: list[str]
    stat_rules: dict[str, dict[str, int]]


class CommanderAllocationOut(_PydanticBaseModel):
    """Per-profile mercenary point allocation.

    The frontend uses this to render the pre-battle upgrade panel
    (spend 100 points across infantry / archer / knight …).
    """
    total_points: int
    spent_points: int
    unit_type_upgrades: dict[str, dict[str, int]]


class MainlineMercenaryConfigOut(_PydanticBaseModel):
    """Response shape for ``GET /mainlines/{id}/mercenary/config``.

    The mainline JSON can optionally override ``balance`` with a
    ``chapter_balance`` block; until that ships, the endpoint returns
    the dataclass defaults so the FE can render the panel without a
    second round-trip.
    """
    mainline_id: str
    balance: ChapterBalanceConfigOut
    allocation: CommanderAllocationOut
    # total - spent, recomputed for FE convenience.
    mercenary_points: int


class MainlineMercenaryAllocateRequest(_PydanticBaseModel):
    """Body for ``POST /mainlines/{id}/mercenary/allocate``."""
    user_name: str = _Field(min_length=1, max_length=64)
    unit_type: str = _Field(min_length=1, max_length=16)
    stat: str = _Field(min_length=1, max_length=16)
    value: int = _Field(ge=1, le=10)


class MainlineMercenaryAllocateOut(_PydanticBaseModel):
    ok: bool = True
    spent_points: int
    remaining_points: int
    unit_type_upgrades: dict[str, dict[str, int]]


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
    "MainlinePrepareHeroOut",
    "MainlinePrepareUnitOut",
    "MainlinePrepareOut",
    "MainlineStartRequest",
    "MainlineStartOut",
    "MainlineAdvanceRequest",
    "MainlineAdvanceOut",
    "MainlineNextBattleRequest",
    "MainlineNextBattleOut",
    "MainlinePreparePromoteRequest",
    "MainlinePreparePromoteOut",
    "MainlinePrepareEquipmentRequest",
    "MainlinePrepareEquipmentOut",
    "MainlineShopPurchaseRequest",
    "MainlineShopPurchaseOut",
    "MainlineShopOut",
    "MainlineAbandonRequest",
    "MainlineAbandonOut",
    "MainlineStepOut",
    # Mercenary domain wire formats
    "ChapterBalanceConfigOut",
    "CommanderAllocationOut",
    "MainlineMercenaryConfigOut",
    "MainlineMercenaryAllocateRequest",
    "MainlineMercenaryAllocateOut",
]
