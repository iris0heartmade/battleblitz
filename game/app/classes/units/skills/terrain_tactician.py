"""Terrain Tactician - passive terrain defense amplification."""
from app.classes.units.skills.base import BaseSkill


class TerrainTacticianSkill(BaseSkill):
    skill_id = "terrain_tactician"
    display_cn = "制图首席"
    display_en = "Terrain Tactician"
    is_passive = True
    default_users: list[str] = []

    def modify_terrain_def_bonus(self, tile_def_bonus: int, defender) -> int:
        if tile_def_bonus <= 0:
            return tile_def_bonus
        return tile_def_bonus + 3
