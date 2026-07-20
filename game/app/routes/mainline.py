"""
Mainline (campaign) routes — Step 3 of the BattleBlitz plan.

Endpoints (mounted under ``/mainlines`` by ``app/main.py``):

  GET  /mainlines                       List every mainline (lobby view).
  GET  /mainlines/dialogue              Serve a dialogue JSON by path.
  GET  /mainlines/{mainline_id}         Detail of one mainline.
  POST /mainlines/{mainline_id}/start   Begin a campaign. Spawns a Game
                                        row + an AI opponent + first
                                        battle's tiles/units. Returns
                                        the game_id and (if any) the
                                        opening dialogue URL.
  POST /mainlines/{mainline_id}/advance Advance after a battle finishes.
                                        Marks the battle_index forward,
                                        or grants rewards and clears the
                                        active campaign on the last
                                        battle.
  POST /mainlines/{mainline_id}/next-battle
                                        Spawn the next battle's Game
                                        after the post-battle dialogue
                                        has been played.
  POST /mainlines/{mainline_id}/abandon Drop the active mainline.

The routes are thin: each handler builds a ``MainlineEngine`` from the
DB session + the loaded mainline, and the engine does the rest.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.battle_config import battle_bgm_meta, expand_battle_config
from app.config import MAINLINE_INITIAL_GOLD
from app.game_logic import MAP_PRESETS, build_ai_player
from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
    list_mainlines,
    load_mainline,
)
from app.mainline.engine import (
    MainlineEngine,
    MainlineState,
    load_engine,
    mainline_game_name,
    parse_mainline_game_name,
    utcnow_iso,
)
from app.mainline.schemas import (
    BattleBgmMeta,
    BattlePreview,
    ChapterBalanceConfigOut,
    CommanderAllocationOut,
    MainlineAbandonOut,
    MainlineAdvanceOut,
    MainlineDetailOut,
    MainlineMercenaryAllocateOut,
    MainlineMercenaryAllocateRequest,
    MainlineMercenaryConfigOut,
    MainlineNextBattleOut,
    MainlinePrepareHeroOut,
    MainlinePrepareEquipmentOut,
    MainlinePrepareEquipmentRequest,
    MainlinePrepareOut,
    MainlinePreparePromoteOut,
    MainlinePrepareUnitOut,
    MainlineShopOut,
    MainlineShopPurchaseOut,
    MainlineShopPurchaseRequest,
    MainlineStartOut,
)
from app.hero_domain import (
    build_campaign_spawn_payload,
    build_hero_character_template,
    build_hero_class_template,
    build_initial_campaign_state,
    can_promote_hero,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
    promote_hero,
    EQUIPMENT_SLOTS,
    catalog_payload,
    default_equipment_for_class,
    equipped_stat_bonuses,
    get_equipment,
)
from app.hero_domain.promotion import HeroPromotionError
from app.mainline.spawn_overrides import apply_spawn_overrides
from app.models import ActionLog, Game, Player, Unit
from app.progression import (
    MainlineAlreadyActive,
    NoActiveMainline,
    PlayerProfile,
    ProfileNotFound,
    ProgressionService,
)
from app.routes.game import _start_battle_internal
from app.routes.save import auto_save_checkpoint
from app.save import (
    AutoSaveCheckpointOut,
    GameSaveSlot,
    PrepCompleteRequest,
)
from app.commanders.registry import get_power_threshold
from app.item_catalog import get_item, load_shop

logger = logging.getLogger(__name__)
# USER_ACTION audit lines per §15 of the logging standard
audit = logging.getLogger("audit.mainline")
# Engine-level logger (carries module:line in the file handler)
engine_logger = logging.getLogger("app.mainline.engine")

router = APIRouter(prefix="/mainlines", tags=["mainline"])


# ============================================================
# Path resolution for /mainlines/dialogue
# ============================================================

# game/app/routes/mainline.py → game/  (parents[2])
_GAME_ROOT: Path = Path(__file__).resolve().parents[2]


def game_root() -> Path:
    """Absolute path to the ``game/`` directory. Exposed for tests."""
    return _GAME_ROOT


TEST_MAINLINE_CHAIN = ("chapter_test_01", "chapter_test_02", "chapter_test_03")


async def _has_cleared_mainline(
    session: AsyncSession,
    user_name: str,
    mainline_id: str,
) -> bool:
    """Return True when a formal save proves this chapter is cleared."""
    try:
        battle_count = len(load_mainline(mainline_id).battles)
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


async def _current_test_mainline_for_user(
    session: AsyncSession,
    user_name: str,
) -> str:
    for mainline_id in TEST_MAINLINE_CHAIN:
        if not await _has_cleared_mainline(session, user_name, mainline_id):
            return mainline_id
    return TEST_MAINLINE_CHAIN[-1]


async def _ensure_test_mainline_unlocked(
    session: AsyncSession,
    user_name: str,
    mainline_id: str,
) -> None:
    if mainline_id not in TEST_MAINLINE_CHAIN:
        return
    allowed = await _current_test_mainline_for_user(session, user_name)
    if mainline_id != allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "error": "mainline_locked",
                "mainline_id": mainline_id,
                "available_mainline_id": allowed,
                "hint": "Clear the previous chapter from a formal save before entering this one.",
            },
        )


async def _build_prepare_payload(
    session: AsyncSession,
    profile: PlayerProfile,
    mainline_id: str,
) -> MainlinePrepareOut:
    ml = load_mainline(mainline_id)
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
        bgm_meta=BattleBgmMeta.model_validate(battle_bgm_meta(_battle_track_id(battle)))
        if _battle_track_id(battle) else None,
        inventory={k: int(v) for k, v in inventory.items()},
        equipment_catalog=catalog_payload(),
        heroes=heroes,
        roster_units=roster_units,
        rewards_on_clear=ml.rewards_on_clear,
    )


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


def _build_disabled_unit_spawn_overrides(
    ml,
    battle,
    disabled_unit_indices: list[int] | None,
) -> dict | None:
    disabled_indices = sorted({
        int(idx) for idx in (disabled_unit_indices or [])
        if isinstance(idx, int) or (isinstance(idx, str) and str(idx).isdigit())
    })
    if not disabled_indices:
        return None

    base_units = list((MAP_PRESETS.get(battle.map_id) or {}).get("initial_units", []))
    resolved_units = apply_spawn_overrides(
        base_units,
        battle.spawn_overrides.model_dump(exclude_none=True)
        if battle.spawn_overrides is not None
        else None,
    )
    used_coords: set[tuple[str, int, int]] = set()
    remove_entries: list[dict] = []

    for idx in disabled_indices:
        if idx < 0 or idx >= len(ml.starting_units):
            continue
        spec = ml.starting_units[idx]
        if spec.hero_id:
            continue
        target_color = spec.color or "red"
        matched = None
        for entry in resolved_units:
            key = (str(entry["color"]), int(entry["x"]), int(entry["y"]))
            if key in used_coords:
                continue
            if str(entry.get("color")) != target_color:
                continue
            if str(entry.get("type")) != spec.class_id:
                continue
            matched = entry
            break
        if matched is None:
            continue
        key = (str(matched["color"]), int(matched["x"]), int(matched["y"]))
        used_coords.add(key)
        remove_entries.append({
            "color": str(matched["color"]),
            "x": int(matched["x"]),
            "y": int(matched["y"]),
        })

    if not remove_entries:
        return None
    return {"remove": remove_entries}


# ============================================================
# BGM helpers (P2.9)
# ============================================================

def _battle_track_id(battle: "BattleSpec") -> Optional[str]:
    """Pull the bare ``audio.bgm.track_id`` from a BattleSpec, or
    None if the battle declares no battle_config / audio / bgm."""
    if battle.battle_config is None or battle.battle_config.audio is None:
        return None
    bgm = battle.battle_config.audio.bgm
    if bgm is None:
        return None
    return bgm.track_id or None


# ============================================================
# Profile loader
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
# Enemy player construction (internal helper)
# ============================================================

async def _build_enemy_player(
    session: AsyncSession,
    game: Game,
    seat: int = 1,
    color: str = "red",
) -> Player:
    """Build + persist one AI Player (units spawned later by helper).

    The unit spawning itself is delegated to ``_start_battle_internal``,
    which reads each map's ``initial_units`` field to seed both players
    in a single, transactional pass.
    """
    # P0.5 — AI gets the same starting gold as the human so the first
    # turn is fair (both can recruit a swordsman on turn 1 instead of
    # waiting one cycle for the first income tick).
    ai = build_ai_player(
        game, seat=seat, color=color, name=f"主线敌人-{seat}"
    )
    ai.agent_kind = "rules"
    ai.agent_personality = "aggressive"
    ai.gold = MAINLINE_INITIAL_GOLD
    session.add(ai)
    await session.flush()
    return ai


# ============================================================
# Battle spawn (shared by /start and /next-battle)
# ============================================================

async def _spawn_battle_for_index(
    session: AsyncSession,
    profile: PlayerProfile,
    mainline_id: str,
    battle_index: int,
    *,
    disabled_unit_indices: list[int] | None = None,
) -> tuple[Game, Player, int]:
    """Build + persist the (Game, players, tiles, units) for one battle.

    Returns ``(game, human_player, total_battles)``.
    """
    logger.debug(
        "_spawn_battle_for_index entry: user=%s mainline=%s battle_index=%d",
        profile.user_name, mainline_id, battle_index,
    )
    ml = load_mainline(mainline_id)
    if not (0 <= battle_index < len(ml.battles)):
        logger.warning(
            "_spawn_battle_for_index bad index: user=%s mainline=%s battle_index=%d total=%d",
            profile.user_name, mainline_id, battle_index, len(ml.battles),
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"battle_index {battle_index} out of range for {mainline_id!r}",
        )
    battle = ml.battles[battle_index]
    logger.debug(
        "_spawn_battle_for_index: battle=%s map_id=%s seed=%s",
        battle.id, battle.map_id, battle.map_seed,
    )

    # 1. Create the Game row.
    game = Game(
        name=mainline_game_name(mainline_id, battle.id),
        status="waiting",
        turn_number=1,
        current_player_index=0,
        map_seed=battle.map_seed if battle.map_seed is not None else 0,
        map_preset=battle.map_id,
        battle_config=expand_battle_config(
            battle.battle_config.model_dump(exclude_none=True)
            if battle.battle_config is not None
            else {}
        ),
    )
    session.add(game)
    await session.flush()

    # 2. Create the human player (seat 0, red / map-left).
    #    P0.5 — give the mainline player a starting gold budget so they
    #    can recruit on turn 1 instead of waiting one full cycle for
    #    the first income tick. AI opponent gets the same budget so the
    #    economy stays symmetric (both can make one recruit at start).
    human = Player(
        game_id=game.id,
        user_name=profile.user_name,
        color="red",
        seat=0,
        is_ai=False,
        gold=int(ml.mercenary_balance.starting_fund),
        commander_id=(profile.mainline_commanders or {}).get(mainline_id),
    )
    human.co_state = {
        "commander_id": human.commander_id,
        "meter": 0,
        "threshold": get_power_threshold(human.commander_id),
        "is_power_active": False,
        "last_start_turn": -1,
    }
    session.add(human)
    await session.flush()

    # 3. Create the AI enemy (seat 1, blue / map-right) — units spawn in step 4.
    ai = await _build_enemy_player(session, game, seat=1, color="blue")
    ai.commander_id = battle.enemy_commander
    ai.co_state = {
        "commander_id": ai.commander_id,
        "meter": 0,
        "threshold": get_power_threshold(ai.commander_id),
        "is_power_active": False,
        "last_start_turn": -1,
    }

    # 4. Spawn tiles + units via the shared helper. P2.6 — units are
    # driven by the map's initial_units JSON, not caller-supplied rosters.
    # The colors listed in `battle.teams` are matched to player.color
    # inside `_start_battle_internal`, so the map's initial_units for
    # each color are automatically assigned to the right seat.
    #
    # P2.6+ — collect hero overrides from mainline.starting_units.
    # The mainline JSON's `starting_units[]` is finally the place
    # where named characters (e.g. "云") can be wired in: each
    # entry with a `hero_id` is converted to an override dict the
    # spawn helper understands.  `color` is taken from the entry
    # (falls back to "red" for the human's roster), and
    # `(x, y)` is passed through if the mainline author wants to
    # pin the hero to a specific map tile.
    hero_overrides: List[Dict] = []
    svc = ProgressionService(session)
    for spec in ml.starting_units:
        if not spec.hero_id:
            continue
        override_color = spec.color or "red"
        campaign_spawn = None
        if override_color == human.color:
            stored_state = await svc.get_hero_campaign_state(
                profile.user_name,
                spec.hero_id,
            )
            if stored_state is None:
                initial_state = build_initial_campaign_state(spec.hero_id)
                stored_state = hero_campaign_state_to_dict(initial_state)
                await svc.set_hero_campaign_state(
                    profile.user_name,
                    spec.hero_id,
                    stored_state,
                )
            campaign_spawn = build_campaign_spawn_payload(
                hero_campaign_state_from_dict(stored_state)
            )
        # When the mainline supplies a class_id that doesn't match
        # the hero's base_class_id, the UnitSpec validator already
        # rejected it; here we can trust the pairing.
        hero_overrides.append({
            "color": override_color,
            "x": spec.x,
            "y": spec.y,
            "hero_id": spec.hero_id,
            "name": spec.name,
            "campaign_state": campaign_spawn,
        })
    if hero_overrides:
        logger.info(
            "mainline spawn: applying %d hero override(s): %s",
            len(hero_overrides),
            [ov["hero_id"] for ov in hero_overrides],
        )
    extra_spawn_overrides = _build_disabled_unit_spawn_overrides(
        ml,
        battle,
        disabled_unit_indices,
    )
    battle_spawn_overrides = (
        battle.spawn_overrides.model_dump(exclude_none=True)
        if battle.spawn_overrides is not None
        else None
    )
    merged_spawn_overrides = {
        "remove": [
            *((battle_spawn_overrides or {}).get("remove") or []),
            *((extra_spawn_overrides or {}).get("remove") or []),
        ],
        "replace": list((battle_spawn_overrides or {}).get("replace") or []),
        "add": list((battle_spawn_overrides or {}).get("add") or []),
    }
    if not merged_spawn_overrides["remove"] and not merged_spawn_overrides["replace"] and not merged_spawn_overrides["add"]:
        merged_spawn_overrides = None

    await _start_battle_internal(
        session,
        game,
        [human, ai],
        map_preset=battle.map_id,
        map_seed=battle.map_seed,
        hero_overrides=hero_overrides or None,
        spawn_overrides=merged_spawn_overrides,
    )

    # Commander points strengthen only generic mercenaries.  Hero Units keep
    # their own campaign snapshot and equipment path, so they are excluded.
    allocation = _load_allocation_from_profile(profile)
    allocation.total_points = int(ml.mercenary_balance.total_points)
    _balance, rules = _build_mercenary_policy(ml)
    human_units = (await session.execute(
        select(Unit).where(Unit.player_id == human.id)
    )).scalars().all()
    from app.mercenary_domain import apply_allocation_to_unit
    applied_unit_count = 0
    for unit in human_units:
        if unit.hero_id or unit.unit_type not in rules.available_unit_types():
            continue
        if apply_allocation_to_unit(unit, allocation.unit_type_upgrades):
            applied_unit_count += 1

    # Persist the exact, already-validated allocation on the Game.  Recruit
    # actions consume this snapshot so post-start changes to a profile cannot
    # rewrite a battle that is already in progress.
    battle_config = dict(game.battle_config or {})
    battle_config["mercenary"] = {
        "human_player_id": int(human.id),
        "unit_type_upgrades": allocation.unit_type_upgrades,
    }
    game.battle_config = battle_config
    logger.info(
        "mainline mercenary allocation applied: mainline=%s game=%d units=%d",
        mainline_id, game.id, applied_unit_count,
    )

    # 5. Audit log.
    session.add(
        ActionLog(
            game_id=game.id,
            turn_number=game.turn_number,
            player_id=None,
            action_type="mainline_start",
            description=f"主线 {mainline_id} 进入战斗 {battle.id}",
        )
    )

    # Count tiles for a quantified spawn summary. P2.6 — unit counts
    # are determined by the map's initial_units (not the battle spec),
    # so the spawn summary just reports the team-color list per side.
    from sqlalchemy import func as _sa_func
    from app.models import Tile as _Tile
    tile_total = await session.scalar(
        select(_sa_func.count()).select_from(_Tile).where(_Tile.game_id == game.id)
    )
    logger.info(
        "battle spawned: mainline=%s battle=%s game=%d human=%d "
        "teams=%s tiles=%d",
        mainline_id, battle.id, game.id, human.id,
        dict(battle.teams), int(tile_total or 0),
    )
    return game, human, len(ml.battles)


# ============================================================
# GET /mainlines — list
# ============================================================

@router.get("", response_model=List)
async def list_mainlines_endpoint(
    user_name: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Return mainlines for the lobby view.

    Without ``user_name`` this remains a pure all-chapter listing for
    tools and tests. With ``user_name`` the temporary test campaign is
    exposed as a Fire Emblem-style current chapter: only the first
    uncleared test chapter appears.
    """
    logger.debug("list_mainlines entry")
    items = list_mainlines()
    if user_name:
        allowed_test = await _current_test_mainline_for_user(session, user_name)
        items = [
            item for item in items
            if item.id not in TEST_MAINLINE_CHAIN or item.id == allowed_test
        ]
    logger.info("list_mainlines ok: count=%d", len(items))
    return items


