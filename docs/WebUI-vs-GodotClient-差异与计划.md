# BattleBlitz Web UI vs Godot Client 差异与计划

> 更新日期：2026-07-19  
> 对比范围：`game/app/web/` 与 `godot-client/` 当前工程。  
> 验证来源：代码检查、Godot 4.7 导入检查、`smoke_test.tscn`、新增 `entry_flow_e2e.tscn`，以及窗口模式截图。

## 当前结论

Godot 客户端已经接近替代原 Web UI 的日常主客户端。当前首页保留“主线章节”和“联机大厅”等入口，已删除旧的“自由对局（人机）”首页选择；自动化截图/测试仍可通过内部 `_start_dev_ai_game()` 创建 AI 对局，但这不再是用户菜单页面。

本轮已修复两个 P0 入口问题，并补上 Web UI 对齐所需的服务端权威攻击预测：

- 主线模式无法进入游戏：根因是 `Callable.bind(mainline_id)` 的回调参数顺序写反，同时全局 `/start` 响应会误处理 `/mainlines/{id}/start`。
- 联机大厅创建房间后无法稳定进入游戏：根因是创建/加入/开始流程依赖全局 `api_response`，导致大厅专用状态没有稳定保存 `player_id`，且进入 GameView 后缺少立即 `/state` 刷新。
- 攻击前伤害预测：新增只读 `GET /games/{id}/forecast-attack`，Godot 在战斗右侧信息栏展示“战斗预测”，客户端不复制伤害公式。

## 搭建进度矩阵

| 模块 | Godot 当前状态 | 和 Web UI 相比缺口 |
|---|---|---|
| 首页/菜单 | 已实现；删除“自由对局（人机）”；保留主线、联机大厅、继续、存档、编辑器、设置、退出 | 帮助/参考入口仍弱 |
| 联机大厅 | 房间列表、创建、加入、观战、队伍切换、房主控制、AI 添加/移除、BGM/指挥官选择已实现 | 房间行信息、提示、创建高级选项不如 Web 细 |
| 进入游戏 | 主线 start、联机大厅 create/join/start 均已验证可进入 GameView | 顶部队伍条仍有 `<null>` fallback 显示问题，可 polish |
| 存档/恢复 | open/mainline 分组、恢复、删除、刷新已实现 | 展示信息密度较低 |
| 战斗棋盘 | TileMapLayer + 单位节点，移动/攻击/技能/占领/招募/待命/结束回合可用 | 地块 tooltip、占领进度/归属标记待补 |
| 战斗 HUD | 回合、当前玩家、CO meter/power、战报、结算、行动面板、服务端攻击预测已实现 | 参考/帮助入口、地块 tooltip、部分 polish 待补 |
| 主线 | 列表、详情、开始、推进、下一战、放弃、指挥官选择、剧情分发已实现；409 自动 abandon 后重试已补 | 锁定原因、失败 modal、胜利专属剧情表现仍可加强 |
| 对话 | dialogue/narration/choice/battle_ref/wait 基础分发可用 | 打字速度、crest/portrait 表现可继续追 Web |
| 地图编辑器 | 基础地形/单位编辑、尺寸、撤销/重做、保存/加载/删除可用 | fill、line、select/move/recolor 等高级工具待补 |
| 设置/音频 | 名字、字号、颜色、主题、静音、BGM 轨道调用已有 | SFX、crossfade、音频 UI 细节待补 |
| 网络 | HTTP 队列、REST 封装、WS heartbeat/reconnect/since_seq 已实现 | 阶段感知轮询、诊断 HUD、WS 安全网待补 |

## 本轮验证记录

使用 `D:\Python\godot\Godot_v4.7-stable_win64_console.exe`：

```powershell
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client --import --quit
```

结果：退出码 0。仅有 `godot-client/godot-ref/godot-open-rts` 嵌套 `project.godot` 被跳过的警告，这是参考项目目录的正常行为。

