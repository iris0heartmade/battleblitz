from app.classes.heroes import get, get_by_dialogue_name, hero_ids


def test_anna_is_registered():
    anna = get("anna")

    assert anna.hero_id == "anna"
    assert anna.display_cn == "安娜"
    assert anna.base_class_id == "healer"
    assert anna.sprite_path == "anna.png"
    assert anna.portrait_path == "portrait_anna.png"
    assert anna.crest_path == "crest_anna.png"
    assert anna.active_skills == ("heal",)


def test_anna_dialogue_name_resolves():
    assert "anna" in hero_ids()
    assert get_by_dialogue_name("安娜").hero_id == "anna"