# ============================================================
# GET /mainlines/dialogue?path=...
# ============================================================

@router.get("/dialogue")
async def get_dialogue(path: str = Query(...)):
    """Serve a dialogue JSON file by relative path.

    Security:
      * Rejects any path containing ``..`` segments.
      * Resolves the path and verifies it stays inside ``game/``.

    Returns the raw JSON content of the file (a ``{"scenes": [...]}``
    object or whatever the designer authored).
    """
    logger.debug("get_dialogue entry: path=%s", path)
    if ".." in path.split("/"):
        logger.warning("get_dialogue rejected: path=%s reason=traversal", path)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid path"
        )
    base = _GAME_ROOT.resolve()
    candidate = (base / path).resolve()
    # Ensure the resolved path is still under game/.
    try:
        candidate.relative_to(base)
    except ValueError:
        logger.warning("get_dialogue rejected: path=%s reason=escape", path)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid path"
        )
    if not candidate.exists() or not candidate.is_file():
        logger.warning("get_dialogue not found: path=%s", path)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"dialogue not found: {path}"
        )
    try:
        raw = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("get_dialogue read failed: path=%s", path)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"cannot read {path}: {exc}",
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.exception("get_dialogue parse failed: path=%s", path)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"{path} is not valid JSON: {exc}",
        )
    scene_n = 0
    if isinstance(payload, dict) and isinstance(payload.get("scenes"), list):
        scene_n = len(payload["scenes"])
    elif isinstance(payload, list):
        scene_n = len(payload)
    logger.info("get_dialogue ok: path=%s scenes=%d", path, scene_n)
    return payload


