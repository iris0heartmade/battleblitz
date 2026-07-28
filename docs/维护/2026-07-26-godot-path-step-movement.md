# BattleBlitz Godot 逐格路径移动日志

## 目标

移动指令下达后,棋子不再从起点直线滑到终点,而是沿 `MapLogic.pathfind()` 算出的格子路径逐格移动。手感目标仍保持:玩家点击后 500ms 内必须看到明确反馈。

## 结构树

```text
移动路径播放
├─ main.gd
│  ├─ hover 时用 MapLogic.pathfind() 计算路径
│  ├─ 缓存 _move_preview_path / _move_preview_target
│  └─ click 时把路径交给 Board
├─ board.gd
│  ├─ preview_unit_move(): 单终点 fallback
│  └─ preview_unit_path(): 逐格串行 Tween
└─ actions.py
   └─ move event context 增加 path,提供服务端权威路径
```

## 变更说明

| 文件 | 变更 | 小猪也能懂的说明 |
|---|---|---|
| `godot-client/scripts/board/board.gd` | 新增 `preview_unit_path()` | 棋子按路径一格一格走,不再像被拉直的橡皮筋一样飞过去 |
| `godot-client/scripts/main.gd` | 新增路径缓存与清理 | 鼠标悬停时算好的路线不会在点击时被丢掉 |
| `game/app/routes/actions.py` | `move` 事件增加 `context.path` | 服务端把自己算出的权威路线告诉客户端、旁观者和回放 |
| `godot-client/tools/action_latency_test.gd` | 扩展路径动画回归测试 | 自动防止未来又退化成“直线瞬移” |
| `game/tests/test_regression_move_ends_turn.py` | 新增 move event path 测试 | 自动确认后端事件真的带完整路径 |

## 验收重点

- 多格移动在中途不会已经贴到终点。
- 路径动画最终落在目标格。
- 点击移动仍在 500ms 内产生反馈。
- 取消移动、切单位、回包、回主菜单时会清理旧路径缓存。
- 后端 move event 的 `context.path[0]` 是起点,最后一项是终点。

## 二次修正

| 问题 | 修正 |
|---|---|
| 非相邻路径点会被当作世界坐标点直线 Tween | `Board.preview_unit_path()` 先把路径展开成曼哈顿直角格子段,再逐段播放 |
| 移动后必须等服务端回包才出现下一步指令 | `GameState.apply_local_move_preview()` 立即更新本地坐标与 `has_moved`,并立刻显示移动后气泡 |
| 服务端回包后可能触发第二次 FLIP | 若回包目标等于本地预演目标,`Board` 直接对齐终点并取消旧 Tween |
| 原地出现空血条残影 | `UnitNode` 清子节点时立即 `remove_child()`,且 `hp/max_hp` 未知时隐藏血条 |

