from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HeroPresetState:
    hero_id: str
    class_id: str
    level: int
    exp: int


def build_standardized_hero_state(
    *,
    hero_id: str,
    class_id: str,
    preset_level: int,
) -> HeroPresetState:
    return HeroPresetState(
        hero_id=hero_id,
        class_id=class_id,
        level=preset_level,
        exp=0,
    )
