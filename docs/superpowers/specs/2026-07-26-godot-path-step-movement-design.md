# Godot Path Step Movement Design

## 背景

BattleBlitz Godot 客户端目前已经具备移动可达范围与悬停路径预览:

- `MapLogic.compute_reachable()` 计算可达格。
- `MapLogic.pathfind()` 返回 `[start, ..., goal]` 形式的最短路径。
- `main.gd::_update_path_dots_on_hover()` 在鼠标悬停时渲染路径点。

上一轮“方案 A”已经让点击移动后 500ms 内出现本地反馈,但 `Board.preview_unit_move(unit_id, to_cell)` 只消费终点格。因此多格移动会沿一条直线 Tween 到终点,视觉上像瞬移或滑翔,没有 FE/Advance Wars 类战棋应有的逐格移动感。

## 参考项目结论

### rot.js

rot.js 的 `Path.Dijkstra` / `Path.AStar` 不直接移动棋子,而是通过 `compute(fromX, fromY, callback)` 把路径上的每个格点逐个回调给调用方。路径确定与棋子动画是分层的:

```text
PassableCallback
└─ Pathfinder.compute()
   └─ callback(x, y) per path item
      └─ game code decides animation / turn consumption
```

### FE8

FE8 把移动系统拆成三个清楚的层:

```text
gBmMapMovement
├─ movement map: 记录格子是否可达/剩余移动力
├─ path arrow proc: 维护玩家选择中的路径点
└─ gWorkingMovementScript: [Dir, Dir, ..., HALT]
   └─ MU movement player: 按方向指令逐步播放单位移动
```

FE8 的关键启发不是“必须照抄算法”,而是“可达图、选择路径、移动播放”必须分层。

## 目标

移动确认后,棋子应沿当前选择路径逐格移动,同时保留 500ms 内出现反馈的手感目标。

## 非目标

- 不改变服务端移动合法性判定。
- 不改变 MP 消耗与地形成本规则。
- 不改变攻击、技能、待命等指令语义。
- 不在本次重构整个 Godot `main.gd` 行动系统。

## 推荐方案

采用“客户端路径预演 + 服务端权威校验”的轻量方案:

```text
Move Mode
├─ _move_reachable_set
├─ _path_hover_last
├─ _move_preview_path
└─ _move_preview_target

Hover Target
├─ MapLogic.pathfind()
├─ cache path for target
└─ board.show_path_marks()

Click Target
├─ resolve cached path or recompute path
├─ board.preview_unit_path(unit_id, path)
├─ clear action UI immediately
└─ NetworkClient.action_move(game_id, player_id, unit_id, to_x, to_y)
```

### 动画规则

- `Board.preview_unit_path(unit_id, path, max_total_sec = 0.45)` 负责路径播放。
- 输入 path 包含起点和终点;播放时跳过起点,依次 Tween 到 `path[1:]`。
- 每步基础时长建议 `0.09s`;总时长超过 `0.45s` 时按比例压缩。
- 单格移动与当前 0.28s 端点反馈保持相近,但多格移动必须能看出逐格节点。
- 如果新路径开始播放,必须 kill 旧 `move_tween`,避免重复指令造成节点漂移。

### 回包同步

服务端仍然是最终裁判。客户端预演后,收到 GameState/WS 更新时以权威坐标为准。若服务端拒绝移动,现有错误处理应触发状态刷新或提示,单位节点由后续快照拉回。

### 后端增强

服务端 `actions.py` 已经算出完整 `path`,但 `GameEvent.context` 未广播。建议在 move event context 增加:

```python
"path": [{"x": x, "y": y} for x, y in path]
```

这样旁观者、AI 行动回放、断线重连后的视觉播放可以使用权威路径。客户端本地玩家仍优先使用缓存路径,保障点击后即时反馈。

## 文件影响

```text
godot-client/scripts/board/board.gd
├─ 新增 preview_unit_path()
└─ 保留 preview_unit_move() 作为单终点 fallback

godot-client/scripts/main.gd
├─ 新增 _move_preview_path / _move_preview_target
├─ hover 时缓存路径
├─ click 时把 path 传给 Board
└─ 取消/结束移动模式时清空缓存

game/app/routes/actions.py
└─ move event context 附带 path

godot-client/tools/action_latency_test.gd
└─ 扩展断言:多格路径在中途格产生逐格位置变化
```

## 验收标准

| 场景 | 期望 |
|---|---|
| 鼠标悬停可达目标 | 路径点照常显示 |
| 点击多格目标 | 棋子沿路径逐格移动,不走斜线直达终点 |
| 点击后 500ms 内 | 菜单/高亮收起,棋子开始移动或出现明确反馈 |
| 连续快速下达移动预演 | 旧 Tween 被取消,不会出现位置漂移 |
| 服务端 move event | context 携带完整 path |
| 现有位置重置测试 | 仍通过 |

## 风险

- `main.gd` 文件较大,移动模式状态容易遗漏清理点。实现时必须只碰移动相关状态。
- Godot Tween 串行路径如果总时长过长会拖慢手感,所以必须设置总时长上限。
- 后端广播 path 是向后兼容字段,旧客户端忽略即可。

