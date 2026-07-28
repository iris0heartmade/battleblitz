"""Shared helpers for the ``app.routes.mainline`` submodules.

Lives in ``_common.py`` because the symbols are referenced across
multiple per-domain submodules (prepare, battle_lifecycle, mercenary,
chapters).  Anything used by only one submodule should live alongside
that submodule rather than here.

Pieces owned here:
  * Game-root path helper (``game_root``) — actually used only by
    ``chapters.get_dialogue`` but kept here for predictable import
    surface.
  * Campaign-chain constants and helpers (``CAMPAIGN_CHAINS``,
    ``TEST_MAINLINE_CHAIN``, ``_chain_for``, ``_campaign_chain_name``)
    — used by chapters (list_mainlines) and battle_lifecycle.
  * Cursor helpers (``_current_mainline_for_user``,
    ``_has_cleared_mainline``, ``_current_test_mainline_for_user``,
    ``_ensure_test_mainline_unlocked``) — used by chapters, prepare,
    and battle_lifecycle.
  * Prepare-state builders (``_build_prepare_payload``,
    ``_persist_mainline_hero_results``) — used by prepare and
    battle_lifecycle.
  * BGM helper (``_battle_track_id``) — used by prepare, chapters,
    battle_lifecycle.
  * Profile loaders (``_load_profile``, ``_ensure_profile_or_create``)
    — used by prepare, shop, mercenary, battle_lifecycle.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.battle_config import battle_bgm_meta
from app.hero_domain import (
    build_hero_character_template,
    build_hero_class_template,
    build_initial_campaign_state,
    can_promote_hero,
    catalog_payload,
    default_equipment_for_class,
    equipped_stat_bonuses,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)
from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
)
from app.mainline.schemas import (
    BattleBgmMeta,
    MainlinePrepareHeroOut,
    MainlinePrepareOut,
    MainlinePrepareUnitOut,
)
from app.models import Player, Unit
from app.progression import ProgressionService
from app.progression.models import PlayerProfile
from app.save.models import GameSaveSlot

logger = logging.getLogger(__name__)

# ============================================================
# Path resolution
# ============================================================
#
# ``app/routes/mainline/_common.py`` → ``game/`` (parents[3]).
# Was parents[2] in the original monolithic ``routes/mainline.py``
# (one fewer level), so this had to shift up by one.
_GAME_ROOT: Path = Path(__file__).resolve().parents[3]


def game_root() -> Path:
    """Absolute path to the ``game/`` directory. Exposed for tests."""
    return _GAME_ROOT


# ============================================================
# Campaign chain abstraction
# ============================================================
#
# Each entry is a tuple of mainline ids that must be cleared
# sequentially.  ``/mainlines`` listing and ``/{id}/start`` gate both
# consume the dict so future chains (e.g. a "veteran" chain that
# unlocks after the test chain) only need a new key here.
TEST_MAINLINE_CHAIN = ("chapter_test_01", "chapter_test_02", "chapter_test_03")

CAMPAIGN_CHAINS: dict[str, tuple[str, ...]] = {
    "test": TEST_MAINLINE_CHAIN,
}


def _chain_for(mainline_id: str) -> Optional[tuple[str, ...]]:
    """Return the campaign chain that contains ``mainline_id`` (if any)."""
    for chain in CAMPAIGN_CHAINS.values():
        if mainline_id in chain:
            return chain
    return None


def _campaign_chain_name(mainline_id: str) -> Optional[str]:
    """Return the campaign name (dict key) for ``mainline_id``."""
    for name, chain in CAMPAIGN_CHAINS.items():
        if mainline_id in chain:
            return name
    return None


# ============================================================
# Per-user mainline cursor (driven by formal save slots)
# ============================================================


async def _has_cleared_mainline(
    session: AsyncSession,
    user_name: str,
    mainline_id: str,
) -> bool:
    """Return True when a formal save proves this chapter is cleared.

    P2(FE8 对齐):章节锁已删除,此函数不再用于门控(不再抛 403)。
    保留为**只读查询**,供前端/UI 给章节列表标注 cleared 状态
    (前端也可直接 join /saves 自行判断)。
    """
    # Late-bound lookup so test monkeypatches (``monkeypatch.setattr(
    # "app.routes.mainline.load_mainline", ...``) propagate.
    import app.routes.mainline as mainline_pkg

    try:
        battle_count = len(mainline_pkg.load_mainline(mainline_id).battles)
    except (MainlineNotFound, MainlineValidationError):
        return False
    rows = (await session.execute(
        select(GameSaveSlot).where(
            GameSaveSlot.user_name == user_name,
            GameSaveSlot.mainline_id == mainline_id,
            GameSaveSlot.chapter_index >= battle_count,
        )
    )).scalars().all()
    return bool(rows)


# ============================================================
# Prepare payload builder
# ============================================================


async def _build_prepare_payload(
    session: AsyncSession,
    profile: PlayerProfile,
    mainline_id: str,
) -> MainlinePrepareOut:
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    ml = mainline_pkg.load_mainline(mainline_id)
    battle_index = int((profile.mainline_progress or {}).get("battle_index", 0))
    if not (0 <= battle_index < len(ml.battles)):
        battle_index = 0
    battle = ml.battles[battle_index]
    svc = ProgressionService(session)
    inventory = await svc.ensure_hero_equipment_starters(profile.user_name)
    crest_count = int(inventory.get("hero_crest", 0))

    heroes: list[MainlinePrepareHeroOut] = []
    roster_units: list[MainlinePrepareUnitOut] = []
    for spec in ml.starting_units:
        roster_units.append(MainlinePrepareUnitOut(
            class_id=spec.class_id,
            level=spec.level,
            name=spec.name,
            hero_id=spec.hero_id,
            color=spec.color,
            x=spec.x,
            y=spec.y,
        ))
        if not spec.hero_id:
            continue
        stored_state = await svc.get_hero_campaign_state(profile.user_name, spec.hero_id)
        if stored_state is None:
            initial_state = build_initial_campaign_state(spec.hero_id)
            stored_state = hero_campaign_state_to_dict(initial_state)
            await svc.set_hero_campaign_state(
                profile.user_name,
                spec.hero_id,
                stored_state,
            )
        state = hero_campaign_state_from_dict(stored_state)
        # One-time migration for campaign saves created before equipment
        # existed.  Thereafter an empty loadout is a deliberate player
        # choice and must stay empty.
        if not state.equipment_initialized:
            state.equipment = default_equipment_for_class(state.class_id)
            state.equipment_initialized = True
            stored_state = hero_campaign_state_to_dict(state)
            await svc.set_hero_campaign_state(
                profile.user_name, spec.hero_id, stored_state,
            )
        current_class = build_hero_class_template(state.class_id)
        heroes.append(MainlinePrepareHeroOut(
            hero_id=state.hero_id,
            name=spec.name or build_hero_character_template(spec.hero_id).hero_id,
            class_id=state.class_id,
            level=state.level,
            exp=state.exp,
            promoted=state.promoted,
            can_promote=(crest_count > 0 and can_promote_hero(state, current_class)),
            promotion_options=list(current_class.promotion_options),
            learned_skills=list(state.learned_skills),
            base_stats=dict(state.base_stats),
            equipment=dict(state.equipment),
            equipment_bonuses=equipped_stat_bonuses(state.equipment),
        ))

    track_id = _battle_track_id(battle)
    return MainlinePrepareOut(
        mainline_id=ml.id,
        is_active=getattr(profile, "active_mainline", None) == ml.id,
        title=ml.title,
        synopsis=ml.synopsis,
        battle_index=battle_index,
        total_battles=len(ml.battles),
        battle_id=battle.id,
        battle_title=battle.title,
        win_condition=battle.win_condition,
        required_classes=list(ml.required_classes),
        pre_battle_dialogue_key=battle.pre_battle_dialogue,
        post_battle_dialogue_key=battle.post_battle_dialogue,
        bgm_meta=(
            BattleBgmMeta.model_validate(battle_bgm_meta(track_id))
            if track_id is not None else None
        ),
        inventory={k: int(v) for k, v in inventory.items()},
        equipment_catalog=catalog_payload(),
        heroes=heroes,
        roster_units=roster_units,
        rewards_on_clear=ml.rewards_on_clear,
    )


# ============================================================
# Persist post-battle hero state
# ============================================================


async def _persist_mainline_hero_results(
    session: AsyncSession,
    profile: PlayerProfile,
    game_id: int,
) -> None:
    """Write long-term Hero progression fields back into profile storage."""

    players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()
    human = next(
        (
            player for player in players
            if not player.is_ai
            and not player.is_spectator
            and player.user_name == profile.user_name
        ),
        None,
    )
    if human is None:
        logger.warning(
            "mainline hero persist skipped: user=%s game=%d reason=no_human_player",
            profile.user_name,
            game_id,
        )
        return

    units = (await session.execute(
        select(Unit).where(Unit.player_id == human.id)
    )).scalars().all()
    svc = ProgressionService(session)
    persisted_count = 0
    for unit in units:
        if not unit.hero_id:
            continue
        stored_state = await svc.get_hero_campaign_state(profile.user_name, unit.hero_id)
        if stored_state is None:
            stored_state = hero_campaign_state_to_dict(
                build_initial_campaign_state(unit.hero_id)
            )
        prior = hero_campaign_state_from_dict(stored_state)
        campaign_base_stats = dict(unit.campaign_base_stats or {})
        if not campaign_base_stats:
            # Legacy in-flight battles predate Unit.campaign_base_stats.
            # This is a one-time best-effort recovery; new games always use
            # the explicit snapshot above.  Log so an operator can identify
            # saves whose equipment may already have been persisted wrongly.
            equipment_bonuses = equipped_stat_bonuses(prior.equipment)
            logger.warning(
                "mainline hero persist using legacy stat fallback: user=%s game=%d hero=%s",
                profile.user_name,
                game_id,
                unit.hero_id,
            )
            campaign_base_stats = {
                "hp": int(unit.max_hp) - int(equipment_bonuses.get("hp", 0)),
                "atk": int(unit.atk) - int(equipment_bonuses.get("atk", 0)),
                "def": int(unit.def_) - int(equipment_bonuses.get("def", 0)),
                "matk": int(unit.matk) - int(equipment_bonuses.get("matk", 0)),
                "mdef": int(unit.mdef) - int(equipment_bonuses.get("mdef", 0)),
                "mov": int(unit.mov) - int(equipment_bonuses.get("mov", 0)),
            }
        updated = {
            "hero_id": unit.hero_id,
            "class_id": unit.unit_type,
            "level": int(unit.level),
            "exp": int(unit.exp),
            "base_stats": {
                "hp": int(campaign_base_stats["hp"]),
                "atk": int(campaign_base_stats["atk"]),
                "def": int(campaign_base_stats["def"]),
                "matk": int(campaign_base_stats["matk"]),
                "mdef": int(campaign_base_stats["mdef"]),
                "mov": int(campaign_base_stats["mov"]),
                # MP is temporary battle state; keep the stored long-term pool.
                "mp": int(prior.base_stats.get("mp", build_initial_campaign_state(unit.hero_id).base_stats["mp"])),
            },
            "weapon_ranks": dict(prior.weapon_ranks),
            "learned_skills": list(unit.skills or []),
            "promoted": build_hero_class_template(unit.unit_type).tier >= 2,
            "equipment": dict(prior.equipment),
            "equipment_initialized": prior.equipment_initialized,
        }
        await svc.set_hero_campaign_state(profile.user_name, unit.hero_id, updated)
        persisted_count += 1

    if persisted_count:
        logger.info(
            "mainline hero persist ok: user=%s game=%d heroes=%d",
            profile.user_name,
            game_id,
            persisted_count,
        )


# ============================================================
# BGM helpers (P2.9)
# ============================================================


def _battle_track_id(battle) -> Optional[str]:
    """Pull the bare ``audio.bgm.track_id`` from a BattleSpec, or
    None if the battle declares no battle_config / audio / bgm."""
    if battle.battle_config is None or battle.battle_config.audio is None:
        return None
    bgm = battle.battle_config.audio.bgm
    if bgm is None:
        return None
    return bgm.track_id or None


# ============================================================
# Profile loaders
# ============================================================


async def _load_profile(session: AsyncSession, user_name: str) -> PlayerProfile:
    """Resolve a ``user_name`` to a ``PlayerProfile`` (or raise 404).

    Agent A's service uses ``user_name`` as the primary key on the
    player-facing API; we mirror that here.

    Business endpoints (advance / next-battle / abandon) must keep this
    strict behavior: a typo'd ``user_name`` MUST surface as 404, never
    silently create a wrong profile. Use ``_ensure_profile_or_create``
    for endpoints that want a fallback auto-create.
    """
    logger.debug("load_profile entry: user_name=%s", user_name)
    result = await session.execute(
        select(PlayerProfile).where(PlayerProfile.user_name == user_name)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        # Frontend MainlineView.ensureProfile() is supposed to call
        # POST /progression/profiles before /mainlines/{id}/start; if
        # we still see a miss here, something in the client flow
        # regressed. The structured detail below helps the FE render a
        # helpful toast AND lets ops grep a single line for triage.
        logger.warning(
            "load_profile miss: user_name=%s hint=call_POST_progression_profiles_first",
            user_name,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "profile_not_found",
                "user_name": user_name,
                "hint": (
                    "Call POST /progression/profiles first to create "
                    "the player profile"
                ),
            },
        )
    logger.debug("load_profile ok: user_name=%s profile_id=%d", user_name, profile.id)
    return profile


async def _ensure_profile_or_create(
    session: AsyncSession, user_name: str
) -> PlayerProfile:
    """Resolve ``user_name`` to a ``PlayerProfile``; auto-create if missing.

    Use ONLY for the entry point (``/mainlines/{id}/start``) where a
    benign race condition / stale frontend cache must not block the
    user from starting a chapter. Business endpoints (advance /
    next-battle / abandon) must keep the strict 404 via
    ``_load_profile`` — otherwise a typo'd user_name would silently
    create a wrong profile.

    The auto-created row uses ORM defaults, so the profile is created
    with the same shape as ``POST /progression/profiles``. The caller
    is responsible for committing the session.
    """
    logger.debug("ensure_profile_or_create entry: user_name=%s", user_name)
    result = await session.execute(
        select(PlayerProfile).where(PlayerProfile.user_name == user_name)
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        logger.debug(
            "ensure_profile_or_create hit: user_name=%s profile_id=%d",
            user_name, profile.id,
        )
        return profile
    # Auto-create. ORM defaults match POST /progression/profiles.
    profile = PlayerProfile(user_name=user_name)
    session.add(profile)
    await session.flush()
    logger.info(
        "auto-created profile for mainline start: user=%s profile_id=%d",
        user_name, profile.id,
    )
    return profile


# ============================================================
# Re-exports
# ============================================================

__all__ = [
    "CAMPAIGN_CHAINS",
    "TEST_MAINLINE_CHAIN",
    "game_root",
    "_chain_for",
    "_campaign_chain_name",
    "_has_cleared_mainline",
    "_build_prepare_payload",
    "_persist_mainline_hero_results",
    "_battle_track_id",
    "_ensure_profile_or_create",
    "_load_profile",
]
