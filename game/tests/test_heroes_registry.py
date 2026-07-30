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


def test_youko_is_registered_as_special_bard_hero():
    youko = get("youko")

    assert youko.hero_id == "youko"
    assert youko.display_cn == "洋子"
    assert youko.base_class_id == "bard"
    assert youko.sprite_path == "youko.png"
    assert youko.portrait_path == "portrait_youko.png"
    assert youko.crest_path == "crest_youko.png"
    assert youko.active_skills == ("sing",)
    assert get_by_dialogue_name("洋子").hero_id == "youko"
