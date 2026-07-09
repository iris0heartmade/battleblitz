from __future__ import annotations

import pytest

from app.mainline.spawn_overrides import (
    SpawnOverrideError,
    apply_spawn_overrides,
)


BASE_UNITS = [
    {"x": 2, "y": 8, "type": "warlock", "color": "red", "level": 1},
    {"x": 3, "y": 7, "type": "swordsman", "color": "red", "level": 1},
    {"x": 12, "y": 8, "type": "warlock", "color": "blue", "level": 1},
]


class TestApplySpawnOverrides:
    def test_remove_replace_add_in_fixed_order(self):
        out = apply_spawn_overrides(
            BASE_UNITS,
            {
                "remove": [
                    {"color": "red", "x": 3, "y": 7},
                ],
                "replace": [
                    {
                        "match": {"color": "red", "x": 2, "y": 8},
                        "unit": {"type": "knight", "color": "red", "level": 2},
                    },
                ],
                "add": [
                    {"x": 13, "y": 8, "type": "archer", "color": "blue", "level": 1},
                ],
            },
        )
        assert sorted((u["x"], u["y"], u["type"], u["color"], u["level"]) for u in out) == [
            (2, 8, "knight", "red", 2),
            (12, 8, "warlock", "blue", 1),
            (13, 8, "archer", "blue", 1),
        ]

    def test_replace_inherits_match_coord_when_omitted(self):
        out = apply_spawn_overrides(
            BASE_UNITS,
            {
                "replace": [
                    {
                        "match": {"color": "blue", "x": 12, "y": 8},
                        "unit": {"type": "healer", "color": "blue", "level": 3},
                    },
                ],
            },
        )
        replaced = next(u for u in out if u["color"] == "blue")
        assert (replaced["x"], replaced["y"]) == (12, 8)
        assert replaced["type"] == "healer"
        assert replaced["level"] == 3

    def test_missing_remove_target_raises(self):
        with pytest.raises(SpawnOverrideError, match="remove target not found"):
            apply_spawn_overrides(
                BASE_UNITS,
                {
                    "remove": [
                        {"color": "red", "x": 99, "y": 99},
                    ],
                },
            )

    def test_duplicate_final_coord_raises(self):
        with pytest.raises(SpawnOverrideError, match="duplicate coord"):
            apply_spawn_overrides(
                BASE_UNITS,
                {
                    "add": [
                        {"x": 12, "y": 8, "type": "archer", "color": "blue", "level": 1},
                    ],
                },
            )
