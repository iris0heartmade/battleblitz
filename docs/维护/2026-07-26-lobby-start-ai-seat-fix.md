# 2026-07-26 联机大厅开局与 AI 座位修复

## 背景

- 创建房间页点击「开启游戏」后，会先短暂切到房间内页，再进入游戏页，玩家视角出现多余页面跳转。
- 4 人地图中，多个座位无法同时设置 AI 替补；给第三个座位设置 AI 时，会把第二个座位的 AI 替补清掉。

## 根因

- 创建房间自动开局链路在 `join` 成功后先执行 `_show_lobby_in_room()` 和大厅轮询，再继续配置 AI/team/start。
- 前端 `_on_lobby_seat_ai_toggled()` 与 `_clear_player_from_other_seats()` 把 AI 替补当成全局唯一状态清理。
- 后端 `/games/{id}/add-ai` 只支持追加到下一个可用座位，不支持指定 seat。

## 修复

- 自动创建并开局时，`join` 成功后直接进入配置流水线，不再渲染中间房间页。
- AI 替补改为按座位独立保存；清理函数只保证同一真人玩家不会占多个座位。
- `AddAIRequest` 增加可选 `seat`，后端按指定空座位创建 AI，并保留旧的自动选空座行为。
- Godot `NetworkClient.add_ai_player()` 增加可选 seat 参数，座位卡和创建流水线都会把目标座位传给后端。
- 创建页「开启游戏」按地图要求席位数禁用：房主座位 + AI 替补座位未补齐时不能创建并开局。
- 房间内「启动游戏」按服务端 `capacity` 禁用：非观战参战方未达到地图要求时不能启动。
- 4 人座位卡高度从 160 增加到 190，并给指挥官描述固定高度、自动换行与裁剪，避免文字压到下一行座位卡。
- 检查首页按钮：`HelpButton`、`SettingsButton`、`InProgressButton`、`SavesButton`、`EditorButton` 均有回调连接；`ResumeButton` 为动态显示入口，暂不删除。

## 验证

```powershell
python -m pytest game/tests/test_team_mode.py game/tests/test_godot_client_contract.py -q
```

结果：`45 passed`。