# ============================================================
# GET /mainlines/{mainline_id}
# ============================================================

@router.get("/{mainline_id}", response_model=MainlineDetailOut)
async def get_mainline_detail(mainline_id: str) -> MainlineDetailOut:
    """Return full mainline detail (for the lobby detail panel)."""
    logger.debug("get_mainline_detail entry: mainline=%s", mainline_id)
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mainline_detail not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mainline_detail invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    out = MainlineDetailOut(
        id=ml.id,
        title=ml.title,
        synopsis=ml.synopsis,
        cover_art=ml.cover_art,
        required_classes=list(ml.required_classes),
        battle_count=len(ml.battles),
        battles=[
            BattlePreview(
                id=b.id,
                title=b.title,
                win_condition=b.win_condition,
                map_id=b.map_id,
                # P2.9 — surface catalogue metadata per battle so the
                # front-end can render "BGM: <title>" in the lobby
                # detail panel. None when the battle has no BGM or
                # the track_id isn't registered. We deliberately use
                # the battle's track_id (not the registry default) so
                # per-battle overrides show through.
                bgm=BattleBgmMeta.model_validate(
                    battle_bgm_meta(_battle_track_id(b))
                )
                if _battle_track_id(b) else None,
            )
            for b in ml.battles
        ],
        dialogue_keys=list(ml.dialogues.keys()),
    )
    logger.info(
        "get_mainline_detail ok: mainline=%s battles=%d dialogues=%d",
        mainline_id, len(ml.battles), len(ml.dialogues),
    )
    return out


