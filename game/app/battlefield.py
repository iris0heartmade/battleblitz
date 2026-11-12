"""Pure, shared terrain and elevation rules; decorative meshes never enter this layer."""
from __future__ import annotations
import json
from pathlib import Path
from app.config import TERRAIN_DEF_BONUS

RULES = json.loads((Path(__file__).resolve().parents[1] / "config/elevation_rules.json").read_text(encoding="utf-8"))

def terrain_key(terrain: str) -> str:
    return RULES["aliases"].get(terrain, terrain)

def tile_height(tile) -> int:
    explicit = getattr(tile, "elevation", None)
    return int(explicit if explicit is not None else RULES["legacy_heights"].get(tile.terrain, 0))

def defense_bonus(tile) -> int:
    if tile is None:
        return 0
    return TERRAIN_DEF_BONUS.get(getattr(tile, "subtype", None) or terrain_key(tile.terrain), 0)

class Battlefield(dict):
    """Terrain mapping plus immutable per-operation height/cover context."""
    def __init__(self, tiles):
        from app.movement import movement_key
        tiles = list(tiles)
        super().__init__(((t.x, t.y), movement_key(t)) for t in tiles)
        self.heights = {(t.x,t.y): tile_height(t) for t in tiles}
        self.cover = {(t.x,t.y): defense_bonus(t) for t in tiles}

def bind_battlefield(units, field: Battlefield) -> None:
    for unit in units:
        unit._battlefield = field

def step_cost(profile, terrain, start, end):
    from app.movement import terrain_cost_x2
    cost = terrain_cost_x2(profile, terrain[end])
    if cost is None:
        return None
    heights = getattr(terrain, "heights", {})
    delta = heights.get(end, 0) - heights.get(start, 0)
    if profile.flying:
        return cost
    if abs(delta) > RULES["max_step"]:
        return None
    stairs = "castle_stairs" in (terrain.get(start), terrain.get(end))
    return cost + (0 if stairs else max(0, delta) * RULES["uphill_cost_x2"])

def path_cost(profile, terrain, path):
    costs = [step_cost(profile,terrain,a,b) for a,b in zip(path,path[1:])]
    if any(c is None for c in costs):
        raise ValueError("path crosses an impassable height edge")
    return sum(costs)

def height_delta(unit, start, end) -> int:
    field = getattr(unit, "_battlefield", None)
    heights = getattr(field, "heights", {})
    return heights.get(start, 0) - heights.get(end, 0)

def high_attack(unit, target) -> int:
    return min(RULES["attack_cap"],max(0,height_delta(unit,(unit.x,unit.y),(target.x,target.y))) * RULES["attack_per_level"])

def attack_allowed(unit, start, end, minimum, maximum, *, physical_ranged=False):
    distance = abs(start[0]-end[0])+abs(start[1]-end[1])
    delta = height_delta(unit,start,end)
    if distance == 1 and abs(delta) > RULES["melee_step"]:
        return False
    if physical_ranged and delta >= RULES["ranged_height"]:
        maximum += RULES["ranged_bonus"]
    return minimum < distance <= maximum

def normalize_grid(grid):
    for row in grid:
        for tile in row:
            if tile.terrain in RULES["aliases"]:
                tile.elevation = tile_height(tile)
                tile.terrain = terrain_key(tile.terrain)
    return grid

async def load_battlefield(session, game_id):
    from sqlalchemy import select
    from app.models import Tile
    tiles = (await session.execute(select(Tile).where(Tile.game_id==game_id))).scalars().all()
    return Battlefield(tiles)

