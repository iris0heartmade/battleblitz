from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1].parent


def test_backend_recruit_cost_covers_all_registered_unit_types():
    from app.classes.units import type_ids
    from app.config import RECRUIT_COST

    assert sorted(RECRUIT_COST) == sorted(type_ids())


def test_web_recruit_modal_lists_all_backend_recruit_types():
    from app.config import RECRUIT_COST

    source = (ROOT / "game" / "app" / "web" / "app.js").read_text(encoding="utf-8")
    for unit_type in RECRUIT_COST:
        assert f'id: "{unit_type}"' in source


def test_godot_recruit_options_list_all_backend_recruit_types():
    from app.config import RECRUIT_COST

    source = (ROOT / "godot-client" / "scripts" / "main.gd").read_text(encoding="utf-8")
    config = (ROOT / "godot-client" / "scripts" / "autoload" / "config.gd").read_text(encoding="utf-8")
    for unit_type in RECRUIT_COST:
        assert f'"type": "{unit_type}"' in source
        assert f'"{unit_type}":' in config
