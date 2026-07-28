# BattleBlitz · Godot 指令响应手感优化日志

## 目标

移动、攻击等指令下达后,玩家必须在 500ms 内看到明确反馈。服务端仍是最终裁判,客户端只负责先把“指令已经下达”的视觉动作演出来。

## 根因结构树

```text
操作慢感
├─ 移动
│  ├─ 原流程:点击目标格 -> 发 REST/等 WS/刷新后才看到单位变化
│  └─ 玩家感受:点了但画面没马上动
└─ 攻击
   ├─ 原流程:确认攻击 -> 等服务端事件后才出现伤害反馈
   └─ 玩家感受:确认按钮像按进棉花里
```

## 变更

| 文件 | 变更 | 蠢猪也能懂的说明 |
|---|---|---|
| `godot-client/scripts/board/board.gd` | 新增 `preview_unit_move()` | 移动指令提交时,棋子先本地滑向目标格,不用等网络回包 |
| `godot-client/scripts/main.gd` | 新增 `_apply_immediate_move_feedback()` | 点击移动目标后立刻隐藏菜单/高亮并播放移动预演 |
| `godot-client/scripts/main.gd` | 新增 `_apply_immediate_attack_feedback()` | 确认攻击后立刻在目标格显示攻击标记,伤害仍等服务端 |
| `godot-client/tools/action_latency_test.gd` | 新增 500ms 回归测试 | 自动检查移动/攻击是否在 500ms 内出现本地反馈 |

## 设计边界

- 不预测伤害、不预扣 HP。
- 不改后端接口。
- 服务端事件或后续 state snapshot 到来后,仍由现有 `GameState.units_changed` / `unit_attacked` 流程校正和显示最终结果。
- 本地移动预演时长为 0.28s,低于 500ms 目标线。

## 验证

| 命令 | 结果 |
|---|---|
| `D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/action_latency_test.tscn` | PASS, 8 passed / 0 failed |
| `D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/view_position_reset_test.tscn` | PASS, 6 passed / 0 failed |

## 后续提醒

- 若未来加入技能/占领/等待的即时演出,优先沿用 `main.gd` 的 `_apply_immediate_*_feedback()` 命名和“先反馈,后请求”顺序。
- 若要做更激进的手感优化,再考虑客户端乐观更新 `GameState`;本轮刻意不做,避免和服务端权威状态打架。
