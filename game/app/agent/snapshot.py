"""
Build GameSnapshot from the live game state (DB session).

Fog of war: an AI only sees enemy units that are:
  - within sight range of one of its own units, OR
  - standing on a visible (line-of-sight-able) tile

For MVP we use a simple rule: any enemy within `chebyshev` distance 4 of any
of my units is visible. Anything farther away we report as fog (position only
if we've ever seen it, otherwise nothing). Units we've never seen are omitted.

This mirrors `AI_AGGRO_RANGE` in `app.config` so the LLM's view roughly matches
what a reasonable rules AI would react to.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import (
    Coord,
    FogUnit,
    GameSnapshot,
    TerrainZh,
    UnitView,
)
from app.config import (
    AI_AGGRO_RANGE,
    MAP_SIZE,
    TERRAIN_CASTLE,
    TERRAIN_TYPES,
)
from app.models import Game, Player, Tile, Unit
from app.utils import chebyshev


# Map internal terrain names to the schema's TerrainZh literal.
# (Currently the literals match the DB values exactly, so it's a no-op,
# but this indirection lets us add localisation later.)
_TERRAIN_PASS: dict[str, TerrainZh] = {t: t for t in TERRAIN_TYPES}


# ----------------------------------------------------------------
# Visibility computation
# ----------------------------------------------------------------

def _compute_visible_enemy_coords(
    my_units: List[Unit],
    enemy_units: List[Unit],
    sight_range: int = AI_AGGRO_RANGE,
) -> set[Coord]:
    """Coords of enemy units within sight range of any of my units."""
    visible: set[Coord] = set()
    for e in enemy_units:
        for m in my_units:
            if chebyshev((m.x, m.y), (e.x, e.y)) <= sight_range:
                visible.add((e.x, e.y))
                break
    return visible


# ----------------------------------------------------------------
# Map → ASCII rendering
# ----------------------------------------------------------------

# Single-character glyphs. Keep the legend in sync with `map_legend` in the snapshot.
_GLYPH = {
    "plain": ".",
    "forest": "♣",   # visual fallback is fine, ascii safe is "#"
    "mountain": "▲",
    "river": "~",
    "castle": "■",
}
_GLYPH_ASCII = {  # same but ASCII-only for terminals that choke on Unicode
    "plain": ".",
    "forest": "#",
    "mountain": "^",
    "river": "~",
    "castle": "*",
}


def render_map_ascii(
    terrain: dict[Coord, str],
    unit_positions: dict[Coord, int],       # (x,y) -> unit_id
    *,
    size: int = MAP_SIZE,
    ascii_only: bool = True,
) -> str:
    """Render a small ASCII map. ~15x15 lines."""
    glyph = _GLYPH_ASCII if ascii_only else _GLYPH
    rows: list[str] = []
    # Header with column numbers
    rows.append("   " + "".join(str(x % 10) for x in range(size)))
    for y in range(size):
        cells: list[str] = []
        for x in range(size):
            t = terrain.get((x, y), ".")
            if (x, y) in unit_positions:
                cells.append("U")  # unit presence; details in text below
            else:
                cells.append(glyph.get(t, "?"))
        rows.append(f"{y:2d} " + "".join(cells))
    return "\n".join(rows)


# ----------------------------------------------------------------
# Public API
# ----------------------------------------------------------------

async def build_snapshot(
    session: AsyncSession,
    game: Game,
    player: Player,
    *,
    budget_left: int,
    action_count: int = 0,
) -> GameSnapshot:
    """Load the current game state from the DB and return a snapshot for the LLM.

    `player` is the AI's player; the snapshot is built from that player's POV.
    """
    # 1. Load tiles, players, units in one round trip each
    tiles = (await session.execute(
        select(Tile).where(Tile.game_id == game.id)
    )).scalars().all()
    terrain: dict[Coord, str] = {(t.x, t.y): t.terrain for t in tiles}
    owners: dict[Coord, Optional[int]] = {(t.x, t.y): t.owner_id for t in tiles}

    all_players = (await session.execute(
        select(Player).where(Player.game_id == game.id)
    )).scalars().all()
    all_units = (await session.execute(
        select(Unit).where(Unit.player_id.in_([p.id for p in all_players]))
    )).scalars().all()

    my_units = [u for u in all_units if u.player_id == player.id and u.hp > 0]
    enemy_units = [u for u in all_units if u.player_id != player.id and u.hp > 0]

    # 2. Apply fog of war
    visible_coords = _compute_visible_enemy_coords(my_units, enemy_units)
    visible_enemies: list[Unit] = []
    fog_enemies: list[Unit] = []
    for e in enemy_units:
        if (e.x, e.y) in visible_coords:
            visible_enemies.append(e)
        else:
            fog_enemies.append(e)

    # 3. Build view models
    def to_view(u: Unit) -> UnitView:
        t = terrain.get((u.x, u.y), "plain")
        return UnitView(
            id=u.id,
            type=u.unit_type,                # type: ignore[arg-type]
            name=u.name,
            hp=u.hp,
            max_hp=u.max_hp,
            mp=u.mp,
            x=u.x,
            y=u.y,
            terrain=t,                       # type: ignore[arg-type]
            skills=list(u.skills or []),
            morale=u.morale,
            has_acted=u.has_acted,
        )

    my_views = [to_view(u) for u in my_units]
    enemy_views = [to_view(u) for u in visible_enemies]
    fog_views = [FogUnit(x=u.x, y=u.y) for u in fog_enemies]

    # 4. Castles
    my_castles: list[Coord] = []
    enemy_castles: list[Coord] = []
    unowned_castles: list[Coord] = []
    for t in tiles:
        if t.terrain != TERRAIN_CASTLE:
            continue
        if t.owner_id is None:
            unowned_castles.append((t.x, t.y))
        elif t.owner_id == player.id:
            my_castles.append((t.x, t.y))
        else:
            enemy_castles.append((t.x, t.y))

    # 5. Map ASCII (units on visible tiles only; fog positions omitted)
    unit_positions: dict[Coord, int] = {}
    for u in my_units:
        unit_positions[(u.x, u.y)] = u.id
    for u in visible_enemies:
        unit_positions[(u.x, u.y)] = u.id

    map_ascii = render_map_ascii(terrain, unit_positions, size=game_map_size(game))

    return GameSnapshot(
        turn=game.turn_number,
        budget_left=budget_left,
        action_count=action_count,
        my_units=my_views,
        visible_enemies=enemy_views,
        fog_enemies=fog_views,
        my_castles=my_castles,
        enemy_castles=enemy_castles,
        unowned_castles=unowned_castles,
        map_size=game_map_size(game),
        map_ascii=map_ascii,
        map_legend={
            ".": "plain", "#": "forest", "^": "mountain", "~": "river",
            "*": "castle", "U": "unit",
        },
    )


def game_map_size(game: Game) -> int:
    """Map size is fixed (15x15) for now; this is the extension point if
    we add rectangular or larger boards."""
    return MAP_SIZE
