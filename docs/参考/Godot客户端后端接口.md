# Godot 客户端后端接口文档

> 更新日期：2026-07-19  
> 适用客户端：`godot-client/`，Godot 4.7  
> 后端入口：`game/app/main.py` 与 `game/app/routes/*`  
> Godot 封装：`godot-client/scripts/autoload/network_client.gd`

## 总体约定

Godot 只负责展示、输入和乐观提示；规则裁决、伤害、胜负、AI 行动、主线进度均以后端为准。

默认本地地址：

```text
HTTP API: http://localhost:8000
WS API:   ws://localhost:8000
```

Godot 通过 `UserSettings.get_api_base()` 和 `UserSettings.get_ws_base()` 获取实际地址。

## 推荐入口流程

### 联机大厅创建房间并开始

1. `POST /games`
2. `POST /games/{game_id}/join`
3. 可选：`POST /games/{game_id}/add-ai`
4. `POST /games/{game_id}/start`
5. `GET /games/{game_id}/state`
6. `WS /ws/games/{game_id}?player_id={player_id}&since_seq=0`

Godot 入口：`_on_lobby_pressed()` -> `_on_create_room_pressed()` -> `_on_lobby_start_pressed()`。创建、加入、开始必须使用显式 callback，不要依赖全局 `api_response` 推断流程。

### 联机大厅加入/观战

1. `GET /games`
2. `POST /games/{game_id}/join`
3. 观战时请求体带 `role: "spectator"`
4. 房主开始后进入 GameView，连接 WS 并主动 `GET /state`

### 主线开始战斗

1. `GET /profile/{user_name}`，必要时 `POST /progression/profiles`
2. `GET /mainlines`
3. `GET /mainlines/{mainline_id}`
4. 可选：`POST /mainlines/{mainline_id}/select-commander`
5. `POST /mainlines/{mainline_id}/start`
6. 若返回 409 且 `detail.error == "mainline_already_active"`：`POST /mainlines/{mainline_id}/abandon` 后重试 start
7. 进入 GameView 后 `GET /games/{game_id}/state` + WS

Godot 已按 Web UI 行为实现 409 自动 abandon 重试。

### 快捷 AI 测试流

首页不再提供“自由对局（人机）”。自动化工具若需要快速进入一局 AI 对战，应调用 Godot 内部 `_start_dev_ai_game()`，其后端流程仍是：

1. `POST /games`
2. `POST /games/{game_id}/join`
3. `POST /games/{game_id}/add-ai`
4. `POST /games/{game_id}/start`
5. `GET /games/{game_id}/state` + WS

## 游戏生命周期

| 方法 | 路径 | 请求体 | 返回 |
|---|---|---|---|
| `GET` | `/games` | query 可带 `user_name` | `GameSummaryOut[]` |
| `POST` | `/games` | `{name, map_preset, map_biome, win_condition?, battle_config?}` | `GameSummaryOut` |
| `DELETE` | `/games/{game_id}` | 无 | `204` |
| `POST` | `/games/{game_id}/join` | `{user_name, color?, team?, role?}` | `PlayerOut` |
| `POST` | `/games/{game_id}/rejoin` | `{player_id}` | `RejoinGameResponse` |
| `POST` | `/games/{game_id}/rejoin_by_name` | `{user_name}` | `RejoinGameResponse` |
| `POST` | `/games/{game_id}/start` | 无 | `GameStateOut` |
| `GET` | `/games/{game_id}/state` | 无 | `GameStateOut` |
| `GET` | `/games/{game_id}/lobby` | 无 | `LobbyInfoOut` |

Godot 封装：

```gdscript
NetworkClient.list_games(callback, user_name)
NetworkClient.create_game(room_name, map_preset, map_biome, win_condition, commander_id, bgm_track_id, ai_commanders, callback)
NetworkClient.join_game(game_id, user_name, color, team, role, callback)
NetworkClient.rejoin_game_by_player_id(game_id, player_id, callback)
NetworkClient.rejoin_game_by_name(game_id, user_name, callback)
NetworkClient.start_game(game_id, callback)
NetworkClient.get_game_state(game_id, callback)
NetworkClient.get_lobby(game_id, callback)
NetworkClient.delete_game(game_id, callback)
```

## 大厅与玩家管理

| 方法 | 路径 | 请求体 | 用途 |
|---|---|---|---|
| `PATCH` | `/games/{game_id}/players/{player_id}/team` | `{caller_player_id, team}` | 自己或房主调整队伍 |
| `POST` | `/games/{game_id}/add-ai` | `{difficulty, agent_kind, personality}` | 添加 AI |
| `DELETE` | `/games/{game_id}/players/{player_id}` | 无 | 移除玩家或 AI |

观战转换沿用 Web UI 做法：先删除自己的 player，再用 `role: "spectator"` 重新 join。

## 战斗动作

