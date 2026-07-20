from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NETWORK_CLIENT = ROOT / "godot-client" / "scripts" / "autoload" / "network_client.gd"
MAIN_GD = ROOT / "godot-client" / "scripts" / "main.gd"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_godot_network_client_exposes_hero_backend_endpoints():
    source = _read(NETWORK_CLIENT)
    required_snippets = [
        "func get_mainline_prepare(",
        '"/mainlines/%s/prepare?user_name=%s"',
        "func promote_mainline_hero(",
        '"/mainlines/%s/prepare/promote"',
        "func equip_mainline_hero(",
        '"/mainlines/%s/prepare/equipment"',
        "func get_post_battle_shop(",
        '"/mainlines/%s/shop?user_name=%s"',
        "func purchase_post_battle_shop_item(",
        '"/mainlines/%s/shop/purchase"',
        "func get_mercenary_config(",
        '"/mainlines/%s/mercenary/config?user_name=%s"',
        "func allocate_mercenary_points(",
        '"/mainlines/%s/mercenary/allocate"',
        "func list_saves(",
        '"/saves?user_name=%s"',
        "func load_save(user_name: String, kind: String, slot_index: int",
        '"/saves/load"',
        "func erase_save(user_name: String, kind: String, slot_index: int",
        '"/saves/erase"',
        "func capture_suspend(game_id: int, user_name: String",
        '"/games/%d/suspend"',
    ]
    for snippet in required_snippets:
        assert snippet in source


def test_godot_save_views_use_save_api_not_game_delete_api():
    source = _read(MAIN_GD)
    assert 'NetworkClient.list_saves(_user_name, Callable(self, "_on_saves_response"))' in source
    assert 'NetworkClient.list_saves(_user_name, Callable(self, "_on_ml_slots_response"))' in source
    assert "NetworkClient.load_save(" in source
    assert "NetworkClient.erase_save(" in source
    assert 'NetworkClient.delete_game(_selected_save_id' not in source
    assert 'NetworkClient.list_games(Callable(self, "_on_saves_response")' not in source
    assert 'NetworkClient.list_games(Callable(self, "_on_ml_slots_response")' not in source


def test_godot_mainline_start_passes_prepare_compatible_arguments():
    source = _read(MAIN_GD)
    assert "NetworkClient.get_mainline_prepare(" in source
    assert "func _on_prepare_start_pressed() -> void:" in source
    assert 'NetworkClient.start_mainline(_selected_mainline_id, _user_name, false, [], Callable(self, "_on_mainline_start_response"))' in source
    assert 'NetworkClient.start_mainline(mainline_id, _user_name, false, [], Callable(self, "_on_mainline_start_response"), true)' in source
    assert 'NetworkClient.next_battle_mainline(_active_mainline_id, _user_name, [], Callable(self, "_on_mainline_next_battle_response"))' in source
    assert "NetworkClient.start_mainline(mainline_id, _user_name, false, [], Callable(self, \"_on_mainline_start_response\"))" not in source


def test_godot_prepare_ui_uses_hero_backend_actions():
    source = _read(MAIN_GD)
    required_snippets = [
        "func _render_mainline_prepare() -> void:",
        "func _build_prepare_heroes_text(payload: Dictionary) -> String:",
        "func _build_prepare_equipment_text(payload: Dictionary) -> String:",
        "func _build_prepare_mercenary_text() -> String:",
        "func _build_prepare_shop_text() -> String:",
        "NetworkClient.promote_mainline_hero(",
        "NetworkClient.equip_mainline_hero(",
        "NetworkClient.get_post_battle_shop(",
        "NetworkClient.purchase_post_battle_shop_item(",
        "NetworkClient.get_mercenary_config(",
        "NetworkClient.allocate_mercenary_points(",
    ]
    for snippet in required_snippets:
        assert snippet in source
