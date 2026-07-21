#!/usr/bin/env python3
"""Patch event_trigger.py: fix all raw SQL issues for wave+trap."""
from pathlib import Path

p = Path("game/app/mainline/event_trigger.py")
src = p.read_text(encoding="utf-8")

# 1. Fix _spawn_unit_from_wave - raw SQL insert
old_sp = 'async def _spawn_unit_from_wave(session: AsyncSession, game: Game, spec: dict,) -> Optional[Unit]:'
new_sp = 'async def _spawn_unit_from_wave(session: AsyncSession, game: Game, spec: dict,) -> Optional[dict]:'
src = src.replace(old_sp, new_sp, 1)

# 2. Replace the function body
old_body = '''    """Insert a Unit row from a wave spawn spec.

    The spec is a dict: {x, y, type, color, level, (optional) name}.
    """
    from app.models import Unit as UnitModel
    # Find the player this wave spawn belongs to.  If the spec says
    # "blue", it\'s an enemy.  If "red", it\'s a player.  Simple lookup
    # by color.
    from app.models import Player
    color = str(spec.get("color", "blue"))
    player = (await session.execute(
        select(Player).where(Player.game_id == game.id, Player.color == color)
    )).scalars().first()
    if player is None:
        return None
    unit = UnitModel(
        game_id=game.id,
        player_id=player.id,
        unit_type=str(spec.get("type", "knight")),
        name=str(spec.get("name", spec.get("type", "?"))),
        x=int(spec.get("x", 0)),
        y=int(spec.get("y", 0)),
        hp=20, max_hp=20,
        mp=3, mov=3,
        atk=10, def_=5,
        matk=0, mdef=0,
        attack_range=1,
        min_attack_range=1,
        skills="[]",
        color=color,
        has_acted=False,
        has_moved=False,
    )
    session.add(unit)
    await session.flush()
    return unit'''
new_body = '''    """Insert a Unit row from a wave spawn spec using raw SQL."""
    from sqlalchemy import text as _stext
    color = str(spec.get("color", "blue"))
    player_row = (await session.execute(
        _stext("SELECT id FROM players WHERE game_id = :g AND color = :c LIMIT 1"),
        {"g": game.id, "c": color},
    )).mappings().first()
    if player_row is None:
        return None
    pid = int(player_row["id"])
    await session.execute(
        _stext("INSERT INTO units (player_id, unit_type, name, level, hp, max_hp, mp, mov, atk, def_, matk, mdef, x, y, attack_range, min_attack_range, skills, color, has_acted, has_moved) VALUES (:pid, :ut, :nm, :lv, :hp, :mhp, :mp, :mv, :atk, :def, :matk, :mdef, :x, :y, 1, 1, '[]', :col, 0, 0)"),
        {"pid": pid, "ut": str(spec.get("type", "knight")), "nm": str(spec.get("name", spec.get("type", "?"))),
         "lv": int(spec.get("level", 1)), "hp": 20, "mhp": 20,
         "mp": 3, "mv": 3, "atk": 10, "def": 5, "matk": 0, "mdef": 0,
         "x": int(spec.get("x", 0)), "y": int(spec.get("y", 0)), "col": color},
    )
    await session.flush()
    return {"id": 0, "player_id": pid}'''

if old_body in src:
    src = src.replace(old_body, new_body, 1)
    print("replaced spawn body")
else:
    print("WARN: old_body not found, dumping 600 chars around")
    idx = src.find("_spawn_unit_from_wave")
    print(src[idx:idx+600])

# 3. Fix trap update: u.x -> u["x"]
src = src.replace("int(u.x)", "int(u[\"x\"])")
src = src.replace("int(u.y)", "int(u[\"y\"])")
src = src.replace('int(u["hp"])', 'int(u["hp"])')  # already ok
# fix target references
src = src.replace("u.player_id", 'u["player_id"]')
src = src.replace("u.id", 'u["id"]')
src = src.replace("u.name", 'u["name"]')

# 4. Update u.hp = with raw SQL UPDATE
old_assign = "new_hp = max(0, int(u[\"hp\"]) - dmg)\n            hits += 1"
new_assign = "new_hp = max(0, int(u[\"hp\"]) - dmg)\n            await session.execute(\n                _text(\"UPDATE units SET hp = :nhp WHERE id = :uid\"),\n                {\"nhp\": new_hp, \"uid\": int(u[\"id\"])},\n            )\n            hits += 1"
# Find the exact line and replace
old_line = '            u["hp"] = max(0, int(u["hp"]) - dmg)'
if old_line in src:
    src = src.replace(old_line, new_assign, 1)
    print("replaced trap hp update with raw SQL")

p.write_text(src, encoding="utf-8")
print("patch done")
