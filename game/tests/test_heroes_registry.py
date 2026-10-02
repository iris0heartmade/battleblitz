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


def test_lin_yilan_is_registered_as_terrain_tactician():
    yilan = get("lin_yilan")

    assert yilan.hero_id == "lin_yilan"
    assert yilan.display_cn == "林依澜"
    assert yilan.base_class_id == "bard"
    assert yilan.hp_override == 44
    assert yilan.atk_override == 8
    assert yilan.def_override == 10
    assert yilan.matk_override == 6
    assert yilan.mdef_override == 16
    assert yilan.mov_override == 5
    assert yilan.sprite_path == "lin_yilan.png"
    assert yilan.portrait_path == "portrait_lin_yilan.png"
    assert yilan.crest_path == "crest_lin_yilan.png"
    assert yilan.active_skills == ("sing",)
    assert yilan.passive_skills == ("terrain_tactician",)
    assert yilan.character_growth_rates == {
        "hp": 75,
        "atk": 35,
        "def": 45,
        "matk": 35,
        "mdef": 70,
        "mov": 0,
    }
    assert get_by_dialogue_name("林依澜").hero_id == "lin_yilan"


def test_baiyu_is_registered_as_high_attack_sage():
    baiyu = get("baiyu")

    assert baiyu.hero_id == "baiyu"
    assert baiyu.display_cn == "白予"
    assert baiyu.base_class_id == "sage"
    assert baiyu.hp_override == 50
    assert baiyu.atk_override == 9
    assert baiyu.def_override == 9
    assert baiyu.matk_override == 36
    assert baiyu.mdef_override == 20
    assert baiyu.mov_override == 5
    assert baiyu.sprite_path == "baiyu.png"
    assert baiyu.portrait_path == "portrait_baiyu.png"
    assert baiyu.crest_path == "crest_baiyu.png"
    assert baiyu.active_skills == ("arcane_strike",)
    assert baiyu.passive_skills == ()
    assert baiyu.character_growth_rates == {
        "hp": 65,
        "atk": 35,
        "def": 35,
        "matk": 100,
        "mdef": 75,
        "mov": 0,
    }
    assert get_by_dialogue_name("白予").hero_id == "baiyu"
