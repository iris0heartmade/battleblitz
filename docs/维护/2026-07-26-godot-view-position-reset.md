# BattleBlitz · Godot 页面位置漂移修复日志

## 问题摘要

在游戏中、Lobby 房间页、Lobby 选择/创建/加入页之间切换时，页面可能出现位置漂移、缩放残留或底部按钮栏飞到异常位置。

## 根因结构树

```text
页面位置漂移
├─ BoardCamera
│  ├─ 用户拖拽/缩放后 _user_positioned = true
│  └─ Board.load_map() 复用同一个 BoardCamera，apply_metrics() 跳过 fit 归位
└─ Lobby BottomBar
   ├─ in_room 模式临时改成顶部绝对布局
   └─ _restore_lobby_default_layout() 复位时 anchor_top/bottom 仍是 0.0
```

## 变更

| 文件 | 变更 | 蠢猪也能懂的说明 |
|---|---|---|
| `godot-client/scripts/board/board_camera.gd` | 新增 `apply_new_map_metrics(metrics)` | 新战斗/新地图进来时，不再继承上一局玩家拖过的镜头位置 |
| `godot-client/scripts/board/board.gd` | `load_map()` 改用新地图相机入口 | 地图加载边界统一负责镜头归位 |
| `godot-client/scripts/main.gd` | 修正 Lobby `BottomBar` 复位锚点 | 房间页临时挪过底栏后，返回选择页会重新钉回右下角 |
| `godot-client/tools/view_position_reset_test.gd` | 新增 headless 回归测试 | 自动模拟“拖歪镜头 + 切新地图”和“房间页 + 返回选择页” |

## 验证

| 命令 | 结果 |
|---|---|
| `D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/view_position_reset_test.tscn` | PASS，6 passed / 0 failed |
| `D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/smoke_test.tscn` | FAIL，527 passed / 4 failed；失败点为既有主线/存档 UI 断言，非本次相机与 Lobby 底栏改动范围 |

## 后续提醒

- 若未来需要保留“同一局内切出再切回”的镜头位置，应把镜头状态挂到具体 `game_id`，不要再挂在裸 `BoardCamera` 实例上。
- Lobby 继续增加子模式时，所有临时布局修改都要经过 `_restore_lobby_default_layout()` 归位。
