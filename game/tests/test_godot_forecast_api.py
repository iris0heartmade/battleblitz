"""
Forecast API contract tests for the Godot client.

Target: ``GET /games/{game_id}/forecast-attack`` (07-19 plan Task 3
residual, M4 of the 07-21 plan). The Godot client renders an in-battle
"attack forecast" panel by reading this endpoint before the player
commits a real attack. The test fixtures in
``test_commanders_attack_hook.py`` already exercise the resolved
``attack`` route, but they don't cover the *forecast* route directly,
which is the one the UI depends on.

These tests pin down the four behaviors the FE consumes:

  * the happy path returns a populated ``AttackForecastOut`` with
    consistent `damage` / `target_hp_after` / `is_kill` / `counter_*`
    fields and a non-empty Chinese description;
  * asking for a non-existent game / player / unit returns the same
    4xx the UI has to handle;
  * killing the target sets ``is_kill=true`` and
    ``counter_damage=0`` regardless of any counter logic;
  * a target with a counter-immune skill (``shield``-style) still
    reports ``counter_damage=0`` even when it would otherwise counter.

Where useful the tests monkey-patch ``attack_with_double_strike`` to
make the damage deterministic, the same pattern used in
``test_commanders_attack_hook.py``.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models import Game, Player, Tile, Unit
from app.routes.actions import forecast_attack
from app.schemas import AttackForecastOut


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def forecast_app():
    """Fresh in-memory app + DB; yields an httpx ASGI client + SessionLocal."""
    from app.database import AsyncSessionLocal, Base, dispose_db, engine, init_db

    await init_db()
    transport = ASGITransport(app=_import_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


def _import_app():
    from app.main import app  # imported lazily so the env var is set first
    return app


async def _seed_combat(SessionLocal):
    """Insert one playing game with attacker (red) and defender (blue)."""
    async with SessionLocal() as s:
        game = Game(name="forecast", status="playing", map_seed=1, win_condition="rout")
        s.add(game)
        await s.flush()
        red = Player(
            game_id=game.id, user_name="red", color="red", seat=0,
            co_state={"meter": 0, "threshold": 20},
        )
        blue = Player(
            game_id=game.id, user_name="blue", color="blue", seat=1,
            co_state={"meter": 0, "threshold": 20},
        )
        s.add_all([red, blue])
        await s.flush()
        attacker = Unit(
            player_id=red.id, unit_type="swordsman", name="Knight",
            hp=20, max_hp=20, atk=12, def_=2, matk=0, mdef=0,
            mov=3, mp=3, x=0, y=0, skills=[],
        )
        target = Unit(
            player_id=blue.id, unit_type="archer", name="Bandit",
            hp=10, max_hp=10, atk=8, def_=1, matk=0, mdef=0,
            mov=3, mp=3, x=1, y=0, skills=[],
        )
        s.add_all([attacker, target])
        await s.flush()
        s.add_all([
            Tile(game_id=game.id, x=0, y=0, terrain="plain", occupied_unit_id=attacker.id),
            Tile(game_id=game.id, x=1, y=0, terrain="plain", occupied_unit_id=target.id),
        ])
        await s.commit()
        return game.id, red.id, blue.id, attacker.id, target.id


def _stub_damage(monkeypatch, *damages):
    """Patch attack_with_double_strike to return DamageResult-like objects.

    forecast_attack calls `attack_with_double_strike` twice: once for the
    base hit, once for the crit re-roll, and again for the counter. We
    return a queue of pre-baked hits.
    """
    from app.routes import actions as actions_module

    queue = list(damages)
    counter = {"n": 0}

    def _fake(attacker, target, tile_bonus=0, rng=None):
        idx = counter["n"]
        counter["n"] += 1
        d = queue[idx] if idx < len(queue) else 0
        return [_make_hit(d)]

    monkeypatch.setattr(actions_module, "attack_with_double_strike", _fake)


def _make_hit(damage: int):
    """Lightweight DamageResult stand-in (the real class is in game_logic)."""
    from app.game_logic import DamageResult

    return DamageResult(
        damage=damage, is_crit=False, is_kill=damage <= 0,
        effective_atk=damage, defense_total=0,
    )


# ============================================================
# 1) Happy path: returns populated AttackForecastOut
# ============================================================

@pytest.mark.asyncio
async def test_forecast_returns_consistent_attack_out(monkeypatch, forecast_app):
    client, SessionLocal = forecast_app
    game_id, red_id, _blue_id, attacker_id, target_id = await _seed_combat(SessionLocal)
    # Damage 6 → target has 10hp, ends at 4hp, not killed.
    _stub_damage(monkeypatch, 6, 6, 0)

    r = await client.get(
        f"/games/{game_id}/forecast-attack",
        params={
            "player_id": red_id,
            "attacker_id": attacker_id,
            "target_id": target_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    parsed = AttackForecastOut(**body)
    assert parsed.attacker_unit_id == attacker_id
    assert parsed.target_unit_id == target_id
    assert parsed.damage == 6
    assert parsed.target_hp_after == 4
    assert parsed.is_kill is False
    assert parsed.attacker_hp_after >= 0
    assert parsed.description, "forecast description should be non-empty"
    # Godot renders Chinese in the forecast panel.
    assert "预计伤害" in parsed.description or "攻击" in parsed.description


# ============================================================
# 2) Kill clamps target_hp_after and counter logic
# ============================================================

@pytest.mark.asyncio
async def test_forecast_kill_reports_no_counter(monkeypatch, forecast_app):
    client, SessionLocal = forecast_app
    game_id, red_id, _blue_id, attacker_id, target_id = await _seed_combat(SessionLocal)
    # Damage 50 (>> target max hp 10) → is_kill.
    _stub_damage(monkeypatch, 50, 50, 50)

    r = await client.get(
        f"/games/{game_id}/forecast-attack",
        params={
            "player_id": red_id,
            "attacker_id": attacker_id,
            "target_id": target_id,
        },
    )
    assert r.status_code == 200, r.text
    parsed = AttackForecastOut(**r.json())
    assert parsed.is_kill is True
    assert parsed.target_hp_after == 0
    # A dead target cannot counter, so the counter slot must read 0
    # regardless of what the stubbed damage is.
    assert parsed.counter_damage == 0
    assert parsed.counter_will_kill is False


# =============================================================
# 3) Counter-immune target still reports counter_damage=0
# =============================================================

@pytest.mark.asyncio
async def test_forecast_counter_immune_target_blocks_counter(
    monkeypatch, forecast_app,
):
    client, SessionLocal = forecast_app
    game_id, red_id, _blue_id, attacker_id, target_id = await _seed_combat(SessionLocal)

    # Mark the target with a counter-immune skill.
    from app.models import Unit as UnitModel
    from app.database import AsyncSessionLocal as _S
    async with _S() as s:
        unit = (await s.execute(
            select(UnitModel).where(UnitModel.id == target_id)
        )).scalar_one()
        unit.skills = ["fortify_defense"]  # any COUNTER_IMMUNE_SKILLS entry
        await s.commit()

    _stub_damage(monkeypatch, 4, 4, 7)
    r = await client.get(
        f"/games/{game_id}/forecast-attack",
        params={
            "player_id": red_id,
            "attacker_id": attacker_id,
            "target_id": target_id,
        },
    )
    assert r.status_code == 200, r.text
    parsed = AttackForecastOut(**r.json())
    assert parsed.counter_damage == 0, (
        "counter-immune target must not return counter damage"
    )
    assert parsed.counter_will_kill is False


# ============================================================
# 4) Error paths the UI must handle
# ============================================================

@pytest.mark.asyncio
async def test_forecast_404_for_unknown_game(forecast_app):
    client, _ = forecast_app
    r = await client.get(
        "/games/999999/forecast-attack",
        params={"player_id": 1, "attacker_id": 2, "target_id": 3},
    )
    assert r.status_code in (400, 404), r.text


@pytest.mark.asyncio
async def test_forecast_404_for_unknown_unit(monkeypatch, forecast_app):
    client, SessionLocal = forecast_app
    game_id, red_id, _blue_id, attacker_id, _target_id = await _seed_combat(SessionLocal)
    _stub_damage(monkeypatch, 0, 0, 0)
    r = await client.get(
        f"/games/{game_id}/forecast-attack",
        params={
            "player_id": red_id,
            "attacker_id": attacker_id,
            "target_id": 999999,
        },
    )
    assert r.status_code in (400, 404), r.text


# ============================================================
# 5) Direct call against the in-process function
# =============================================================
# Skipped if the module exposes forecast_attack as a route function with
# an internal "Depends(get_session)" — we instead call the function
# directly using the same db_session fixture that
# test_commanders_attack_hook.py relies on.

@pytest.mark.asyncio
async def test_forecast_direct_call_shape(monkeypatch):
    from app.database import AsyncSessionLocal, Base, dispose_db, engine, init_db

    await init_db()
    try:
        game_id, red_id, _blue_id, attacker_id, target_id = await _seed_combat(AsyncSessionLocal)
        _stub_damage(monkeypatch, 3, 3, 1)

        async with AsyncSessionLocal() as s:
            out = await forecast_attack(
                game_id=game_id,
                player_id=red_id,
                attacker_id=attacker_id,
                target_id=target_id,
                session=s,
            )
        assert isinstance(out, AttackForecastOut)
        assert out.damage == 3
        assert out.target_hp_after == 7
        assert out.is_kill is False
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await dispose_db()