| 方法 | 路径 | 请求体 | 返回 |
|---|---|---|---|
| `POST` | `/games/{game_id}/move` | `{player_id, unit_id, to_x, to_y}` | `MoveResult` |
| `GET` | `/games/{game_id}/forecast-attack` | query: `player_id, attacker_id, target_id` | `AttackForecastOut` |
| `POST` | `/games/{game_id}/attack` | `{player_id, attacker_id, target_id}` | `AttackResult` |
| `POST` | `/games/{game_id}/skill` | `{player_id, unit_id, skill, target_id?}` | `SkillResult` |
| `POST` | `/games/{game_id}/wait` | `{player_id, unit_id}` | `WaitResult` |
| `POST` | `/games/{game_id}/claim` | `{player_id, unit_id}` | `ClaimResult` |
| `POST` | `/games/{game_id}/recruit` | `{player_id, tile_x, tile_y, unit_type}` | `RecruitResult` |
| `POST` | `/games/{game_id}/end-turn` | `{player_id}` | `EndTurnResult` |
| `POST` | `/games/{game_id}/co-power` | `{player_id}` | `GameStateOut` 或动作结果 |

动作发出后客户端不应本地改权威状态，应等待 REST 返回或 WS `state.snapshot` / `event.delta`。

### 攻击预测

Godot 攻击确认时调用：

```text
GET /games/{game_id}/forecast-attack?player_id={player_id}&attacker_id={attacker_id}&target_id={target_id}
```

该接口只读，不改变单位生命、行动状态、回合或事件日志。后端复用攻击范围、视线、敌我、当前玩家、反击免疫等校验；Godot 只展示返回结果，不在客户端复制伤害公式。

返回字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `ok` | `bool` | 预测成功标记 |
| `attacker_unit_id` | `int` | 攻击方单位 |
| `target_unit_id` | `int` | 目标单位 |
| `damage` | `int` | 本次普通预测总伤害，已包含双击等后端规则 |
| `crit_damage` | `int` | 暴击参考伤害 |
| `is_kill` | `bool` | 预测是否可击杀目标 |
| `target_hp_after` | `int` | 目标预测剩余生命 |
| `target_def_bonus` | `int` | 目标所在地形防御加成 |
| `counter_damage` | `int` | 目标可反击时的预测反击伤害 |
| `attacker_hp_after` | `int` | 我方承受反击后的预测剩余生命 |
| `counter_will_kill` | `bool` | 反击是否可能击倒我方 |
| `description` | `string` | 已本地化的中文摘要 |

Godot 封装：

```gdscript
NetworkClient.forecast_attack(game_id, player_id, attacker_id, target_id, callback)
```

当前展示位置：战斗中右侧单位信息栏。选择攻击目标后，攻击确认浮层仍负责“确认/取消”，伤害预测数字显示在右侧信息栏的“战斗预测”区。

