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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.game_logic import build_ai_player, castle_positions
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
    BattlePreview,
    MainlineAbandonOut,
    MainlineAdvanceOut,
    MainlineDetailOut,
    MainlineNextBattleOut,
    MainlineStartOut,
)
from app.models import ActionLog, Game, Player, Unit
from app.progression import (
    MainlineAlreadyActive,
    NoActiveMainline,
    PlayerProfile,
    ProfileNotFound,
    ProgressionService,
)
from app.routes.game import _start_battle_internal

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

    The unit spawning itself is delegated to ``_start_battle_internal``
    via the ``rosters_by_seat`` parameter so both players get their
    respective rosters in a single, transactional pass.
    """
    ai = build_ai_player(
        game, seat=seat, color=color, name=f"主线敌人-{seat}"
    )
    ai.agent_kind = "rules"
    ai.agent_personality = "aggressive"
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
        "_spawn_battle_for_index: battle=%s map_preset=%s seed=%s",
        battle.id, battle.map_preset, battle.map_seed,
    )

    # 1. Create the Game row.
    game = Game(
        name=mainline_game_name(mainline_id, battle.id),
        status="waiting",
        turn_number=1,
        current_player_index=0,
        map_seed=battle.map_seed if battle.map_seed is not None else 0,
        map_preset=battle.map_preset,
        unit_composition=None,
    )
    session.add(game)
    await session.flush()

    # 2. Create the human player (seat 0, blue).
    human = Player(
        game_id=game.id,
        user_name=profile.user_name,
        color="blue",
        seat=0,
        is_ai=False,
    )
    session.add(human)
    await session.flush()

    # 3. Create the AI enemy (seat 1, red) — units spawn in step 4.
    ai = await _build_enemy_player(session, game, seat=1, color="red")

    # 4. Spawn tiles + per-seat unit rosters via the shared helper.
    await _start_battle_internal(
        session,
        game,
        [human, ai],
        map_preset=battle.map_preset,
        map_seed=battle.map_seed,
        rosters_by_seat={
            0: dict(battle.ally_composition),
            1: dict(battle.enemy_composition),
        },
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

    # Count units + tiles for a quantified spawn summary.
    ally_units = sum(int(v) for v in (battle.ally_composition or {}).values())
    enemy_units = sum(int(v) for v in (battle.enemy_composition or {}).values())
    from sqlalchemy import func as _sa_func
    from app.models import Tile as _Tile
    tile_total = await session.scalar(
        select(_sa_func.count()).select_from(_Tile).where(_Tile.game_id == game.id)
    )
    logger.info(
        "battle spawned: mainline=%s battle=%s game=%d human=%d "
        "ally_units=%d enemy_units=%d tiles=%d",
        mainline_id, battle.id, game.id, human.id,
        ally_units, enemy_units, int(tile_total or 0),
    )
    return game, human, len(ml.battles)


# ============================================================
# GET /mainlines — list
# ============================================================

@router.get("", response_model=List)
async def list_mainlines_endpoint():
    """Return all mainlines (lobby view). Pure passthrough to loader."""
    logger.debug("list_mainlines entry")
    items = list_mainlines()
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
                map_preset=b.map_preset,
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


# ============================================================
# POST /mainlines/{mainline_id}/start
# ============================================================

# Re-export the request classes from schemas at module-import time so
# the @router decorator below can reference them by name.
from app.mainline.schemas import (  # noqa: E402
    MainlineAbandonRequest,
    MainlineAdvanceRequest,
    MainlineNextBattleRequest,
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
    # MainlineAlreadyActive if another campaign is in progress.
    svc = ProgressionService(session)
    try:
        await svc.set_active_mainline(body.user_name, mainline_id)
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

    await session.flush()
    await session.refresh(profile)

    # Spawn the first battle (always index 0 on /start).
    game, human, total_battles = await _spawn_battle_for_index(
        session, profile, mainline_id, 0
    )

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
        pre_battle_dialogue_url=pre_url,
        pre_battle_dialogue_key=pre_key,
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

    total_battles = len(ml.battles)
    next_index = battle_index + 1
    is_last = next_index >= total_battles

    if is_last:
        rewards = await engine.apply_victory()
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
        )

    # Otherwise: advance the cursor and return the post-battle dialogue
    # for the battle we just won (so the frontend can play it before
    # requesting /next-battle).
    battle = ml.battles[battle_index]
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
        session, profile, mainline_id, next_idx
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
        pre_battle_dialogue_url=pre_url,
        pre_battle_dialogue_key=pre_key,
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


__all__ = ["router"]
