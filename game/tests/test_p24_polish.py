"""P2.4 polish — tests for the bundled consistency fixes.

Covers:
- 3-player procedural presets exist and are correctly categorised
- Snow biome contains zero TERRAIN_MOUNTAIN (pure-snow)
- All handcrafted maps have a `recommended_players` field
- `notes` field round-trips through the preset schema
- Universal rout fires regardless of game.win_condition
- Defend-mode at the target turn still reports "defend" reason
- reach_*/defend_* maps carry a warning note about the lack of
  well-designed mission maps (NOT "deprecated" — engine still
  supports the modes, the UI selector just doesn't expose them
  because no balanced mission map exists yet)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import (
    MAP_STYLES, STYLE_SNOW_OUTER, TERRAIN_MOUNTAIN, TERRAIN_SNOW_PEAK,
)
from app.game_logic import check_win_condition, generate_map
from app.models import Game, Player, Tile, Unit
from app.schemas import PresetInfo

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


# ============================================================
# 3-player procedural presets
# ============================================================

def test_3p_presets_exist_for_all_outer_styles():
    """Each outer style should now have a *_3p.json preset (P2.4
    polish). The 3p category in the lobby used to be empty.

    castle_internal is intentionally excluded in P2.6+ — that style
    has no hand-authored JSON files because every tile is a castle
    sub-feature and designers don't author them by hand."""
    outer_styles = ["grass_outer", "snow_outer", "desert_outer",
                    "compact_outer"]
    for style in outer_styles:
        matches = list(MAPS_DIR.glob(f"{style}_*_3p.json"))
        assert matches, f"no *_3p.json found for style={style}"


def test_3p_preset_has_recommended_players_3():
    """Each procedural 3p preset must declare recommended_players: 3
    so the lobby's cascade filter buckets it under the 3p category."""
    for p in MAPS_DIR.glob("*_3p.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data.get("recommended_players") == 3, (
            f"{p.name} should declare recommended_players=3"
        )


def test_3p_preset_generates_3_castles():
    """Sanity: a 3p procedural map must spawn exactly 3 castle tiles
    in the requested grid (one per HQ)."""
    grid = generate_map(seed=42, num_castles=3, style="grass_outer", size=15)
    from app.config import TERRAIN_CASTLE
    castle_count = sum(1 for row in grid for t in row if t.terrain == TERRAIN_CASTLE)
    assert castle_count == 3, f"expected 3 castles, got {castle_count}"


# ============================================================
# Snow biome purity
# ============================================================

def test_snow_outer_has_no_terrain_mountain_weight():
    """The snow biome is now PURE-snow. The weight table must not
    include TERRAIN_MOUNTAIN — only TERRAIN_SNOW_PEAK for peaks."""
    weights = MAP_STYLES[STYLE_SNOW_OUTER]["weights"]
    assert TERRAIN_MOUNTAIN not in weights, (
        "snow_outer still references TERRAIN_MOUNTAIN"
    )
    assert TERRAIN_SNOW_PEAK in weights
    # And the snow_peak weight should be reasonable (≥10, so the
    # biome still has visible silver peaks).
    assert weights[TERRAIN_SNOW_PEAK] >= 10


def test_snow_outer_generated_map_never_has_mountain():
    """Across many seeds, a snow_outer map must never emit a
    TERRAIN_MOUNTAIN tile (snow_peak is the only peak type)."""
    for seed in range(20):
        g = generate_map(seed=seed, num_castles=2,
                         style=STYLE_SNOW_OUTER, size=20)
        for row in g:
            for t in row:
                assert t.terrain != TERRAIN_MOUNTAIN, (
                    f"snow_outer seed={seed} emitted TERRAIN_MOUNTAIN"
                )


# ============================================================
# Handcrafted maps have metadata
# ============================================================

def test_all_handcrafted_maps_have_recommended_players():
    """P2.4 polish — every handcrafted map JSON must declare its
    recommended player count. Maps without this field used to fall
    back to 4p, causing the miscategorisation the user reported."""
    auto_prefixes = ("castle_internal_", "grass_outer_", "snow_outer_",
                     "desert_outer_", "compact_outer_")
    for p in MAPS_DIR.glob("*.json"):
        if p.name.startswith(auto_prefixes) or p.name == "classic.json":
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        rec = data.get("recommended_players")
        assert rec in (2, 3, 4), (
            f"{p.name} has invalid recommended_players={rec!r}"
        )


def test_recommended_players_matches_map_size():
    """Cross-check: small 15×15 classics should be 2p, 20×20 should
    be 4p. Loose heuristic — just ensure the basics for the new
    hand-authored balanced maps."""
    cases = [
        ("balanced_2p_15.json", 2),
        ("balanced_3p_15.json", 3),
        ("balanced_4p_20.json", 4),
    ]
    for fname, expected in cases:
        data = json.loads((MAPS_DIR / fname).read_text(encoding="utf-8"))
        assert data.get("recommended_players") == expected, (
            f"{fname}: expected {expected}, got {data.get('recommended_players')}"
        )


# ============================================================
# PresetInfo.notes field
# ============================================================

