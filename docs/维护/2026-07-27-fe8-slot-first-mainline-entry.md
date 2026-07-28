# 2026-07-27 FE8 三槽优先主线入口

## 背景

原 Godot 主线入口直接展示所有主线章节,体验更像“选关列表”,不符合 FE8 的三正式存档槽机制。FE8 的核心是先进入某个存档槽,再由槽内进度决定当前最新章节。

## 本次调整

- `MainlineView.open()` 改为先请求 `/saves`,渲染 3 个正式手动槽。
- 已有槽点击“继续”会先 `load_save`,再按该槽的 `mainline_id` 进入章节详情/整备。
- 空槽点击“新游戏”从 `chapter_01_steel_rebellion` 开始,并写入对应手动槽。
- 默认玩家入口不再调用 `/mainlines` 展示全部章节;章节列表逻辑保留为内部调试/旧流程兼容辅助。
- 菜单与主线页标题从“主线章节”改为“主线存档”。

## 验证

- `python -m pytest tests/test_godot_client_contract.py`
- `python -m pytest tests/test_save_slot_independence.py tests/test_mainline_chain_gates.py`
