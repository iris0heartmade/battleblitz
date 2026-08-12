# FE8 风格键盘操作设计

## 背景

Godot 客户端已经有手柄棋盘光标、`board_*` action、`ui_*` action 和 `InputHints` 提示文案。键盘目前只覆盖了方向键、Enter、Esc、Backspace 和 `+/-` 缩放,但缺少更接近 FE8 模拟器常用手感的 `Z/X/WASD/Q/E` 辅助键。

## 目标

- 棋盘和菜单共用 Godot input action,不新增独立键盘流程。
- 鼠标、手柄、键盘继续复用 `board.gd:_handle_cursor_input` 和现有按钮焦点逻辑。
- 默认键位贴近 FE8:方向键或 WASD 移动,Z/Enter/Space 确认,X/Esc/Backspace 取消,Q/E 与 `+/-` 缩放。
- `InputHints` 的键盘提示文案显示 `Z/Enter` 和 `X/Esc`,避免 UI 仍只提示 Enter/Esc。

## 架构

输入层维持三层:

- `project.godot [input]`: 定义 Godot action 到物理键位/手柄键位的映射。
- `InputHints`: 根据当前输入风格显示提示文字,只负责文案。
- `Board` / UI 控制器: 继续只消费 action 名称,不关心实际设备。

本次只改第一层和第二层,不改棋盘业务逻辑。

## 键位

| 动作 | 键盘 |
|---|---|
| 上/下/左/右 | 方向键 + WASD |
| 确认 | Z + Enter + Space |
| 取消/返回 | X + Esc + Backspace |
| 缩放近/远 | E 或 `+`,Q 或 `-` |
| 暂停 | Esc 保持现状,手柄 Start 保持现状 |

## 测试

- 在 `game/tests/test_godot_client_contract.py` 增加契约测试,读取 `project.godot` 的 action 段并断言 FE8 键位存在。
- 同一测试断言 `InputHints` 键盘文案更新为 `Z/Enter`、`X/Esc`、`E/+`、`Q/-`。
- 先运行测试看到失败,再实现映射并重跑通过。