## 元数据

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/games/presets` | 地图预设 |
| `GET` | `/games/units` | 单位类型、数值、技能 |
| `GET` | `/games/skills` | 技能定义 |
| `GET` | `/heroes` | 英雄、portrait、crest |
| `GET` | `/audio/tracks` | BGM 轨道 |
| `GET` | `/players/me/commanders?user_name={name}` | 已解锁指挥官 |

Godot 当前已封装 presets、heroes、audio tracks、commanders。单位和技能仍主要来自 `Config.gd` 镜像，后续建议动态拉取。

## 主线

| 方法 | 路径 | 请求/参数 | 用途 |
|---|---|---|---|
| `GET` | `/mainlines` | 无 | 主线列表 |
| `GET` | `/mainlines/{mainline_id}` | 无 | 主线详情 |
| `GET` | `/mainlines/dialogue?path={path}` | query | 读取剧情 JSON |
| `POST` | `/mainlines/{mainline_id}/select-commander` | `{user_name, commander_id}` | 主线指挥官选择 |
| `POST` | `/mainlines/{mainline_id}/start` | `{user_name, skip_intro}` | 开始主线战斗 |
| `POST` | `/mainlines/{mainline_id}/advance` | `{user_name, game_id}` | 战后推进 |
| `POST` | `/mainlines/{mainline_id}/next-battle` | `{user_name}` | 开下一场 |
| `POST` | `/mainlines/{mainline_id}/abandon` | `{user_name}` | 放弃当前主线 |

409 格式：

```json
{
  "detail": {
    "error": "mainline_already_active",
    "user_name": "Player",
    "active_mainline": "chapter_01_steel_rebellion"
  }
}
```

## Profile / 养成

| 方法 | 路径 | 请求体 | 用途 |
|---|---|---|---|
| `GET` | `/profile/{user_name}` | 无 | 玩家档案 |
| `POST` | `/progression/profiles` | `{user_name}` | 创建档案 |
| `GET` | `/progression/profiles` | 无 | 档案列表 |
| `GET` | `/progression/profiles/{profile_id}/units` | 无 | 单位实例列表 |
| `POST` | `/progression/units/{unit_id}/xp` | `{amount, reason?}` | 加经验 |
| `POST` | `/progression/units/{unit_id}/promote` | `{target_class?}` | 转职 |

## 地图编辑器

| 方法 | 路径 | 请求体 | 用途 |
|---|---|---|---|
| `GET` | `/editor/maps` | 无 | 自定义地图列表 |
| `GET` | `/editor/maps/{map_id}` | 无 | 读取自定义地图 |
| `POST` | `/editor/maps` | `CustomMapIn` | 新建或更新地图 |
| `DELETE` | `/editor/maps/{map_id}` | 无 | 删除地图 |

`CustomMapIn` 核心字段：

```json
{
  "id": "optional_map_id",
  "name": "My Map",
  "size": {"width": 15, "height": 15},
  "biome": "grass",
  "layout": ["PPPP...", "..."],
  "initial_units": [
    {"x": 1, "y": 1, "type": "swordsman", "color": "red", "level": 1}
  ]
}
```

## WebSocket

连接：

```text
ws://<host>/ws/games/{game_id}?player_id={player_id}&since_seq={last_seq}
wss://<host>/ws/games/{game_id}?player_id={player_id}&since_seq={last_seq}
```

Envelope：

```json
{
  "v": 1,
  "type": "state.snapshot",
  "seq": 12,
  "sent_at_ms": 123456,
  "payload": {}
}
```

| type | payload | Godot 处理 |
|---|---|---|
| `server.hello` | `{server_version, protocol_version, current_seq, heartbeat_sec, supports_replay, authed_player_id}` | 更新 seq / 连接状态 |
| `state.snapshot` | `{game: GameStateOut}` | `GameState._on_state_snapshot` |
| `event.delta` | `GameEvent` | `GameState._on_event_delta` |
| `turn.advance` | `{turn, next_player_id, ...}` | 作为 event 转发 |
| `server.pong` | `{echo_at_ms}` | 心跳确认 |
| `commentary.text` / `commentary.audio` | `{text}` 或音频字段 | 当前 Godot no-op，待接 UI |
| `error` | `{code, message, field?, trace_id?}` | 协议错误 signal |

客户端心跳：

```json
{
  "v": 1,
  "type": "client.ping",
  "sent_at_ms": 123456,
  "payload": {}
}
```

## 关键字段注意事项

- `UnitOut.def_` 在 JSON 中就是 `"def_"`，不要改成 `def`。
- `unit.mp` 是当前 MP；移动消耗配置里 `road=1` 表示 0.5 MP。
- `terrain="castle"` 时还要看 `subtype`，不能只按 terrain 判断视觉和防御。
- 观战者 `is_spectator=true`，没有单位，不参与胜负。
- `since_seq` 是单局递增序号，重连时传最后收到的 `seq`。

## Godot 指令气泡与接口边界

Godot 客户端会根据当前 `GameStateOut` 在本地决定战斗指令气泡显示哪些按钮，但这只是 UI 筛选。所有动作仍必须调用后端接口，并以后端响应作为最终结果。

当前按钮和接口关系：

| 指令 | Godot 显示条件 | 后端接口 |
|---|---|---|
| 移动 | 轮到本玩家、单位未完成行动、`unit.mp > 0`，且可到达格不为空 | `POST /games/{game_id}/move` |
| 继续移动 | 移动后仍有 MP；或行动后单位数据/类型允许 move-after-action | `POST /games/{game_id}/move` |
| 攻击 | 敌方单位处在当前单位攻击范围内 | `GET /games/{game_id}/forecast-attack` 预览，确认后 `POST /games/{game_id}/attack` |
| 主动技能 | 当前单位存在可用主动技能且有合法目标，例如治疗友军或奥术攻击敌军 | 对应技能 action 接口；当前 Godot 仍使用既有技能封装 |
| 占领 | 单位脚下是可占领建筑，且建筑不是本方所有 | `POST /games/{game_id}/claim` |
| 待命 | 本玩家当前单位可操作时始终保留 | `POST /games/{game_id}/wait` 或客户端结束本单位操作路径 |

实现注意：

- 初始点击单位和移动后的气泡是不同语境。初始点击会显示“移动”，移动后会显示“继续移动”。
- 攻击或使用行动后，气泡只保留“待命”；如果单位 `can_move_after_action=true`，或当前兼容规则允许该单位类型行动后移动，则额外保留“继续移动”。
- 客户端不复制完整服务端规则。射程、治疗目标、占领按钮等只用于减少无效点击；后端仍可能因为状态变化、回合变化、资源变化或隐藏规则拒绝请求。
- 本地汉化只影响按钮和状态文本，不改变接口字段。请求体和响应字段继续使用后端定义的英文 key，例如 `unit_id`、`target_id`、`skill_id`、`player_id`。

## 当前接口缺口

1. Godot 尚未消费 `commentary.text/audio` 到 UI。
2. Godot 尚未统一从 `/games/units`、`/games/skills` 动态拉单位/技能表。
3. 创建房间的玩家人数、seed、地图说明、BGM meta 未完全追平 Web。
4. 玩家动作仍走 REST，WS action dispatcher 只是预留方向。
