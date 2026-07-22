# 2026-07-23 自由模式 HQ 指挥官开局

## 需求

自由模式开局时，每个玩家的 HQ 上刷新一枚特殊初始单位：

- 玩家选择了指挥官：刷新该指挥官英雄对应的基础职业棋子，并绑定 `hero_id`。
- 玩家未选择指挥官：刷新 `dragon_rider`（飞龙骑士）。

## 实现

- 新增 `_apply_hq_commander_spawns()`，输入 `initial_units + players + seat->HQ`，输出替换后的初始单位和 hero override。
- `start_game()` 仅在 `battle_config._mode == "free"` 时启用该规则。
- 规则放在 `_start_battle_internal()` 中单位落库前执行，后续主线模式可复用同一 helper。

## 验证

- `test_free_mode_battle_config_commander_spawns_on_host`
- `test_free_mode_empty_commander_spawns_dragon_rider_on_hq`
