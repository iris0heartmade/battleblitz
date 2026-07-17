"""Load game items from one JSON file per item and shop stock from JSON."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping


_GAME_ROOT = Path(__file__).resolve().parents[1]
_ITEMS_DIR = _GAME_ROOT / "items"
_SHOPS_DIR = _GAME_ROOT / "shops"


@dataclass(frozen=True)
class ItemDefinition:
    item_id: str
    name: str
    kind: str
    description: str
    slot: str | None
    rarity: int
    stat_bonuses: Mapping[str, int]
    price: int
    icon_path: str

    def payload(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "kind": self.kind,
            "slot": self.slot,
            "rarity": self.rarity,
            "stat_bonuses": dict(self.stat_bonuses),
            "description": self.description,
            "price": self.price,
            "icon_path": self.icon_path,
        }


@lru_cache(maxsize=1)
def load_items() -> dict[str, ItemDefinition]:
    items: dict[str, ItemDefinition] = {}
    for path in sorted(_ITEMS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        item_id = str(raw["item_id"])
        if item_id in items:
            raise ValueError(f"duplicate item_id: {item_id}")
        price = int((raw.get("shop") or {}).get("price", 0))
        if price < 0:
            raise ValueError(f"item {item_id}: shop.price must be >= 0")
        items[item_id] = ItemDefinition(
            item_id=item_id,
            name=str(raw["name"]),
            kind=str(raw["kind"]),
            description=str(raw.get("description", "")),
            slot=raw.get("slot"),
            rarity=int(raw.get("rarity", 1)),
            stat_bonuses={k: int(v) for k, v in (raw.get("stat_bonuses") or {}).items()},
            price=price,
            icon_path=str((raw.get("art") or {}).get("icon_path", "")),
        )
    return items


def get_item(item_id: str | None) -> ItemDefinition | None:
    return load_items().get(item_id or "")


@lru_cache(maxsize=8)
def load_shop(shop_id: str) -> list[ItemDefinition]:
    path = _SHOPS_DIR / f"{shop_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("shop_id") != shop_id:
        raise ValueError(f"shop id mismatch in {path.name}")
    items = load_items()
    result: list[ItemDefinition] = []
    for item_id in raw.get("item_ids", []):
        item = items.get(str(item_id))
        if item is None:
            raise ValueError(f"shop {shop_id}: unknown item {item_id!r}")
        result.append(item)
    return result
