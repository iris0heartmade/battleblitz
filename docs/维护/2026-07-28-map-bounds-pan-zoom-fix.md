# 2026-07-28 大地图边界、佣兵站显示、缩放拖动修复

## 背景

用户反馈三个问题：

| 问题 | 根因 | 修复 |
|---|---|---|
| 4 人红方演兵地图的佣兵站显示成草地 | 客户端渲染链路需要固定验证 `b -> barracks`，避免 atlas/层级改动后回退成 plain | 新增 Godot 解码护栏脚本 `res://tools/map_loader_decode_test.gd` |
| 单位靠近 20x20 地图右侧/下侧会被服务器拉回 | 移动接口仍用全局 `MAP_SIZE=15` 判断边界，并让寻路使用默认 15 | 移动接口改为用当前战局 Tile 表判断目标是否存在，并按实际 Tile 范围传入寻路 |
| 页面/棋盘放大后自动恢复，拖动不可用 | 状态轮询反复重载棋盘并触发相机 fit；Web 每次渲染也重新 fit 到固定 15 尺寸 | Godot 缓存棋盘签名，只更新单位；Web 保留独立缩放/拖动视图状态，并按真实地图尺寸适配 |

## 修改范围

| 模块 | 文件 | 说明 |
|---|---|---|
| 后端移动 | `game/app/routes/actions.py` | 移除 15x15 硬边界，改用 Tile 表存在性与实际寻路尺寸 |
| 后端测试 | `game/tests/test_movement.py` | 覆盖 20x20 地图从 x=14 移动到 x=15 的回归场景 |
| Web 棋盘 | `game/app/web/app.js` | 真实地图尺寸适配、滚轮缩放、中键/右键拖动、渲染刷新不覆盖手动视图 |
| Web 样式 | `game/app/web/style.css` | 棋盘 transform 原点与拖动光标 |
| Godot 棋盘 | `godot-client/scripts/main.gd` | 同一地图状态刷新不再反复 `load_map`，改为增量更新单位 |
| Godot 相机 | `godot-client/scripts/board/board_camera.gd` | 用户手动定位后不被 resize / map metrics 刷新复位 |
| Godot 输入 | `godot-client/scripts/board/board.gd` | 中键也可拖动棋盘 |
| Godot 护栏 | `godot-client/tools/map_loader_decode_test.gd` | 验证 `b` 字符解码为 barracks |

## 验证

| 命令 | 结果 |
|---|---|
| `python -m pytest game/tests/test_movement.py::test_move_route_accepts_tiles_beyond_legacy_15_on_20x20_map game/tests/test_data_driven_initial_units.py::TestRedFullRosterMap -q` | 6 passed |
| `python -m py_compile game/app/routes/actions.py` | passed |
| `node --check game/app/web/app.js` | passed |

Godot 本机命令 `godot` 当前不在 PATH，未能直接跑 headless 场景；已留下 `map_loader_decode_test.gd` 作为可执行护栏。
