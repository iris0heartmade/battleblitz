"""Battle lifecycle endpoints — start, advance, next-battle, abandon.

Endpoints owned here:
  * POST /mainlines/{mainline_id}/start       — :func:`start_mainline`
  * POST /mainlines/{mainline_id}/advance     — :func:`advance_mainline`
  * POST /mainlines/{mainline_id}/next-battle — :func:`next_battle_mainline`
  * POST /mainlines/{mainline_id}/abandon     — :func:`abandon_mainline`

Plus the heavy internal helpers used by /start and /next-battle:
  * :func:`_spawn_battle_for_index` — builds + persists the (Game,
    players, tiles, units) for one battle
  * :func:`_build_enemy_player` — AI opponent builder
  * :func:`_build_disabled_unit_spawn_overrides` — map preset mutator
    for the ``disabled_unit_indices`` knob.

The mercenary helpers live in :mod:`.mercenary`; this module imports
them directly because :func:`_spawn_battle_for_index` applies the
player's commander-points allocation to freshly-spawned units.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.battle_config import battle_bgm_meta, expand_battle_config
from app.commanders.registry import get_power_threshold
from app.config import MAINLINE_INITIAL_GOLD
from app.database import get_session
from app.events import GameEvent, bus
from app.game_logic import MAP_PRESETS, build_ai_player
from app.hero_domain import (
    build_campaign_spawn_payload,
    build_initial_campaign_state,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)
from app.mainline import MainlineNotFound
from app.mainline.engine import (
    MainlineEngine,
    mainline_game_name,
    parse_mainline_game_name,
    utcnow_iso,
)
from app.mainline.schemas import (
    BattleBgmMeta,
    MainlineAbandonOut,
    MainlineAbandonRequest,
    MainlineAdvanceOut,
    MainlineAdvanceRequest,
    MainlineNextBattleOut,
    MainlineNextBattleRequest,
    MainlineStartOut,
    MainlineStartRequest,
)
from app.mainline.spawn_overrides import apply_spawn_overrides
from app.models import ActionLog, Game, Player, Tile, Unit
from app.progression import (
    MainlineAlreadyActive,
    ProgressionService,
)
from app.progression.models import PlayerProfile
from app.routes.save import auto_save_checkpoint
from app.routes.game import _start_battle_internal
from sqlalchemy import func as _sa_func

from ._common import (
    _battle_track_id,
    _ensure_profile_or_create,
    _ensure_test_mainline_unlocked,
    _load_profile,
    _persist_mainline_hero_results,
)
from .mercenary import (
    _build_mercenary_policy,
    _load_allocation_from_profile,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger("audit.mainline")

# Each submodule carries the full ``/mainlines`` prefix.
router = APIRouter(prefix="/mainlines", tags=["mainline"])


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
# Spawn override helpers
# ============================================================


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
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "_spawn_battle_for_index entry: user=%s mainline=%s battle_index=%d",
        profile.user_name, mainline_id, battle_index,
    )
    ml = mainline_pkg.load_mainline(mainline_id)
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
    tile_total = await session.scalar(
        select(_sa_func.count()).select_from(Tile).where(Tile.game_id == game.id)
    )
    logger.info(
        "battle spawned: mainline=%s battle=%s game=%d human=%d "
        "teams=%s tiles=%d",
        mainline_id, battle.id, game.id, human.id,
        dict(battle.teams), int(tile_total or 0),
    )
    return game, human, len(ml.battles)


# ============================================================
# POST /mainlines/{mainline_id}/start
# ============================================================


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
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "mainline_start entry: user_name=%s mainline_id=%s skip_intro=%s",
        body.user_name, mainline_id, body.skip_intro,
    )
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_start not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except Exception as exc:  # noqa: BLE001 — preserve original error mapping
        logger.exception("mainline_start invalid: user=%s mainline=%s",
                         body.user_name, mainline_id)
        # The original mainline.py caught MainlineValidationError here;
        # keep the public API mapping but accept any other exception as
        # 422 (matches the original semantics for bad mainline data).
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

    # 07-21 F5A: publish match_start
    await bus.publish(GameEvent(
        type="match_start", game_id=game.id, turn=1,
        context={"mainline_id": mainline_id, "user_name": body.user_name},
    ))
    track_id = _battle_track_id(ml.battles[0])
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
        bgm_meta=(
            BattleBgmMeta.model_validate(battle_bgm_meta(track_id))
            if track_id is not None else None
        ),
    )


# ============================================================
# POST /mainlines/{mainline_id}/advance
# ============================================================


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
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "mainline_advance entry: user_name=%s mainline_id=%s game_id=%d",
        body.user_name, mainline_id, body.game_id,
    )
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
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
                next_mainline_title = mainline_pkg.load_mainline(next_mainline_id).title
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
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "mainline_next_battle entry: user_name=%s mainline_id=%s",
        body.user_name, mainline_id,
    )
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
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

    track_id = _battle_track_id(ml.battles[next_idx])
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
        bgm_meta=(
            BattleBgmMeta.model_validate(battle_bgm_meta(track_id))
            if track_id is not None else None
        ),
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
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug(
        "mainline_abandon entry: user_name=%s mainline_id=%s",
        body.user_name, mainline_id,
    )
    # Touch the loader so an invalid id yields 404 even when the
    # profile has nothing active.
    try:
        mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("mainline_abandon not found: user=%s mainline=%s",
                       body.user_name, mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    profile = await _load_profile(session, body.user_name)
    active = getattr(profile, "active_mainline", None)

    abandoned_at: Optional[str] = None
    was_active = active == mainline_id
    if was_active:
        engine = MainlineEngine(session, profile, mainline_pkg.load_mainline(mainline_id))
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
