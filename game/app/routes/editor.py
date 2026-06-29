"""Map editor API — design custom maps via UI, persist to JSON.

Maps are stored as JSON files under game/maps/custom/. Each map includes:
  - id, name, size (width/height), biome
  - layout: List[str] (each row = width chars from P/F/M/R/C)
  - initial_units: List[{x, y, type, color, level}]

Size constraints: width 15–35, height 15–40.

Currently usable by mainline chapter design (custom maps can be referenced
by mainline battle specs). Future restriction: free mode only.
"""
from __future__ import annotations

import json as _json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.config import MAP_SIZE as DEFAULT_MAP_SIZE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editor/maps", tags=["editor"])

# Storage: game/maps/custom/
_CUSTOM_DIR = Path(__file__).resolve().parent.parent.parent / "maps" / "custom"
_CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

# Valid terrain chars (single-char per cell)
_VALID_TERRAINS = set("PFMRC")
_VALID_UNIT_TYPES = {"swordsman", "archer", "knight", "healer"}
_VALID_COLORS = {"red", "blue", "green", "yellow"}

# Size constraints (per requirements)
MIN_SIZE = 15
MAX_W = 45
MAX_H = 45


# ============================================================
# Request / Response models
# ============================================================

class MapSize(BaseModel):
    width: int = Field(ge=MIN_SIZE, le=MAX_W)
    height: int = Field(ge=MIN_SIZE, le=MAX_H)


class InitialUnit(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    type: str
    color: str
    level: int = Field(default=1, ge=1, le=10)

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in _VALID_UNIT_TYPES:
            raise ValueError(f"Invalid unit type: {v}")
        return v

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: str) -> str:
        if v not in _VALID_COLORS:
            raise ValueError(f"Invalid color: {v}")
        return v


class CustomMapSave(BaseModel):
    """Body for POST /editor/maps"""
    id: Optional[str] = None  # omit for new map; server assigns if missing
    name: str = Field(min_length=1, max_length=64)
    size: MapSize
    biome: str = Field(default="grass")  # grass | snow | desert
    layout: List[str]
    initial_units: List[InitialUnit] = []

    @field_validator("biome")
    @classmethod
    def _check_biome(cls, v: str) -> str:
        if v not in {"grass", "snow", "desert"}:
            raise ValueError(f"Invalid biome: {v}")
        return v


class CustomMapOut(BaseModel):
    id: str
    name: str
    size: MapSize
    biome: str
    layout: List[str]
    initial_units: List[Dict[str, Any]]
    created_at: float
    updated_at: float


class CustomMapListItem(BaseModel):
    id: str
    name: str
    width: int
    height: int
    biome: str
    updated_at: float


# ============================================================
# Helpers
# ============================================================

_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _validate_layout(layout: List[str], width: int, height: int) -> None:
    """Check layout dimensions and characters."""
    if len(layout) != height:
        raise HTTPException(
            status_code=400,
            detail=f"layout must have {height} rows, got {len(layout)}",
        )
    for y, row in enumerate(layout):
        if len(row) != width:
            raise HTTPException(
                status_code=400,
                detail=f"row {y} has {len(row)} cols, expected {width}",
            )
        for x, ch in enumerate(row):
            if ch not in _VALID_TERRAINS:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid terrain char {ch!r} at ({x},{y})",
                )


def _validate_units(units: List[InitialUnit], width: int, height: int) -> None:
    """Check units are within bounds and on passable terrain (not castle)."""
    for u in units:
        if not (0 <= u.x < width and 0 <= u.y < height):
            raise HTTPException(
                status_code=400,
                detail=f"unit at ({u.x},{u.y}) is out of bounds ({width}x{height})",
            )


def _validate_units_on_terrain(units: List[InitialUnit], layout: List[str]) -> None:
    """Check units aren't placed on castle tiles (they need starting space)."""
    for u in units:
        row = layout[u.y] if u.y < len(layout) else ""
        if u.x < len(row) and row[u.x] == "C":
            raise HTTPException(
                status_code=400,
                detail=f"unit at ({u.x},{u.y}) is on a castle tile",
            )


def _map_path(map_id: str) -> Path:
    return _CUSTOM_DIR / f"{map_id}.json"


def _read_map(map_id: str) -> Dict[str, Any]:
    path = _map_path(map_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"map {map_id!r} not found")
    return _json.loads(path.read_text(encoding="utf-8"))


def _write_map(map_id: str, data: Dict[str, Any]) -> None:
    path = _map_path(map_id)
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_id(name: str) -> str:
    """Generate a slug-ish map id from name + short uuid suffix."""
    base = re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip().lower())[:32] or "map"
    suffix = uuid.uuid4().hex[:6]
    return f"{base}_{suffix}"


def _list_custom_maps(directory: Path) -> List[Dict[str, Any]]:
    """Read all map JSON files in directory and return summary dicts.

    Reusable by /presets endpoint to merge custom maps with built-in presets.
    """
    if not directory.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "id": data["id"],
                "name": data["name"],
                "width": data["size"]["width"],
                "height": data["size"]["height"],
                "biome": data.get("biome", "grass"),
                "updated_at": data.get("updated_at", 0.0),
            })
        except Exception as e:
            logger.warning("Skipping malformed map file %s: %s", path.name, e)
    items.sort(key=lambda m: m["updated_at"], reverse=True)
    return items


# ============================================================
# Endpoints
# ============================================================

@router.get("", response_model=List[CustomMapListItem])
async def list_custom_maps() -> List[CustomMapListItem]:
    """List all saved custom maps (id, name, size, biome, updated_at)."""
    return [CustomMapListItem(**m) for m in _list_custom_maps(_CUSTOM_DIR)]


@router.get("/{map_id}", response_model=CustomMapOut)
async def load_custom_map(map_id: str) -> CustomMapOut:
    """Load a specific custom map by id."""
    return CustomMapOut(**_read_map(map_id))


@router.post("", response_model=CustomMapOut, status_code=status.HTTP_201_CREATED)
async def save_custom_map(body: CustomMapSave) -> CustomMapOut:
    """Save (create or update) a custom map.

    If body.id is provided and exists, updates the map (preserves created_at).
    Otherwise creates a new map with server-assigned id.
    """
    # Validate layout dimensions & characters
    _validate_layout(body.layout, body.size.width, body.size.height)
    # Validate units in bounds
    _validate_units(body.initial_units, body.size.width, body.size.height)
    # Validate units not on castles
    _validate_units_on_terrain(body.initial_units, body.layout)

    now = time.time()

    # Reuse existing map if id matches
    if body.id and _SAFE_ID.match(body.id):
        existing_path = _map_path(body.id)
        if existing_path.is_file():
            existing = _json.loads(existing_path.read_text(encoding="utf-8"))
            map_id = body.id
            created_at = existing.get("created_at", now)
        else:
            map_id = body.id
            created_at = now
    else:
        map_id = _generate_id(body.name)
        created_at = now

    data = {
        "id": map_id,
        "name": body.name,
        "size": {"width": body.size.width, "height": body.size.height},
        "biome": body.biome,
        "layout": body.layout,
        "initial_units": [u.model_dump() for u in body.initial_units],
        "created_at": created_at,
        "updated_at": now,
    }
    _write_map(map_id, data)
    logger.info("Saved custom map %r (%dx%d biome=%s)", map_id,
                body.size.width, body.size.height, body.biome)
    return CustomMapOut(**data)


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_map(map_id: str) -> None:
    """Delete a custom map."""
    path = _map_path(map_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"map {map_id!r} not found")
    path.unlink()
    logger.info("Deleted custom map %r", map_id)