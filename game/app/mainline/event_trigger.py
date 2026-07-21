"""Event triggers for mainline battles (07-21 F5B)."""
from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession
from app.events import GameEvent, bus
from app.mainline import load_mainline
from app.models import Game

logger = logging.getLogger(__name__)

_ALIVE = _sqltext("SELECT u.id,u.player_id,u.name,u.hp,u.x,u.y FROM units u JOIN players pl ON u.player_id=pl.id WHERE pl.game_id=:g AND u.hp>0")
_DEAD  = _sqltext("SELECT u.id,u.player_id,u.name,u.hp,u.x,u.y FROM units u JOIN players pl ON u.player_id=pl.id WHERE pl.game_id=:g AND u.hp<=0")
_KILLR = _sqltext("SELECT u.id,u.player_id,u.name FROM units u JOIN players pl ON u.player_id=pl.id WHERE pl.game_id=:g AND u.hp>0 LIMIT 1")
_PLR   = _sqltext("SELECT id FROM players WHERE game_id=:g AND color=:c LIMIT 1")
_INSERT = _sqltext("INSERT INTO units (player_id,unit_type,name,level,exp,hp,max_hp,atk,def_,matk,mdef,mov,mp,morale,x,y,has_acted,has_moved,skills) VALUES (:p,:t,:n,1,0,20,20,10,5,0,0,3,3,5,:x,:y,0,0,'[]')")


async def _spawn(session, game, spec):
    pid = (await session.execute(_PLR, {"g": game.id, "c": str(spec.get("color", "blue"))})).scalar()
    if pid is None:
        return None
    await session.execute(_INSERT, {
        "p": int(pid), "t": str(spec.get("type", "knight")),
        "n": str(spec.get("name", spec.get("type", "?"))),
        "lv": int(spec.get("level", 1)),
        "x": int(spec.get("x", 0)), "y": int(spec.get("y", 0)),
        "c": str(spec.get("color", "blue")),
    })
    await session.flush()
    return 0


async def trigger_wave_spawns(session, game):
    mlid = _resolve(game)
    if mlid is None:
        return 0
    try:
        ml = load_mainline(mlid)
    except Exception:
        return 0
    b = _battle(ml, game)
    if b is None:
        return 0
    wvs = b.get("waves") or []
    n = 0
    for w in wvs:
        if int(w.get("turn", 0)) != int(game.turn_number):
            continue
        for s in w.get("spawns", []):
            uid = await _spawn(session, game, s)
            if uid is not None:
                n += 1
                await bus.publish(GameEvent(
                    type="move", game_id=game.id, turn=game.turn_number,
                    actor_name=str(s.get("type", "?")),
                    context={"x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
                             "type": str(s.get("type", "?")), "color": str(s.get("color", "blue")),
                             "wave_turn": int(w.get("turn", 0)),
                             "trigger_msg": str(w.get("trigger_msg", ""))},
                ))
    if n:
        await session.commit()
    return n


async def trigger_trap_damage(session, game):
    mlid = _resolve(game)
    if mlid is None:
        return 0
    try:
        ml = load_mainline(mlid)
    except Exception:
        return 0
    b = _battle(ml, game)
    if b is None:
        return 0
    trs = b.get("traps") or []
    if not trs:
        return 0
    rows = (await session.execute(_ALIVE, {"g": game.id})).mappings().all()
    h = 0
    for tr in trs:
        tx, ty = int(tr.get("x", -1)), int(tr.get("y", -1))
        for u in rows:
            if int(u["x"]) != tx or int(u["y"]) != ty:
                continue
            dmg = int(tr.get("damage", 0))
            nhp = max(0, int(u["hp"]) - dmg)
            await session.execute(_sqltext("UPDATE units SET hp=:h WHERE id=:id"), {"h": nhp, "id": int(u["id"])})
            h += 1
            await bus.publish(GameEvent(
                type="attack", game_id=game.id, turn=game.turn_number,
                actor_name=f"trap_{tr.get('type','spike')}",
                target_player_id=int(u["player_id"]), target_unit_id=int(u["id"]), target_name=str(u["name"]),
                context={"dmg": dmg, "trap": True, "trap_type": str(tr.get("type", "spike")), "x": tx, "y": ty},
            ))
            if nhp <= 0:
                await bus.publish(GameEvent(
                    type="kill", game_id=game.id, turn=game.turn_number,
                    actor_name=f"trap_{tr.get('type','spike')}",
                    target_player_id=int(u["player_id"]), target_unit_id=int(u["id"]), target_name=str(u["name"]),
                    context={"trap_kill": True, "trap_type": str(tr.get("type", "spike"))},
                ))
    return h


async def trigger_boss_kill_check(session, game):
    rows = (await session.execute(_DEAD, {"g": game.id})).mappings().all()
    for u in rows:
        nm = str(u.get("name", ""))
        if nm.lower() not in ("kalde", "boss", "warlord"):
            continue
        k = (await session.execute(_KILLR, {"g": game.id})).mappings().first()
        if k is None:
            continue
        await bus.publish(GameEvent(
            type="kill", game_id=game.id, turn=game.turn_number,
            actor_player_id=int(k["player_id"]), actor_unit_id=int(k["id"]), actor_name=str(k["name"]),
            target_player_id=int(u["player_id"]), target_unit_id=int(u["id"]), target_name=str(u["name"]),
            context={"boss": True, "is_boss_kill": True},
        ))
        return 1
    return 0


def register_end_of_turn_hook():
    from app import game_logic as gl
    orig = gl.apply_end_of_turn
    async def wrapped(session, game):
        result = await orig(session, game)
        for fn, lb in [(trigger_wave_spawns, "wave"), (trigger_trap_damage, "trap"), (trigger_boss_kill_check, "boss_kill")]:
            try:
                await fn(session, game)
            except Exception as e:
                logger.warning("F5B %s trigger failed: %s", lb, e)
        return result
    gl.apply_end_of_turn = wrapped
    logger.info("F5B hook registered")


def _resolve(game):
    nm = getattr(game, "name", None) or ""
    if not nm.startswith("mainline:"):
        return None
    return nm.split(":")[1] if ":" in nm else None


def _battle(ml, game):
    nm = getattr(game, "name", None) or ""
    parts = nm.split(":")
    if len(parts) < 3:
        return None
    bid = parts[2]
    for b in getattr(ml, "battles", []) or []:
        if getattr(b, "id", None) == bid:
            return b.model_dump() if hasattr(b, "model_dump") else b
    return None
