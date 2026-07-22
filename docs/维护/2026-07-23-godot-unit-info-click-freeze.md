# 2026-07-23 Godot 单位点击卡死修复

## 现象

刚开局点击骑士单位后，Godot 调试器暂停：

`Invalid call 'String' constructor: 连击`

栈顶位于 `godot-client/scripts/main.gd::_refresh_unit_info()`，由单位点击链路触发：

`_on_board_unit_clicked -> _handle_unit_click -> _refresh_unit_info`

## 根因

右侧单位信息面板刷新战斗加成时，直接用 `String(tile_d.get("subtype", ""))` 转换快照字段。Godot 4 对部分 Variant 值不接受 `String(...)` 构造，字段内容又可能来自后端快照或客户端临时状态，因此会在 InfoPanel 刷新阶段中断整局交互。

## 修复

- `terrain` / `subtype` 读取改为先处理 `null`，再使用 `str(...)`。
- 在 Godot smoke 中加入回归场景：构造带非标 `subtype` 的 tile，并调用 `_refresh_unit_info()`，确保点击单位不会因为信息面板字符串化失败而卡住。

## 验证

已通过：

`D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/smoke_test.tscn`

结果：`Passed: 517 Failed: 0`
