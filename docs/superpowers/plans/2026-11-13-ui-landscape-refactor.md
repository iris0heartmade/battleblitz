# 通透地貌 UI 重构实施计划

> **For agentic workers:** 使用 subagent-driven-development 分工实施，主任务负责整合、规格核对和质量复核。

**Goal:** 将已确认的通透地貌底栏接入正式游戏，并统一全部 Godot 界面视觉。

**Architecture:** 使用公共视觉配置管理颜色与透明度；公共控件保留现有业务信号；独立底栏消费现有单位与预测信息。地貌 PNG 使用透明中层，文字前层仅保留局部暗底。

**Tech Stack:** Godot 4.7 / GDScript / Python 测试与本地服务 / 内置 imagegen。

## 任务与文件边界

- [x] 1. 公共与页面视觉：`scripts/ui/menu_theme.gd`、`mainline_theme.gd`、`battle_theme.gd` 和公共组件；新增统一外部配置。覆盖标题、备战、人物装备、联机、存档、设置、剧情与结算、编辑器。保持按钮和业务行为。
- [x] 2. 战场底栏：新增独立 `scripts/ui/landscape_hud.gd`，在 `scripts/main.gd`、`hud_theme.gd` 接入；移除常驻巨型左右框，保留详情入口。单位、地形、半点移动力、预测、取消与清理必须同步；地图安全区域适配。
- [x] 3. 地貌资源：`assets/ui/terrain_hud/`，沿用已确认草原，补森林/岩地/沙地/水岸/城镇；中间低，建筑类中央主体，透明留白。资源路径集中管理，未知类型可降级。
- [x] 4. 验证：Godot 编辑器导入检查、现有 UI 与流程检查、正式服务端移动/攻击/地形更新、1280 和 1920 实机截图；检查遮挡与按钮点击，不以示意图当通过。
- [x] 5. 中文 changelog、资源说明和验证记录，列明任何未解决限制。

## 执行规则

本次继续当前工作区，保留已有未提交设计稿、用户地图和已生成草原，不清理或覆盖用户内容。子任务分文件负责，合并后统一运行。图片生成失败不连续盲试；每种成品保存实际提示词。设计已由用户确认并授权全量开发，不再次停在计划审批。

## 验证命令

Godot 使用客户端 README 指定的本地 4.7 可执行程序，先 `--headless --editor --path godot-client --quit`；再运行现有 `tools/smoke_test.tscn` 和页面/战场截图场景。Python 使用 `python -m pytest game/tests/test_godot_ui_design_tokens.py game/tests/test_godot_client_contract.py game/tests/test_godot_unit_portrait_paths.py`，并根据实际行为改动补充底栏状态检查。所有命令按真实输出记录结果。