@router.get("/{mainline_id}/prepare", response_model=MainlinePrepareOut)
async def get_mainline_prepare(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlinePrepareOut:
    """Build a read-only pre-battle payload without spawning a Game row."""
    logger.debug(
        "get_mainline_prepare entry: mainline=%s user=%s",
        mainline_id,
        user_name,
    )
    try:
        load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mainline_prepare not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mainline_prepare invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _ensure_profile_or_create(session, user_name)
    await _ensure_test_mainline_unlocked(session, user_name, mainline_id)
    payload = await _build_prepare_payload(session, profile, mainline_id)
    logger.info(
        "get_mainline_prepare ok: mainline=%s user=%s battle=%s heroes=%d",
        mainline_id,
        user_name,
        payload.battle_id,
        len(payload.heroes),
    )
    return payload


@router.post(
    "/{mainline_id}/prepare/promote",
    response_model=MainlinePreparePromoteOut,
)
async def promote_mainline_hero(
    mainline_id: str,
    body: MainlinePreparePromoteRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlinePreparePromoteOut:
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _load_profile(session, body.user_name)
    if getattr(profile, "active_mainline", None) not in (None, mainline_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"profile {body.user_name!r} is active in another mainline",
        )

    hero_ids = {spec.hero_id for spec in ml.starting_units if spec.hero_id}
    if body.hero_id not in hero_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"hero {body.hero_id!r} not found in mainline roster")

    svc = ProgressionService(session)
    stored_state = await svc.get_hero_campaign_state(body.user_name, body.hero_id)
    if stored_state is None:
        stored_state = hero_campaign_state_to_dict(build_initial_campaign_state(body.hero_id))
        await svc.set_hero_campaign_state(body.user_name, body.hero_id, stored_state)
    state = hero_campaign_state_from_dict(stored_state)
    current_class = build_hero_class_template(state.class_id)
    target_class = build_hero_class_template(body.target_class_id)
    inventory = await svc.get_hero_inventory(body.user_name)
    crest_count = int(inventory.get("hero_crest", 0))
    if crest_count <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "hero_crest is required for promotion")
    try:
        promoted_state = promote_hero(state, current_class, target_class)
    except HeroPromotionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    await svc.set_hero_campaign_state(
        body.user_name,
        body.hero_id,
        hero_campaign_state_to_dict(promoted_state),
    )
    updated_inventory = await svc.set_hero_inventory_item(
        body.user_name,
        "hero_crest",
        crest_count - 1,
    )

    return MainlinePreparePromoteOut(
        hero_id=promoted_state.hero_id,
        class_id=promoted_state.class_id,
        level=promoted_state.level,
        promoted=promoted_state.promoted,
        hero_crest_left=int((updated_inventory or {}).get("hero_crest", 0)),
    )


@router.post(
    "/{mainline_id}/prepare/equipment",
    response_model=MainlinePrepareEquipmentOut,
)
async def equip_mainline_hero(
    mainline_id: str,
    body: MainlinePrepareEquipmentRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlinePrepareEquipmentOut:
    """Persist one equipment choice made in the pre-battle preparation view."""
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if body.slot not in EQUIPMENT_SLOTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown equipment slot")
    hero_ids = {spec.hero_id for spec in ml.starting_units if spec.hero_id}
    if body.hero_id not in hero_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"hero {body.hero_id!r} not found in mainline roster")
    profile = await _load_profile(session, body.user_name)
    definition = get_equipment(body.equipment_id)
    if body.equipment_id is not None and (definition is None or definition.slot != body.slot):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "equipment does not match this slot")

    svc = ProgressionService(session)
    inventory = await svc.ensure_hero_equipment_starters(body.user_name)
    if definition is not None and int(inventory.get(definition.item_id, 0)) <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "equipment is not in inventory")
    stored_state = await svc.get_hero_campaign_state(body.user_name, body.hero_id)
    if stored_state is None:
        stored_state = hero_campaign_state_to_dict(build_initial_campaign_state(body.hero_id))
    state = hero_campaign_state_from_dict(stored_state)

    # An inventory item can be equipped by only one hero at a time.
    if definition is not None:
        equipped_elsewhere = 0
        all_states = dict(getattr(profile, "hero_campaign_states", {}) or {})
        for hero_id, raw_state in all_states.items():
            if hero_id != body.hero_id and definition.item_id in (raw_state.get("equipment") or {}).values():
                equipped_elsewhere += 1
        if equipped_elsewhere >= int(inventory.get(definition.item_id, 0)):
            raise HTTPException(status.HTTP_409_CONFLICT, "equipment is already equipped by another hero")
    equipment = dict(state.equipment)
    equipment[body.slot] = body.equipment_id
    state.equipment = equipment
    state.equipment_initialized = True
    await svc.set_hero_campaign_state(body.user_name, body.hero_id, hero_campaign_state_to_dict(state))
    return MainlinePrepareEquipmentOut(
        hero_id=state.hero_id,
        equipment=equipment,
        equipment_bonuses=equipped_stat_bonuses(equipment),
    )


