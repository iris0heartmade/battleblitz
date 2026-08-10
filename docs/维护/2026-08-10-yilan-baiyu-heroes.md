# 2026-08-10 林依澜与白予英雄单位落地

## 背景

根据原角色档案补入两名 BattleBlitz 英雄单位：

- 林依澜：无魔力的联合会首席，核心不是击杀，而是制图、推演、调度和让友军少死。
- 白予：大旻龙王之女，掌握“星礼”魔法，魔力顶尖但缺实战经验。

## 本次调整

- 新增 `lin_yilan` 英雄：基于 `bard`，保留 `sing`，新增被动 `terrain_tactician`。
- 新增 `baiyu` 英雄：基于 `sage`，使用 `arcane_strike`，以 `matk_override = 36` 确立高魔攻炮台定位。
- 新增 `terrain_tactician` 被动：防守方站在有地形防御的格子时，地形防御收益额外 `+3`。
- 补齐两名英雄的 `character_growth_rates`，避免回落到旧版 `personal_growth_modifier`。
- 补齐 Web 与 Godot 默认英雄资产三件套：棋盘 sprite、对话 portrait、crest。
- 更新 Godot 棋盘英雄 sprite 注册表。

## 数值锚点

| 英雄 | 职业 | HP | ATK | DEF | MATK | MDEF | MOV | 定位 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 林依澜 | bard | 44 | 8 | 10 | 6 | 16 | 5 | 地形防守/再动军师 |
| 白予 | sage | 50 | 9 | 9 | 36 | 20 | 5 | 高魔攻星礼炮台 |

## 验证

- `python -m pytest game/tests/test_heroes_registry.py game/tests/test_game_logic.py::TestCalculateDamage::test_terrain_tactician_adds_three_defense_on_defensive_terrain game/tests/test_godot_unit_portrait_paths.py::test_yilan_and_baiyu_hero_assets_exist_for_web_and_godot game/tests/test_godot_unit_portrait_paths.py::test_godot_hero_sprite_registry_includes_yilan_and_baiyu -q`
