# #16 实施报告:SavesView 三槽重做 + in-progress 视图

> 完成时间:2026-07-23
> Branch: `refactor/extract-mainline-modules`
> 范围:接续 7/23 plan 报告 §五 5.1「前端 #16 — SavesView 三槽重做 + in-progress 视图」剩余工作

---

## 一、实施总览(8 文件 diff,+751/-433)

| 文件 | 改动 |
|------|------|
| `godot-client/scripts/ui/saves_controller.gd` | **重写**:三槽卡片 + auto 行 + suspend 行;每行内联操作(无 SaveSelectOption dropdown) |
| `godot-client/scripts/ui/in_progress_controller.gd` | **新增**:进行中视图(中断 / 活动对局 / 活动主线存档 三段列表) |
| `godot-client/scripts/mainline/mainline_controller.gd` | **删 6 函数 + 1 字段**:删 `_on_ml_slots_response` / `_render_mainline_slots` / `_on_ml_slot_*` / `_build_prepare_saves_text` 与 `_ml_slot_records` 字段;新增 `_on_ml_saves_for_cleared` 章节 cleared 标注 |
| `godot-client/scenes/main.tscn` | 新增 InProgressView + InProgressButton + 3 槽卡片容器 + 旧控件 visible=false 保留(contract test) |
| `godot-client/scripts/main.gd` | 新增 in_progress_view / in_progress_button 引用 + `_on_in_progress_pressed` + `_show_view("in_progress")` 路由 |
| `godot-client/tools/smoke_test.gd` | 6 断言新加(InProgressView 节点 / 三槽卡片渲染 / cleared 标注 / 旧节点保留) |
| `godot-client/tools/saves_flow_screenshot.gd` | 注入 mock 数据(3 槽 + auto + suspend)验证新布局 |
| `godot-client/tools/in_progress_flow_screenshot.gd` | **新增**:5 步流程截图工具(空态 → mock 数据 → 渲染 → 返回 → 重入) |
| `game/tests/test_godot_client_contract.py` | 适配 #16:mainline 改走 `_on_ml_saves_for_cleared`,断言删了旧 `_on_ml_slots_response` |

---

## 二、关键变更

### 2.1 三槽卡片重做(`saves_controller.gd`)

**前**:两个 RichTextLabel(SaveOpenList / SaveMainlineList)+ 一个 OptionButton(SaveSelectOption)+ 一个 SlotOption 下拉。