@router.get("/{mainline_id}/shop", response_model=MainlineShopOut)
async def get_post_battle_shop(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlineShopOut:
    """Return the JSON-authored post-battle stock and campaign gold."""
    try:
        load_mainline(mainline_id)
        items = load_shop("post_battle")
    except (MainlineNotFound, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    profile = await _load_profile(session, user_name)
    return MainlineShopOut(
        mainline_id=mainline_id,
        gold=int(profile.gold),
        items=[item.payload() for item in items],
    )


@router.post(
    "/{mainline_id}/shop/purchase",
    response_model=MainlineShopPurchaseOut,
)
async def purchase_post_battle_shop_item(
    mainline_id: str,
    body: MainlineShopPurchaseRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineShopPurchaseOut:
    try:
        load_mainline(mainline_id)
        stock_ids = {item.item_id for item in load_shop("post_battle")}
    except (MainlineNotFound, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    item = get_item(body.item_id)
    if item is None or item.item_id not in stock_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item is not sold by this shop")
    svc = ProgressionService(session)
    try:
        result = await svc.purchase_hero_inventory_item(
            body.user_name, item.item_id, unit_price=item.price, quantity=body.quantity,
        )
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "not enough campaign gold")
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    gold_remaining, inventory_count = result
    return MainlineShopPurchaseOut(
        item_id=item.item_id,
        quantity=body.quantity,
        inventory_count=inventory_count,
        gold_remaining=gold_remaining,
    )


# ============================================================
# POST /mainlines/{mainline_id}/prepare/complete
# ============================================================


@router.post(
    "/{mainline_id}/prepare/complete",
    response_model=AutoSaveCheckpointOut,
)
async def complete_prepare(
    mainline_id: str,
    body: PrepCompleteRequest,
    session: AsyncSession = Depends(get_session),
) -> AutoSaveCheckpointOut:
    """Player signals "I'm done prepping — ready to start".

    Triggers an auto-save with label ``f"{mainline_id}-准备"`` so the
    player can later reload to the post-prep / pre-battle state.
    The FE renders "自动存档中…… 自动存档完毕" on success.

    Pre-conditions (matches the FE8 design v2 §2.6 invariants):
      * profile exists
      * mainline is valid
      * the player may prep an inactive mainline too — the
        auto-save then captures them at the *post-prep / pre-start*
        state of an inactive profile, useful for stash-style flow
    """
    logger.debug(
        "complete_prepare entry: user=%s mainline=%s",
        body.user_name, mainline_id,
    )
    try:
        load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _load_profile(session, body.user_name)
    # Persist hero_campaign_states for any heroes in this mainline
    # that haven't been initialised yet, so the auto-save captures
    # a complete snapshot rather than a half-empty one.  This is
    # the same initialisation the /start path performs.
    svc = ProgressionService(session)
    try:
        ml = load_mainline(mainline_id)
        cursor_index = int(
            (profile.mainline_progress or {}).get("battle_index", 0)
        )
        if not (0 <= cursor_index < len(ml.battles)):
            cursor_index = 0
    except Exception:  # pragma: no cover
        cursor_index = 0

    return await auto_save_checkpoint(
        session,
        profile,
        mainline_id=mainline_id,
        chapter_index=cursor_index,
        label=f"{mainline_id}-准备",
    )


# ============================================================
# POST /mainlines/{mainline_id}/start
# ============================================================

# Re-export the request classes from schemas at module-import time so
# the @router decorator below can reference them by name.
from app.mainline.schemas import (  # noqa: E402
    MainlineAbandonRequest,
    MainlineAdvanceRequest,
    MainlineNextBattleRequest,
    MainlinePreparePromoteRequest,
    MainlineStartRequest,
)


@router.post(
    "/{mainline_id}/start",
    response_model=MainlineStartOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_mainline(
    mainline_id: str,
    body: MainlineStartRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineStartOut:
    """Begin a new mainline campaign.

    Validates that ``profile.unlocked_classes`` covers the mainline's
    ``required_classes``, marks the profile as having this mainline
    active (via ``ProgressionService.set_active_mainline``), and
    spawns the first battle (always ``battle_index = 0``).
    """
    logger.debug(
        "mainline_start entry: user_name=%s mainline_id=%s skip_intro=%s",
        body.user_name, mainline_id, body.skip_intro,
    )
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_start not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("mainline_start invalid: user=%s mainline=%s",
                         body.user_name, mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    # Use the auto-create variant for /start: a missing profile here is
    # almost always a stale FE cache (e.g. old `_resolveUserName`
    # fallback like `玩家-${id}`) or a benign race against a concurrent
    # POST /progression/profiles. Always honor the user's intent: click
    # "开始" → 必然进入战斗。 Business endpoints below still use
    # _load_profile (strict 404) so a typo'd user_name never silently
    # creates the wrong profile.
    profile = await _ensure_profile_or_create(session, body.user_name)
    await _ensure_test_mainline_unlocked(session, body.user_name, mainline_id)

    # Class prerequisite check (the mainline declares required_classes).
    unlocked = set(profile.unlocked_classes or [])
    missing = [c for c in ml.required_classes if c not in unlocked]
    if missing:
        logger.warning(
            "mainline_start class check failed: user=%s mainline=%s missing=%s",
            body.user_name, mainline_id, missing,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"profile {body.user_name!r} missing required classes: {missing}",
        )

    # Set active mainline via the progression service. Raises
    # MainlineAlreadyActive if another campaign is in progress
    # (unless ``body.force`` is True, which allows restart of the
    # same mainline after a save load).
    svc = ProgressionService(session)
    # When force=True, also abort any in-flight game for this user
    # so the new battle spawn doesn't leave an orphan.
    if body.force:
        from app.save import SaveService
        save_svc = SaveService(session)
        aborted = await save_svc._abort_in_flight_games(body.user_name)  # noqa: SLF001
        if aborted:
            logger.info(
                "mainline_start force=true aborted in-flight games: "
                "user=%s count=%d",
                body.user_name, aborted,
            )
    try:
        progress_summary = await svc.set_active_mainline(
            body.user_name, mainline_id, force=body.force,
        )
    except MainlineAlreadyActive as exc:
        logger.warning(
            "mainline_start already active: user=%s mainline=%s err=%s",
            body.user_name, mainline_id, exc,
        )
        # Structured 409 so the FE can detect "already active" and auto-retry
        # via /abandon + /start without relying on string matching the message.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "mainline_already_active",
                "user_name": body.user_name,
                "active_mainline": getattr(profile, "active_mainline", None),
                "hint": (
                    f"POST /mainlines/{mainline_id}/abandon first to drop the "
                    f"active campaign, or POST /mainlines/{mainline_id}/start "
                    "with force=true to overwrite"
                ),
            },
        )

    profile.active_mainline = progress_summary.active_mainline
    profile.mainline_progress = dict(progress_summary.mainline_progress)
    await session.flush()

    # Spawn the first battle (always index 0 on /start).
    game, human, total_battles = await _spawn_battle_for_index(
        session, profile, mainline_id, 0,
        disabled_unit_indices=body.disabled_unit_indices,
    )
    profile.active_mainline = progress_summary.active_mainline
    profile.mainline_progress = dict(progress_summary.mainline_progress)
    await session.execute(
        update(PlayerProfile)
        .where(PlayerProfile.user_name == body.user_name)
        .values(
            active_mainline=progress_summary.active_mainline,
            mainline_progress=dict(progress_summary.mainline_progress),
        )
    )
    await session.flush()

    # Determine whether to expose a pre-battle dialogue URL.
    pre_key = ml.battles[0].pre_battle_dialogue
    pre_url = ml.dialogues.get(pre_key) if pre_key else None
    if body.skip_intro:
        pre_url = None
        pre_key = None
    state = "dialogue" if pre_url else "battle"

    logger.info(
        "mainline_start ok: user=%s mainline=%s game=%d battle=%s "
        "battle_index=0 total=%d pre_dlg=%s state=%s",
        body.user_name, mainline_id, game.id, ml.battles[0].id,
        total_battles, pre_key or "-", state,
    )
    audit.info(
        "USER_ACTION | user=%s | action=MAINLINE_START | mainline=%s | "
        "game=%d | result=SUCCESS",
        body.user_name, mainline_id, game.id,
    )

    return MainlineStartOut(
        game_id=game.id,
        player_id=human.id,
        mainline_id=mainline_id,
        battle_id=ml.battles[0].id,
        battle_index=0,
        total_battles=total_battles,
        state=state,
        battle_config=game.battle_config or {},
        pre_battle_dialogue_url=pre_url,
        pre_battle_dialogue_key=pre_key,
        # P2.9 — catalogue metadata for the just-spawned battle so
        # the mainline header can show "BGM: <title> (<category>)".
        bgm_meta=BattleBgmMeta.model_validate(battle_bgm_meta(_battle_track_id(ml.battles[0])))
        if _battle_track_id(ml.battles[0]) else None,
    )


@router.post(
    "/{mainline_id}/advance",
    response_model=MainlineAdvanceOut,
)
async def advance_mainline(
    mainline_id: str,
    body: MainlineAdvanceRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineAdvanceOut:
    """Advance the campaign cursor after a battle finishes.

    Validates that ``game_id`` belongs to this mainline (via the
    naming convention) and that the human won (game.status ==
    "finished"). Returns either the post-battle dialogue URL for the
    current battle OR a VICTORY payload with rewards.
    """
    logger.debug(
        "mainline_advance entry: user_name=%s mainline_id=%s game_id=%d",
        body.user_name, mainline_id, body.game_id,
    )
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_advance not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    profile = await _load_profile(session, body.user_name)

    game = await session.get(Game, body.game_id)
    if game is None:
        logger.warning(
            "mainline_advance game not found: user=%s game_id=%d",
            body.user_name, body.game_id,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")

    parsed = parse_mainline_game_name(game.name)
    if not parsed or parsed[0] != mainline_id:
        logger.warning(
            "mainline_advance game mismatch: user=%s game=%d expected_mainline=%s got=%s",
            body.user_name, body.game_id, mainline_id,
            (parsed[0] if parsed else "?"),
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"game {body.game_id} does not belong to mainline {mainline_id!r}",
        )
    battle_id = parsed[1]

    if game.status != "finished":
        logger.warning(
            "mainline_advance game not finished: user=%s game=%d status=%s",
            body.user_name, body.game_id, game.status,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"game {body.game_id} is not finished (status={game.status!r})",
        )

    # Identify the battle index by id within this mainline.
    battle_index: Optional[int] = None
    for idx, b in enumerate(ml.battles):
        if b.id == battle_id:
            battle_index = idx
            break
    if battle_index is None:
        logger.warning(
            "mainline_advance unknown battle: user=%s game=%d battle=%s",
            body.user_name, body.game_id, battle_id,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"game {body.game_id} references unknown battle {battle_id!r}",
        )

    # Build an engine against the live profile.
    engine = MainlineEngine(session, profile, ml)
    await _persist_mainline_hero_results(session, profile, game.id)

    total_battles = len(ml.battles)
    next_index = battle_index + 1
    is_last = next_index >= total_battles

    # Auto-save at chapter-end (per FE8 design v2 §2.3).  Fires on
    # both the victory path and the next-battle path — the player
    # gets a fresh checkpoint after every settlement so they can
    # always reload to "post-this-battle" state.  The FE uses
    # ``auto_save`` to render "自动存档中…… 自动存档完毕".
    auto_save_out = await auto_save_checkpoint(
        session,
        profile,
        mainline_id=mainline_id,
        chapter_index=next_index,
        label=f"{mainline_id}-结束",
    )
    if is_last:
        rewards = await engine.apply_victory(
            completed_battle=ml.battles[battle_index]
        )
        next_mainline_id = ml.next_mainline_id
        next_mainline_title = None
        if next_mainline_id:
            try:
                next_mainline_title = load_mainline(next_mainline_id).title
            except MainlineNotFound:
                logger.warning(
                    "mainline_advance successor missing: mainline=%s next=%s",
                    mainline_id, next_mainline_id,
                )
                next_mainline_id = None
        logger.info(
            "mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=victory "
            "gold=+%d unlock=%s exp_per_unit=+%d",
            body.user_name, mainline_id, battle_index, next_index,
            rewards.gold or 0, rewards.unlock_class or "-",
            rewards.exp_per_unit or 0,
        )
        audit.info(
            "USER_ACTION | user=%s | action=MAINLINE_ADVANCE | mainline=%s | "
            "battle_index=%d | result=SUCCESS | state=victory",
            body.user_name, mainline_id, next_index,
        )
        return MainlineAdvanceOut(
            state="victory",
            mainline_id=mainline_id,
            battle_index=next_index,
            total_battles=total_battles,
            post_battle_dialogue_url=None,
            post_battle_dialogue_key=None,
            rewards=rewards,
            victory_dialogue_url=ml.dialogues.get("victory"),
            victory_dialogue_key="victory" if ml.dialogues.get("victory") else None,
            next_mainline_id=next_mainline_id,
            next_mainline_title=next_mainline_title,
            auto_save=auto_save_out.model_dump(),
        )

    # Otherwise: advance the cursor and return the post-battle dialogue
    # for the battle we just won (so the frontend can play it before
    # requesting /next-battle).
    battle = ml.battles[battle_index]
    engine.apply_battle_victory(battle)
    post_key = battle.post_battle_dialogue
    post_url = ml.dialogues.get(post_key) if post_key else None

    # Bump the cursor via the service so the JSON column is well-formed.
    # We use next_battle=True here to advance battle_index by 1, AND set
    # the cursor's scene_id to the post_battle_dialogue key (or fall back
    # to the only dialogue key if the battle has no post_battle_dialogue).
    if post_key:
        await engine.mark_scene_done(post_key, next_battle=True)
    else:
        # No post-battle dialogue; just bump the cursor with no scene change.
        await engine.mark_scene_done(
            ml.battles[next_index - 1].pre_battle_dialogue or "intro",
            next_battle=True,
        )

    logger.info(
        "mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=%s post_dlg=%s",
        body.user_name, mainline_id, battle_index, next_index,
        "dialogue" if post_url else "battle", post_key or "-",
    )
    audit.info(
        "USER_ACTION | user=%s | action=MAINLINE_ADVANCE | mainline=%s | "
        "battle_index=%d | result=SUCCESS",
        body.user_name, mainline_id, next_index,
    )

    return MainlineAdvanceOut(
        state="dialogue" if post_url else "battle",
        mainline_id=mainline_id,
        battle_index=next_index,
        total_battles=total_battles,
        post_battle_dialogue_url=post_url,
        post_battle_dialogue_key=post_key,
        rewards=None,
        auto_save=auto_save_out.model_dump(),
    )


# ============================================================
# POST /mainlines/{mainline_id}/next-battle
# ============================================================

@router.post(
    "/{mainline_id}/next-battle",
    response_model=MainlineNextBattleOut,
    status_code=status.HTTP_201_CREATED,
)
async def next_battle_mainline(
    mainline_id: str,
    body: MainlineNextBattleRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineNextBattleOut:
    """Spawn the next battle after the post-battle dialogue has been played.

    Reads ``profile.mainline_progress.battle_index`` to determine which
    battle to spawn; advances the cursor on success.
    """
    logger.debug(
        "mainline_next_battle entry: user_name=%s mainline_id=%s",
        body.user_name, mainline_id,
    )
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_next_battle not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    profile = await _load_profile(session, body.user_name)

    if getattr(profile, "active_mainline", None) != mainline_id:
        logger.warning(
            "mainline_next_battle wrong active: user=%s expected=%s got=%s",
            body.user_name, mainline_id,
            getattr(profile, "active_mainline", None),
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"profile {body.user_name!r} has no active mainline {mainline_id!r}",
        )

    engine = MainlineEngine(session, profile, ml)
    next_idx = engine.current_battle_index
    if not (0 <= next_idx < len(ml.battles)):
        logger.warning(
            "mainline_next_battle cleared: user=%s mainline=%s next_idx=%d total=%d",
            body.user_name, mainline_id, next_idx, len(ml.battles),
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no next battle available (campaign already cleared)",
        )

    game, human, total_battles = await _spawn_battle_for_index(
        session, profile, mainline_id, next_idx,
        disabled_unit_indices=body.disabled_unit_indices,
    )

    pre_key = ml.battles[next_idx].pre_battle_dialogue
    pre_url = ml.dialogues.get(pre_key) if pre_key else None

    logger.info(
        "mainline_next_battle ok: user=%s mainline=%s game=%d "
        "battle_index=%d/%d pre_dlg=%s",
        body.user_name, mainline_id, game.id, next_idx, total_battles, pre_key or "-",
    )
    audit.info(
        "USER_ACTION | user=%s | action=MAINLINE_NEXT_BATTLE | mainline=%s | "
        "battle_index=%d | game=%d | result=SUCCESS",
        body.user_name, mainline_id, next_idx, game.id,
    )

    return MainlineNextBattleOut(
        game_id=game.id,
        player_id=human.id,
        mainline_id=mainline_id,
        battle_id=ml.battles[next_idx].id,
        battle_index=next_idx,
        total_battles=total_battles,
        state="dialogue" if pre_url else "battle",
        battle_config=game.battle_config or {},
        pre_battle_dialogue_url=pre_url,
        pre_battle_dialogue_key=pre_key,
        bgm_meta=BattleBgmMeta.model_validate(battle_bgm_meta(_battle_track_id(ml.battles[next_idx])))
        if _battle_track_id(ml.battles[next_idx]) else None,
    )


# ============================================================
# POST /mainlines/{mainline_id}/abandon
# ============================================================

@router.post(
    "/{mainline_id}/abandon",
    response_model=MainlineAbandonOut,
)
async def abandon_mainline(
    mainline_id: str,
    body: MainlineAbandonRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineAbandonOut:
    """Drop the active mainline (if any) without finishing it.

    Idempotent: if no campaign is active, returns ``ok=True`` with no
    abandoned_at timestamp.
    """
    logger.debug(
        "mainline_abandon entry: user_name=%s mainline_id=%s",
        body.user_name, mainline_id,
    )
    # Touch the loader so an invalid id yields 404 even when the
    # profile has nothing active.
    try:
        load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_abandon not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    profile = await _load_profile(session, body.user_name)
    active = getattr(profile, "active_mainline", None)

    abandoned_at: Optional[str] = None
    was_active = active == mainline_id
    if was_active:
        engine = MainlineEngine(session, profile, load_mainline(mainline_id))
        await engine.abandon()
        abandoned_at = utcnow_iso()

    logger.info(
        "mainline_abandon ok: user=%s mainline=%s was_active=%s abandoned_at=%s",
        body.user_name, mainline_id, was_active, abandoned_at or "-",
    )
    audit.info(
        "USER_ACTION | user=%s | action=MAINLINE_ABANDON | mainline=%s | "
        "was_active=%s | result=SUCCESS",
        body.user_name, mainline_id, was_active,
    )

    return MainlineAbandonOut(
        ok=True,
        mainline_id=mainline_id if was_active else None,
        abandoned_at=abandoned_at,
    )


# ============================================================
# Mercenary domain endpoints (dual-track phase 3)
# ============================================================


def _build_mercenary_policy(ml):
    """Build the server-authoritative allocation policy from mainline JSON."""
    from app.mercenary_domain import (
        ChapterBalanceConfig,
        DEFAULT_UPGRADE_RULES,
        MercenaryAllocationRules,
        UpgradeRule,
    )

    config = ml.mercenary_balance
    balance = ChapterBalanceConfig(starting_fund=int(config.starting_fund))
    configured_rules = {
        stat: UpgradeRule(
            point_cost=int(rule.point_cost), max_bonus=int(rule.max_bonus),
        )
        for stat, rule in config.stat_rules.items()
    }
    return balance, MercenaryAllocationRules(
        stat_rules=configured_rules or dict(DEFAULT_UPGRADE_RULES),
        allowed_unit_types=(
            frozenset(config.allowed_unit_types)
            if config.allowed_unit_types is not None
            else None
        ),
    )


def _load_allocation_from_profile(
    profile: PlayerProfile,
) -> "CommanderAllocation":
    """Read ``profile.mercenary_roster_state`` into a fresh
    ``CommanderAllocation`` (or a default if absent).

    The chapter determines which part of this shared commander allocation
    can be spent; no client-controlled value participates in pricing.
    """
    from app.mercenary_domain import CommanderAllocation
    stored = dict(getattr(profile, "mercenary_roster_state", {}) or {})
    alloc_payload = dict(stored.get("allocation") or {})
    allocation = CommanderAllocation(
        total_points=int(alloc_payload.get("total_points", 100)),
        spent_points=int(alloc_payload.get("spent_points", 0)),
        unit_type_upgrades={
            str(ut): dict(stats)
            for ut, stats in (alloc_payload.get("unit_type_upgrades") or {}).items()
        },
    )
    return allocation


async def _save_allocation_to_profile(
    session: AsyncSession,
    profile: PlayerProfile,
    allocation: "CommanderAllocation",
) -> None:
    """Write the allocation back into the JSON column on the profile.

    The dataclass ``unit_type_upgrades`` keys must round-trip as
    ``str``; SQLAlchemy's JSON type may coerce them, so we re-wrap
    here.
    """
    stored = dict(getattr(profile, "mercenary_roster_state", {}) or {})
    stored["allocation"] = {
        "total_points": int(allocation.total_points),
        "spent_points": int(allocation.spent_points),
        "unit_type_upgrades": {
            str(ut): {str(stat): int(value) for stat, value in stats.items()}
            for ut, stats in allocation.unit_type_upgrades.items()
        },
    }
    profile.mercenary_roster_state = stored
    await session.flush()


@router.get(
    "/{mainline_id}/mercenary/config",
    response_model=MainlineMercenaryConfigOut,
)
async def get_mercenary_config(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlineMercenaryConfigOut:
    """Return the chapter's balance config + the player's allocation.

    Auto-creates the profile on miss (mirrors ``/start``) so a fresh
    player can open the panel without a 404 round-trip.
    """
    logger.debug(
        "get_mercenary_config entry: mainline=%s user=%s",
        mainline_id, user_name,
    )
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mercenary_config not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mercenary_config invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    profile = await _ensure_profile_or_create(session, user_name)
    allocation = _load_allocation_from_profile(profile)
    allocation.total_points = int(ml.mercenary_balance.total_points)
    balance, rules = _build_mercenary_policy(ml)
    return MainlineMercenaryConfigOut(
        mainline_id=mainline_id,
        balance=ChapterBalanceConfigOut(
            enemy_modifiers=dict(balance.enemy_modifiers),
            max_recruit_count=int(balance.max_recruit_count),
            starting_fund=int(balance.starting_fund),
            total_points=int(ml.mercenary_balance.total_points),
            allowed_unit_types=sorted(rules.available_unit_types()),
            stat_rules={
                stat: {
                    "point_cost": int(rule.point_cost),
                    "max_bonus": int(rule.max_bonus),
                }
                for stat, rule in rules.stat_rules.items()
            },
        ),
        allocation=CommanderAllocationOut(
            total_points=int(allocation.total_points),
            spent_points=int(allocation.spent_points),
            unit_type_upgrades={
                str(ut): {str(stat): int(value) for stat, value in stats.items()}
                for ut, stats in allocation.unit_type_upgrades.items()
            },
        ),
        mercenary_points=int(allocation.total_points - allocation.spent_points),
    )


@router.post(
    "/{mainline_id}/mercenary/allocate",
    response_model=MainlineMercenaryAllocateOut,
)
async def allocate_mercenary_points(
    mainline_id: str,
    body: MainlineMercenaryAllocateRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineMercenaryAllocateOut:
    """Spend mercenary points on a per-unit-type stat upgrade.

    Validates the point cost against the player's remaining budget,
    writes the upgrade into the profile's
    ``mercenary_roster_state.allocation``, and returns the new state.

    This is the dual-track "pre-battle" panel; the *application* of
    these upgrades to spawned ``Unit`` rows is a follow-up wiring
    step (Task #1 phase 2).
    """
    logger.debug(
        "allocate_mercenary_points entry: mainline=%s user=%s unit_type=%s stat=%s",
        mainline_id, body.user_name, body.unit_type, body.stat,
    )
    try:
        ml = load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning(
            "allocate_mercenary_points not found: mainline=%s", mainline_id,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception(
            "allocate_mercenary_points invalid: mainline=%s", mainline_id,
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    # Strict 404: a typo'd user_name must not auto-create a wrong
    # profile (mirrors /advance, /abandon).
    profile = await _load_profile(session, body.user_name)
    allocation = _load_allocation_from_profile(profile)
    allocation.total_points = int(ml.mercenary_balance.total_points)
    _balance, rules = _build_mercenary_policy(ml)

    try:
        from app.mercenary_domain import apply_commander_upgrade
        receipt = apply_commander_upgrade(
            allocation,
            unit_type=body.unit_type,
            stat=body.stat,
            value=body.value,
            rules=rules,
        )
    except ValueError as exc:
        logger.warning(
            "allocate_mercenary_points rejected: user=%s reason=%s",
            body.user_name, exc,
        )
        status_code = (
            status.HTTP_409_CONFLICT
            if "points exceeded" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code, str(exc))

    await _save_allocation_to_profile(session, profile, allocation)
    logger.info(
        "allocate_mercenary_points ok: user=%s unit_type=%s stat=%s "
        "value=%d cost=%d spent=%d",
        body.user_name, body.unit_type, body.stat,
        body.value, receipt.cost, allocation.spent_points,
    )
    return MainlineMercenaryAllocateOut(
        ok=True,
        spent_points=int(allocation.spent_points),
        remaining_points=int(
            allocation.total_points - allocation.spent_points
        ),
        unit_type_upgrades={
            str(ut): {str(stat): int(value) for stat, value in stats.items()}
            for ut, stats in allocation.unit_type_upgrades.items()
        },
    )


__all__ = ["router"]