def test_preset_info_accepts_notes():
    """The schema's `notes` field is optional and free-form."""
    p = PresetInfo(
        id="x", name="X", description="d", notes="hello world"
    )
    assert p.notes == "hello world"


def test_preset_info_notes_optional():
    p = PresetInfo(id="x", name="X", description="d")
    assert p.notes is None


def test_reach_and_defend_maps_carry_warning_note():
    """reach_*/defend_* maps carry a "⚠️" warning in their `notes`
    field — the warning says the map was DESIGNED for that mode but
    no well-designed mission map is exposed in the UI yet. The
    engine still fully supports both modes; they're just not in the
    create-game selector. (P2.4 polish — refactored away from the
    earlier "deprecated" wording after user clarification.)"""
    for p in MAPS_DIR.glob("*.json"):
        if not (p.name.startswith("reach_") or p.name.startswith("defend_")):
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        notes = data.get("notes", "")
        assert "⚠" in notes, (
            f"{p.name} missing warning note (no-mission-map-yet)"
        )
        # Sanity: the warning should NOT say "已弃用" (deprecated)
        # — the engine still works, the maps just don't have a
        # well-designed mission flavour yet.
        assert "已弃用" not in notes, (
            f"{p.name} still uses '已弃用' wording — should be "
            "'暂无理想的任务关卡' (P2.4 polish fix)"
        )


# ============================================================
# Universal win condition
# ============================================================

async def _make_two_player_game(db_session, win_condition="rout"):
    game = Game(
        name="uni-rout", status="playing", map_seed=0,
        map_preset="classic", turn_number=5,
        current_player_index=0, phase="player",
        win_condition=win_condition,
    )
    db_session.add(game)
    await db_session.flush()
    players = []
    for i, color in enumerate(("red", "blue")):
        p = Player(
            game_id=game.id, user_name=f"P{i}", color=color,
            seat=i, is_alive=True, has_ended_turn=False,
            is_ai=False, agent_kind="rules", agent_personality="balanced",
            team_id=color,
        )
        db_session.add(p)
        await db_session.flush()
        players.append(p)
    return game, players


async def _add_unit(db_session, game, player, x, y, alive=True):
    u = Unit(
        player_id=player.id, unit_type="swordsman", name=f"{player.user_name}-u",
        level=1, exp=0, hp=45 if alive else 0, max_hp=45,
        atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0,
        x=x, y=y, has_acted=False, has_moved=False, skills=[],
    )
    db_session.add(u)
    await db_session.flush()
    tile = (await db_session.execute(
        select(Tile).where(Tile.game_id == game.id, Tile.x == x, Tile.y == y)
    )).scalars().first()
    if tile is None:
        tile = Tile(game_id=game.id, x=x, y=y, terrain="plain")
        db_session.add(tile)
        await db_session.flush()
    tile.occupied_unit_id = u.id
    return u


@pytest.mark.asyncio
async def test_universal_rout_fires_for_seize_mode(db_session, tmp_db_path):
    """P2.4 polish — even when win_condition='seize', the rout
    check (last team alive) must still fire and end the game."""
    game, players = await _make_two_player_game(db_session, win_condition="seize")
    u0 = await _add_unit(db_session, game, players[0], 0, 0)
    await _add_unit(db_session, game, players[1], 5, 5)
    # Kill player 0's unit -> only blue alive -> rout
    u0.hp = 0
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.win_reason == "rout"
    assert game.status == "finished"


@pytest.mark.asyncio
async def test_universal_rout_fires_for_reach_mode(db_session, tmp_db_path):
    """Even when win_condition='reach', the rout check still fires
    if only one team is alive."""
    game, players = await _make_two_player_game(db_session, win_condition="reach")
    u0 = await _add_unit(db_session, game, players[0], 0, 0)
    await _add_unit(db_session, game, players[1], 5, 5)
    u0.hp = 0
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.win_reason == "rout"


@pytest.mark.asyncio
async def test_defend_target_turn_keeps_defend_reason(db_session, tmp_db_path):
    """Defend mode at the target turn: the rout check fires but the
    reason is preserved as 'defend' (not overwritten to 'rout') so
    the win banner and analytics keep the original semantic."""
    game, players = await _make_two_player_game(db_session, win_condition="defend")
    game.defend_turns = 5
    game.turn_number = 5
    u0 = await _add_unit(db_session, game, players[0], 0, 0)
    await _add_unit(db_session, game, players[1], 5, 5)
    u0.hp = 0
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.status == "finished"
    assert game.win_reason == "defend"


@pytest.mark.asyncio
async def test_defend_continues_before_target_turn(db_session, tmp_db_path):
    """Defend mode before the target turn with 2 teams alive: game
    continues even if the rout check is otherwise triggered."""
    game, players = await _make_two_player_game(db_session, win_condition="defend")
    game.defend_turns = 10
    game.turn_number = 5  # not yet at the target
    await _add_unit(db_session, game, players[0], 0, 0)
    await _add_unit(db_session, game, players[1], 5, 5)
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is False
    assert game.status == "playing"