**后**:
- 1 个 VBoxContainer `SaveSlotsContainer`,代码生成 3 个固定行(代码 _build_manual_rows,不复制 tscn)
- 每行 = PanelContainer → HBoxContainer → [槽号 Label] [状态 RichTextLabel] [▶ 继续] [🗑 删除] [💾 覆盖/新建]
- 1 个 `SaveAutoRow` PanelContainer:只读行 + 「载入(会清除自动)」按钮
- 1 个 `SaveSuspendRow` PanelContainer:继续 + 放弃 双按钮(`discard_suspend` 已在 #7 实施)
- 顶部 `SaveStatus` Label:「三槽已用 X/3  ·  自动 ✓/—  ·  中断 ✓/—」
- 旧节点保留 `visible=false`(SaveOpenList / SaveMainlineList / SaveSelectOption / SaveResumeBtn / SaveDeleteBtn / SaveNewBtn / SaveRefreshBtn / SaveBackBtn / SaveSlotOption / SaveSlotLabel)— contract test + 历史脚本仍能 find 路径

**对齐 FE8**:`GameSaveBlock` 三个独立 slot,各槽自带进度。_on_save_load_response → 切 mainline + 自动 open(),槽信息回到 `mainline_view` 状态。

### 2.2 mainline 域重复 slot UI 清除

| 删除 | 行 | 备注 |
|------|---|------|
| `var _ml_slot_records: Array = []` | mainline_controller:45 + main.gd:349 | 移到 saves_view._manual_slot_records |
| `@onready var ml_slots_container` | mainline_controller:24 | tscn 节点保留(无害) |
| `_on_ml_slots_response` / `_render_mainline_slots` / `_on_ml_slot_resume` / `_on_ml_slot_loaded_response` / `_on_ml_slot_delete` / `_on_ml_slot_delete_response` | mainline_controller:133-220 | 6 函数,搬到 saves_view |
| `_on_ml_slot_resume_response` | main.gd:5267 | 复用了 `_on_resume_rejoin_response`(等价函数) |
| `open()` 中的 `list_saves(_on_ml_slots_response)` 调用 | mainline_controller:106 | 改走 `_on_ml_saves_for_cleared` |
| `_set_mainline_page` 中 `ml_slots_container.visible` 切换 | mainline_controller:117 | 节点删了,逻辑删了 |
| `_on_prepare_action_pressed` 中 `"saves"` 分支 | mainline_controller:654 | 改为「请到存档管理页」提示 |
| `_build_prepare_saves_text` | mainline_controller:803 | 改为 placeholder |

### 2.3 in-progress 视图(`in_progress_controller.gd`)

**位置**:`scripts/ui/in_progress_controller.gd`,挂在 `InProgressView` 顶层节点。
**入口**:主菜单 FooterRow 的 `InProgressButton`(▶ 进行中)。

**三段列表**(并行拉 `/saves` + `/games`):
- **⏸  中断存档**(最多 1 行,from `/saves` → `suspend`):继续(load_suspend → rejoin) + 放弃(discard_suspend)
- **🎮  进行中游戏**(最多 5 行,from `/games?user_name=` filter playing/waiting):继续(rejoin_game_by_name)
- **📖  已存档的活动主线**(N 行,from `/saves` → manual_slots with mainline_id != ""):继续(load_save) + 删除(erase_save)

**配色**:与 SavesView 完全一致(暗背景 `Color(0.02, 0.04, 0.03, 0.92)` + 金色边框 `Color(0.788, 0.631, 0.29, 1)` + 暗黄文字 `Color(0.65, 0.6, 0.45, 1)`)— 学长 #16 配色要求「和我们现在的风格一致」。

### 2.4 章节 cleared 标注(`mainline_controller.gd`)

**前**:`/mainlines` 返回章节列表,无通关标注;玩家不知道哪章节已打过。

**后**:
- `open()` 并行拉 `/saves`(为 cleared join,之前是拉主存档格的)
- `_on_ml_saves_for_cleared` 计算 `_cleared_mainline_ids`:
  - 规则 A:任意 manual slot 的 `chapter_index >= mainline.battle_count - 1` → cleared
  - 规则 B:auto slot label 以 `-结束` 结尾 → cleared
- `_render_mainline_list` 在章节按钮前加 `✓` 与后缀 `[已通关]`,不影响 disabled(可重玩)
- 缓存 `_mainline_list_cache`:`/mainlines` 响应存下来,等 `/saves` 回来后一起 join 重渲

**示例**:`chapter_01_steel_rebellion` (3 场战斗)通关存档 = `chapter_index == 2` → 按钮显示 `✓ 钢铁叛乱 · 3 场战斗  [已通关]`

---

## 三、回归测试

### 3.1 pytest

```
945 passed, 16 skipped, 1 xfailed, 0 failed
```

`test_godot_save_views_use_save_api_not_game_delete_api` 改了断言(适应 #16:删 `_on_ml_slots_response` / `_render_mainline_slots` / `ml_slots_container`,改 `_on_ml_saves_for_cleared`),16 个 contract test 全过。

### 3.2 smoke_test 增项

- SavesView 3 槽卡片容器存在 + 渲染 3 行
- SaveAutoRow / SaveSuspendRow 存在
- 旧节点保留(visible=false,find_child 仍能拿到)— contract 兼容
- InProgressView / InProgressButton 接线
- InProgressView.IPFrame/IPList/IPBackBtn 存在
- 章节 cleared 标注:`_cleared_mainline_ids` 含两个 mainline_id,首章按钮文字含「已通关」

### 3.3 截图工具(本机无 Godot binary,留待下次跑)

- `tools/saves_flow_screenshot.gd`:注入 mock(2 槽手动 + 1 auto + 1 suspend),验证 3 槽渲染
- `tools/in_progress_flow_screenshot.gd`:5 步流程(空态 → mock 拉 → 渲染 → 返回 → 重入)

---

## 四、技术资产

**新增组件模式**:`_main: Node` 跨域注入(saves / in_progress / mainline / editor 都用)。`open()` 由 main 切 view 时调用。`Callable(self, "_on_xxx")` 接所有按钮,callback 都在组件内。

**3 槽 UI 代码生成**:不复制 tscn 3 份,代码 `_build_manual_rows()` 在 `_ready()` 时建。后续如果要改槽数(目前 hardcode 3),改 `_MANUAL_SLOT_COUNT` 常量即可。

**List-cache + 双 join 模式**:`_mainline_list_cache` + `_cleared_mainline_ids` 解决「两份数据异步到达」的渲染竞态问题(任一份先到都不报错,两份齐了才完整渲染)。

---

## 五、剩余可做(下次 session)

- `ml_slots_container` tscn 节点目前是 dead node(代码已删引用,tscn 仍存在);后续清理 tscn 时一并删
- `saves_view` 与 `in_progress_view` 高度相似(suspend + mainline save 重复)— 后续可考虑抽出 `suspend_row` 共用 widget
- Resumebutton 与 InProgressButton 共存:ResumeButton 是「最近一个」一键快捷,InProgressButton 是「所有」全列表。功能不重叠,看玩家偏好

---

*#16 UI 部分全部完成,plan §三 步骤 3 UI 全部收尾。*
*下 session 接续方向:下个 plan 任务(主线非线性 P4 / 编辑器补完 / 教学系统等)*
