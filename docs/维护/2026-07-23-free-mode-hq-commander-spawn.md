# 2026-07-23 自由模式 HQ 指挥官开局

## 需求

自由模式开局时，每个玩家的 HQ 上刷新一枚特殊初始单位：

- 玩家选择了指挥官：刷新该指挥官英雄对应的基础职业棋子，并绑定 `hero_id`。
- 玩家未选择指挥官：刷新 `dragon_rider`（飞龙骑士）。

## 实现

- 新增 `_apply_hq_commander_spawns()`，输入 `initial_units + players + seat->HQ`，输出替换后的初始单位和 hero override。
- `start_game()` 仅在 `battle_config._mode == "free"` 时启用该规则。
- 规则放在 `_start_battle_internal()` 中单位落库前执行，后续主线模式可复用同一 helper。

## 2026-07-23 追加修复

实测 Godot 标准 2 人图未生效，根因在客户端：

- `NetworkClient.create_game()` 未发送 `mode="free"`，后端按默认 `mainline` 开局，导致 HQ 指挥官替换规则不启用。
- Godot 全局 AI 指挥官配置硬编码为 `{2: commander_id}`，标准 2 人图 AI 是 seat 1，导致 AI 指挥官没有绑定到实际 AI 玩家。

修复后：

- Godot 自由模式创建房间请求显式携带 `mode="free"`。
- `_selected_lobby_ai_commanders()` 按当前地图座位遍历所有 AI replacement seat，逐座写入 commander。

## 验证

- `test_free_mode_battle_config_commander_spawns_on_host`
- `test_free_mode_empty_commander_spawns_dragon_rider_on_hq`
- `test_free_mode_seat_commanders_spawn_on_human_and_ai_hqs`
- `test_godot_free_lobby_create_sends_free_mode_to_backend`
