from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_GD = ROOT / "godot-client" / "scripts" / "main.gd"
HUD_THEME_GD = ROOT / "godot-client" / "scripts" / "ui" / "hud_theme.gd"


def test_selected_unit_portrait_resolves_hero_and_generic_unit_paths():
    source = MAIN_GD.read_text(encoding="utf-8")

    assert "func _unit_portrait_path_for(unit: Dictionary) -> String:" in source
    assert '"res://assets/heroes/portrait_%s.png" % hero_id' in source
    assert '"res://assets/unit_portraits/portrait_%s.png" % unit_type' in source
    assert "_set_unit_info_portrait(unit: Dictionary)" in source


def test_selected_unit_portrait_panel_is_transparent_and_borderless():
    source = HUD_THEME_GD.read_text(encoding="utf-8")

    assert "hero_portrait_panel.self_modulate = Color(1, 1, 1, 0)" in source
    assert "sb_portrait.bg_color = Color(0, 0, 0, 0)" in source
    assert "sb_portrait.border_width_left = 0" in source
    assert "sb_portrait.border_width_right = 0" in source
    assert "sb_portrait.border_width_top = 0" in source
    assert "sb_portrait.border_width_bottom = 0" in source


def test_youko_hero_assets_exist_for_web_and_godot():
    expected = ("youko.png", "portrait_youko.png", "crest_youko.png")
    for asset_name in expected:
        assert (ROOT / "game" / "app" / "web" / "assets" / "heroes" / asset_name).exists()
        assert (ROOT / "godot-client" / "assets" / "heroes" / asset_name).exists()


def test_yuanying_hero_assets_exist_for_web_and_godot():
    expected = ("yuanying.png", "portrait_yuanying.png", "crest_yuanying.png")
    for asset_name in expected:
        assert (ROOT / "game" / "app" / "web" / "assets" / "heroes" / asset_name).exists()
        assert (ROOT / "godot-client" / "assets" / "heroes" / asset_name).exists()


def test_godot_hero_sprite_registry_includes_yuanying():
    source = (ROOT / "godot-client" / "scripts" / "board" / "unit_node.gd").read_text(encoding="utf-8")

    assert '"yuanying": "yuanying.png"' in source