```powershell
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client res://tools/smoke_test.tscn
```

结果：退出码 0，`Passed: 205 Failed: 0`。

```powershell
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client res://tools/entry_flow_e2e.tscn
```

结果：退出码 0。主线和联机大厅创建房间均进入 GameView，地块数 225。

窗口模式额外生成截图：

- `godot-client/entry_flow_mainline_game.png`
- `godot-client/entry_flow_lobby_game.png`

## 剩余优先级

1. P1：地图编辑器高级工具：flood fill、line、select/move/recolor。
2. P1：帮助/参考面板：地形、单位、技能、胜利条件、CO power。
3. P1：AI commentary UI：消费 `commentary.text/audio` 并接入战报/聊天面板。
4. P1：网络诊断：阶段感知轮询、WS 软刷新、连接诊断 HUD。
5. P2：发布 polish：修复 PNG 直接 `Image.load` 的导出 warning、SFX/crossfade、地块 tooltip、顶部 `<null>` fallback。

## Godot 参考项目说明

`godot-client/godot-ref/` 中的开源 Godot 项目只作为结构、UI、资源组织参考。Godot 导入当前项目时会跳过其中嵌套的 `project.godot`，这不是 BattleBlitz 客户端语法错误。

---

## 2026-07-19 补充：汉化与动态指令气泡

本轮继续对齐 Web UI 的可玩性和可交付状态，重点完成了两类之前容易影响实机体验的内容：

1. 静态可见 UI 已完成全局汉化。覆盖首页、主线模式、联机大厅、创建房间、设置、存档、地图编辑器、战斗 HUD、右侧单位信息栏、战斗预测、招募、指挥官技、常见状态提示和错误提示。新增 `godot-client/tools/check_chinese_ui.py`，用于扫描 `.tscn` 和 UI 相关 `.gd` 赋值，防止新增英文文案回流。
2. 战斗中的指令气泡已改为按单位当前能力动态展示，不再固定显示五个按钮。初始点击单位时展示当前可执行的移动、攻击、主动技能、占领、待命；移动后会切到移动后语境，继续显示攻击、技能、占领、待命等仍可用动作；攻击或行动后只保留待命，以及少数允许行动后继续移动的单位的继续移动按钮。

需要注意的边界：

- 指令气泡只负责 UI 层筛选，最终动作合法性仍以后端 REST 接口返回为准。
- 汉化扫描覆盖静态 UI 文案和常见动态赋值。后端返回的玩家名、地图 ID、房间名、BGM 轨道名、调试字段、未来新增数据字段仍可能含英文或原始 ID，后续应按展示入口逐步增加映射。
- Godot 导入和 smoke test 均已覆盖本轮动态按钮逻辑和地图编辑器撤销/重做。当前 smoke test 为 `Passed: 205 Failed: 0`，额外包含初始指令气泡、移动后气泡、攻击可用状态、主动治疗技能、占领按钮、编辑器撤销、编辑器重做等断言。

### 2026-07-19 追加进展：地图编辑器撤销/重做

- 新增编辑器“撤销”“重做”按钮，保持全中文 UI。
- 支持 Ctrl+Z / Ctrl+Y 快捷键。
- 地形绘制、单位放置、单位擦除、新建地图、调整尺寸会进入历史栈。
- 后端加载或保存响应会清空历史栈，避免跨地图撤销。
- 历史按钮会按栈状态自动启用/禁用。

当前剩余缺口应按以下顺序继续：

1. 地图编辑器高级工具：fill、line、select/move/recolor。
2. 帮助/参考面板：地形、单位、技能、胜利条件、CO power。
3. AI commentary UI：消费 `commentary.text/audio` 并接入战报或聊天面板。
4. 网络诊断和发布 polish：阶段感知轮询、WS 软刷新、连接诊断 HUD、PNG 导出 warning、SFX/crossfade、地块 tooltip、动态后端数据汉化映射。
