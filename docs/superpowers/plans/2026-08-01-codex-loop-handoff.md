# BattleBlitz Godot 客户端 UI 评审闭环 — Codex 接管 Prompt

## 任务

你(Codex)将接管 BattleBlitz Godot 4.7 客户端的 UI 优化 loop,目标是让**所有截图画面在 4 个独立维度的评分都 ≥ 8.5/10**。工作目录是 `/home/youko/PycharmProjects/battleblitz`,分支是 `feat/godot-mainline-fe-ui`。

**不要自动 commit 或 push**。每轮修复后用 `git add` + `git commit`,但绝不 push。保留所有 untracked 工作树修改(用户可能正在改别的)。

---

## 1. 项目背景

- **BattleBlitz** 是回合制策略战棋,Python 后端 + Godot 4.7 客户端
- 主线模式:`主线档案 → 章节详情 → 战前整备 → 战斗 → 结算`
- 当前 round:Round 5(已经完成 P0 修复 11 项,仍需推到 8.5+)
- 美术系统:**原创** frontier war council archive 风格,资产在 `godot-client/assets/ui/original_v2/`(`base/` `controls/` `battle/` 三个子目录)
- **绝对不可模仿商业游戏**(无任天堂/索尼/暴雪等)、**不可读 `docs/参考/fe_image/`**、**不可改 board/terrain/pieces/unit 渲染**

## 2. 工作目录关键文件

```
godot-client/
├── scenes/
│   ├── main.tscn                          # 根场景,所有 Panel 容器在这里
│   └── ui/
│       ├── mainline_campaign_panel.tscn   # 主线档案界面(空槽列表 + 预览 + 任务)
│       └── mainline_prepare_panel.tscn    # 战前整备界面(英雄列表 + 装备 + 任务)
├── scripts/
│   ├── ui/
│   │   ├── mainline_theme.gd              # 主线主题:常量 + apply_*_panel/row/tab
│   │   ├── mainline_campaign_panel.gd    # CampaignPanel 逻辑
│   │   ├── mainline_prepare_panel.gd     # PreparePanel 逻辑
│   │   ├── hud_theme.gd                   # 战斗 HUD 主题 + 字号补偿
│   │   └── skin_assets.gd                 # 纹理加载唯一入口(勿绕过)
│   ├── mainline/
│   │   └── mainline_controller.gd        # 主线总控:slot_requested → NetworkClient → _show_view
│   ├── main.gd                            # 战斗 HUD + 行动菜单 + 结算 + 暂停
│   └── autoload/
│       ├── game_state.gd                  # GameState 缓存 snapshot + units_changed
│       ├── dialog_manager.gd              # 对话框 + DialogOverlay 遮罩
│       └── network_client.gd              # HTTP 客户端(start_mainline 等)
├── assets/ui/original_v2/
│   ├── base/    (页面框架/卡片/织纹)
│   ├── controls/(按钮/页签/列表行/铭牌)
│   └── battle/  (HUD/侧栏/行动菜单/对话/结算)
└── tools/
    ├── ui_review_screenshot.tscn          # 截图入口
    └── ui_review_screenshot.gd            # 截图脚本(已修复 headless viewport 64×64 bug)
```

## 3. 截图 + Smoke 命令

**关键**:`--headless` 模式下 `get_viewport().get_texture().get_image()` 永远 null,**不要**带 `--headless`。直接 GPU 渲染模式跑:

```bash
cd /home/youko/PycharmProjects/battleblitz
GODOT=/home/youko/下载/Godot_v4.7-stable_linux.x86_64

# 截图(三个分辨率)
for res in "1280x720" "1600x900" "1920x1080"; do
  BB_REVIEW_RES="$res" timeout 35 $GODOT --rendering-method gl_compatibility --resolution "$res" \
    --path godot-client res://tools/ui_review_screenshot.tscn 2>&1 | grep "saved"
done
```

输出位置:`godot-client/.refactor_shots/ui_<WxH>/` 下 11 张 PNG。

**Smoke test**(必须 592/0 通过才算编译 OK):
```bash
timeout 60 $GODOT --headless --rendering-method gl_compatibility --quit-after 30 \
  --path godot-client res://tools/smoke_test.tscn 2>&1 | tail -5
```

## 4. Loop 工作流(每轮)

每轮 4 步:

**Step A — 读现状**
读所有截图(`godot-client/.refactor_shots/ui_1920x1080/*.png`):

- 主线 4 张:`mainline_slots.png` / `mainline_chapter_detail.png` / `mainline_heroes.png` / `mainline_equipment.png`
- 战斗 6 张:`battle_default.png` / `battle_unit_selected.png` / `battle_action_menu.png` / `battle_dialogue.png` / `battle_pause.png` / `battle_result.png`

**Step B — 修改**
针对仍 < 8.5 的画面,修改对应 .gd / .tscn。每次修改只动 1-2 个文件,保持 diff 小。

**Step C — 验证**
跑 smoke + 重跑截图三档,确保 592/0 + 截图正常保存。

**Step D — 评审**
启动 4 个独立 reviewer agent 并行打分(见 §6)。把分数汇总。

**Loop 终止条件**:4 个维度平均分 ≥ 8.5 **且** 每张画面单独 ≥ 8.5。

## 5. 已修复 P0(Round 5 完成)

| P0 编号 | 内容 | 状态 |
|---|---|---|
| 1 | SlotCard 用 PanelContainer + 透明 Button 热区(避免 list_row_states 金属带遮字) | ✅ |
| 2 | PreviewColumn 用 ◆✦⚔☠➤✧⌚ 图标 bullet 分行 | ✅ |
| 3 | 主操作按钮文字改"▶ 进入战役 / ▶ 开始新战役",字号 22,高度 76 | ✅ |
| 4 | `PreparePanel/ActionBar` 残留导致右栏被覆盖 → 截图工具改用 `find_child` 精准显隐 | ✅ |
| 5 | propagate_call 副作用导致 prepare 切回空白帧 → 同上 | ✅ |
| 6 | `--headless` 下 viewport 64×64 → 改 GPU 渲染模式 | ✅ |
| 7 | bug B:敌方英雄击杀 sprite 残留 → `game_state.gd` kill 分支 emit `units_changed` | ✅ |
| 8 | 招募佣兵 UI 重叠 → `RecruitList` 套 `RecruitScroll` ScrollContainer | ✅ |
| 9 | `apply_slot_card_panel` 找不到 `hit_button` meta 错误 → 先 set_meta 再 apply | ✅ |
| 10 | `开始新游戏` 按钮无反应 → `_on_slot_new_game_pressed` 立即切 PreparePanel + mock payload | ✅ |
| 11 | 进入战役偏远无引导 → `PreviewHint` 加引导文字 "← 在左侧选档 · 右下「进入战役」开始" | ✅ |

## 5.5 用户手动增量(Round 5 之后接手时)

以下结构是我交接后用户手写的,codex 接管时**不要 revert**,直接基于这些结构继续:

- `scripts/ui/mainline_theme.gd`:新增 `C_PARCHMENT_INK` / `C_PARCHMENT_DIM` / `C_PARCHMENT_ACCENT` 三个 parchment 内容区配色常量(用在 PreviewColumn 的 BriefingPanel 等 parchment 内部)
- `scenes/ui/mainline_campaign_panel.tscn`:PreviewColumn 内部拆出独立 `BriefingPanel`(下一战简报子面板,占下方 ~210px);IntelColumn 改名为 `IntelTitle="行动指引"`,加 `IntelStatus` 状态指示 Label(`◆ 选择一个档案`);`PreviewHint` 14pt 居中引导;`PreviewBody` 加 `custom_minimum_size (0, 154)` 强制撑开
- `scripts/ui/mainline_campaign_panel.gd`:`set_mission` / `set_heroes` 等签名扩展 — `set_mission(title, body)` 现在把战役标题下沉到正文并写 `MissionChecklist`(出征核对列表);set_slots / select_slot / _make_slot_card 行为不变
- `scripts/ui/mainline_prepare_panel.gd`:新增 `_apply_responsive_layout()`(监听 `viewport.size_changed`);`_select_hero(hero_id)` + `_refresh_hero_selection()`(英雄卡选中态追踪);`_refresh_content_insight(choice_index)`(根据当前 tab + 装备选择刷新右侧 `InsightTitle`/`InsightBody`/`ContentKicker` 三个洞察 Label);`%MissionChecklist` 出征核对文本 + `set_prepare_ready` 文字改为 `"1  完成整备"` / `"2  开始战斗 →"`
- `tools/ui_review_screenshot.gd`:已升级,支持 BB_REVIEW_RES env + `--resolution=WxH` 兜底 + `find_child` 精准显隐 + GPU 渲染模式(不带 `--headless`)

> **Codex 接手后第一件事**:跑 `git status` 看 uncommitted 修改,确认这些结构都在;然后 `Read` 这几个文件拿到当前最新内容,**不要假设**你之前看到的内容是最新的。

## 6. 4 个评审 Agent 配置(复制粘贴到 subagent 调用)

### 6.1 通用主观题段(每个 agent 都必须先答)

```
## 必答主观题(不计入客观分,但触发下一轮修复)

在打分之前,先回答这 5 题。每题 0-10 分,主观分单独列出。

1. 【点击欲】看到这画面,你的第一反应想不想点?
   0=想关掉 / 5=无感 / 10=迫不及待想点

2. 【直觉性】不看任何文字,只看布局和图标,你能猜出几件事:
   - 这是什么界面?(是/否)
   - 该点什么?(是/否)
   - 会发生什么?(是/否)
   答对 3 个=10 / 2 个=7 / 1 个=4 / 全猜错=0

3. 【5秒测试】5 秒后你能记住这个画面的 3 个关键信息吗?
   全记住=10 / 记住 2 个=7 / 1 个=4 / 完全没记住=0

4. 【情绪反应】用一个词描述心情:
   - 兴奋 / 安心 / 好奇 / 平静 → 8-10
   - 困惑 / 焦虑 / 无聊 / 压迫 → 0-4

5. 【品牌辨识度】给一个玩过 50+ 战棋的人看,能不能立刻判断"这不是某商业游戏"?
   10=一眼原创 / 5=可能有混淆 / 0=像某商业游戏

主观分平均 < 6 的画面,即使客观分 ≥ 8.5,也必须进入下一轮修复。
```

---

**Agent #1 — 主线叙事引导**

```
你是 UI 评审 agent #1(主线叙事引导维度),请严格评估 BattleBlitz 主线界面。

评分尺度(0-10,比业界严苛):
- 9-10:世界级,看一眼就知道怎么玩
- 8.5:优秀,玩家一次能理解所有功能
- 8:良好,但仍有可察觉的瑕疵
- 7:及格,有明显问题
- < 7:不合格

任务:
1. 先回答 §6.1 通用主观题段(5 题) — 不计入客观分
2. 读以下截图(每张都要看):
   - godot-client/.refactor_shots/ui_1280x720/mainline_slots.png
   - godot-client/.refactor_shots/ui_1280x720/mainline_chapter_detail.png
   - godot-client/.refactor_shots/ui_1280x720/mainline_heroes.png
   - godot-client/.refactor_shots/ui_1280x720/mainline_equipment.png
   - godot-client/.refactor_shots/ui_1600x900/mainline_slots.png
   - godot-client/.refactor_shots/ui_1920x1080/mainline_slots.png
   - godot-client/.refactor_shots/ui_1920x1080/mainline_chapter_detail.png
   - godot-client/.refactor_shots/ui_1920x1080/mainline_heroes.png
   - godot-client/.refactor_shots/ui_1920x1080/mainline_equipment.png

3. 对每张图按 6 维度打分(总分 = 平均,需 ≥ 8.5):
   a) 视觉层次(字号/颜色/对比度是否清晰传递"哪个重要")
   b) 信息密度(布局是否填满但不过载)
   c) 叙事引导(玩家能否一眼理解"这是什么/下一步做什么")
   d) 选中/悬停反馈(选中态是否清楚)
   e) 中文渲染(中文截断/换行/字距)
   f) 整体一致性(主操作/次操作/禁用态视觉差异)

4. 输出:主观 5 题分 + 客观 6 分 + 总分(仅客观平均)+ 扣分原因。
   最后给主线维度平均分(客观 6 维平均)。
```

**Agent #2 — 战斗 HUD**

```
你是 UI 评审 agent #2(战斗 HUD 维度),请严格评估 BattleBlitz 战斗 HUD。

评分尺度:同 agent #1。

任务:
1. 先回答 §6.1 通用主观题段(5 题)
2. 读以下截图:
   - godot-client/.refactor_shots/ui_1280x720/battle_default.png
   - godot-client/.refactor_shots/ui_1280x720/battle_unit_selected.png
   - godot-client/.refactor_shots/ui_1280x720/battle_action_menu.png
   - godot-client/.refactor_shots/ui_1280x720/battle_dialogue.png
   - godot-client/.refactor_shots/ui_1280x720/battle_pause.png
   - godot-client/.refactor_shots/ui_1280x720/battle_result.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_default.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_unit_selected.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_action_menu.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_dialogue.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_pause.png
   - godot-client/.refactor_shots/ui_1920x1080/battle_result.png

3. 6 维度:
   a) 信息可读性(HP/MP/回合/阶段/金币)
   b) 行动菜单(可用/不可用 + 理由)
   c) 模态覆盖(对话框/暂停/结算是否压暗背景)
   d) 单位视觉(选中态/范围高亮)
   e) 中文渲染
   f) 整体一致性(顶栏/侧栏/行动菜单权重)

4. 输出:主观 5 题分 + 客观 6 分 + 总分(客观平均)+ 扣分原因。
```

**Agent #3 — 响应式断点**

```
你是 UI 评审 agent #3(响应式 / 三档断点评测维度)。

评分尺度:同 agent #1。

任务:
1. 先回答 §6.1 通用主观题段(5 题)
2. 每个截图 × 3 分辨率 = 30 张图,全部读:
   godot-client/.refactor_shots/ui_1280x720/*.png
   godot-client/.refactor_shots/ui_1600x900/*.png
   godot-client/.refactor_shots/ui_1920x1080/*.png

3. 6 维度:
   a) 内容不溢出(没有文字/按钮溢出 panel)
   b) 内容不截断
   c) 大面积留白(有没有"大块空"的失重感)
   d) 自适应布局(三档之间视觉优雅伸缩)
   e) 元素比例(字号/按钮/卡片大小合理变化)
   f) 中文密度(1920 下文字稀疏或拥挤)

4. 输出:主观 5 题分 + 客观 6 分 + 总分(客观平均)+ 扣分原因。
```

**Agent #4 — 交互引导**

```
你是 UI 评审 agent #4(交互引导维度)。

评分尺度:9-10 第一秒就懂;8.5 一眼懂 80%;8 能上手但要试几次;7 会卡住。

任务:
1. 先回答 §6.1 通用主观题段(5 题)
2. 读 1920x1080 主流程截图 8 张:
   - mainline_slots.png(从这里开始)
   - mainline_chapter_detail.png
   - mainline_heroes.png
   - mainline_equipment.png
   - battle_default.png
   - battle_unit_selected.png
   - battle_action_menu.png
   - battle_result.png

3. 5 维度:
   a) 玩家能否一眼看出"这是什么"
   b) 玩家能否一眼看出"下一步做什么"
   c) 主操作按钮是否显眼(进入战役/开始战斗)
   d) 禁用/不可用状态是否合理灰显(避免点了空响应)
   e) 视觉权重匹配语义权重

4. 输出:主观 5 题分 + 客观 5 分 + 总分(客观平均)+ 扣分原因。
```

## 7. 当前 Round 5 评审基线(2026-08-01 测得)

| 维度 | 平均分 | 状态 |
|---|---:|---|
| 主线叙事引导 | **4.28** | ✗ 远低(因为 hero/equipment 在 P0 fix 之前整屏空白) |
| 战斗 HUD | **7.40** | ✗ 差 1.10 |
| 响应式断点 | **7.82** | ✗ 差 0.68 |
| 交互引导 | **6.45** | ✗ 差 2.05 |

> 实际分数会因为 P0 fix 后上升,但用户希望**每张图都 ≥ 8.5**(不是平均)。需要继续优化。

## 8. 已知 P1 / P2 问题(优先修这些)

按评分差距排序(差距 = 8.5 − 当前分):

### 主线(P0 之后仍有)
1. **PreviewColumn 中栏底部大片留白**(1920x1080 占 ~60%):当前 7 行 bullet 用完顶部 1/3,下方 2/3 全空。
   - **修复方向**:在 PreviewBody 之后追加"地图缩略图"TextureRect(占下方 40% 高度),或者用 2 列布局(图标+描述在左,小地图在右)。
2. **IntelColumn 内容重复 PreviewColumn**(7.3):"出征情报"栏只显示章节名/进度,和预览栏重复。
   - **修复方向**:把"出征情报"改成"下一战情报",内容只放:胜利条件、敌方预览、推荐装备。
3. **1280x720 下 chapter_detail 字体偏小**(7.3):预览栏 16pt 在 720p 下视觉拥挤。
   - **修复方向**:hud_theme 字号补偿分支已存在,但 mainline_theme 没有,加 `_preview_body.font_size = 14 if vp.x <= 1366 else 16`。

### 战斗 HUD
4. **顶栏字号偏小**(battle_default 8.0):回合/队伍名/资源数字小,1920 下应 16-18pt。
   - **修复方向**:`hud_theme.gd` `apply_hud` 字号已扩展到 18,但顶栏仍有 14pt,需要在 main.gd 顶栏设置处强制 `font_size = 16`。
5. **右侧指挥官面板下半部留白**(battle_default 8.0):约 30-45% 高度空白。
   - **修复方向**:在 InfoPanel 下半部加"战场情报"小卡:回合数、胜利条件、当前任务、AI 思考状态。
6. **battle_result "返回联机大厅"灰显缺原因**(8.7,差 0.2):目前按钮 disabled 但鼠标 hover 不显示原因。
   - **修复方向**:`main.gd:show_battle_result` 把 disabled 按钮的 `tooltip_text` 设成"需要先在联机大厅创建对局"。

### 响应式
7. **1280x720 battle 左翼黑边**(8.0):左翼在 1280 下不显示,但 board 没扩展到 viewport 左缘,留 ~100px 黑边。
   - **修复方向**:在 1280 下把 board 的 `offset_left` 减 50px,腾给左翼(虽然隐藏但视觉对齐)。
8. **1920x1080 中文密度显得稀疏**(8.4):字号未随分辨率加大。
   - **修复方向**:`hud_theme.gd` 已实现 `pill_size = 20 if vp.x <= 1366 else 14` 反向补偿,再加 mainline/battle 字号 1.1× 在 1920。

## 9. 硬约束(不可破坏)

1. **不要修改**:
   - `godot-client/scenes/board*.tscn`(棋盘布局)
   - `godot-client/scenes/battle_*.tscn` 中地形/单位层
   - `game/maps/*.json`(地图数据)
   - `godot-client/scripts/board/*.gd`(棋盘逻辑)
   - `godot-client/scripts/battle/*.gd` 中 pathfinding/胜负判定
   - `godot-client/assets/ui/original_v2/sources/`(仅作 traceability)
2. **不要读** `docs/参考/fe_image/` — 这是商业参考图,只看规范文档 `docs/规范/`。
3. **不要模仿** 商业游戏角色/徽章/公司/艺术家风格。
4. **不要 push** 到 origin(用户已经手动 push)。
5. **不要删除** 现有 untracked 文件(用户可能正在改)。
6. **不要让 smoke 掉** — 任何修改必须保持当前基线 608/0 通过。

## 10. 每轮结束的报告格式

完成一轮 loop 后,给用户报告:

```
## Round X 完成

### 4 维度评分(客观 6/5 维平均)
| 维度 | 上轮 | 本轮 | Δ |
|---|---:|---:|---:|
| 主线叙事引导 | X.XX | X.XX | ±X.XX |
| 战斗 HUD | X.XX | X.XX | ±X.XX |
| 响应式断点 | X.XX | X.XX | ±X.XX |
| 交互引导 | X.XX | X.XX | ±X.XX |

### 主观题平均分(5 题平均)
| 维度 | 点击欲 | 直觉性 | 5秒测试 | 情绪 | 品牌 | 主观平均 |
|---|---:|---:|---:|---:|---:|---:|
| 主线 | X.X | X.X | X.X | X.X | X.X | X.X |
| 战斗 | X.X | X.X | X.X | X.X | X.X | X.X |
| 响应式 | X.X | X.X | X.X | X.X | X.X | X.X |
| 交互 | X.X | X.X | X.X | X.X | X.X | X.X |

### 本轮修改
- <文件:行> 改了什么(一句话)
- ...

### 触发下轮的画面(任一条件即触发)
- 客观分 < 8.5:画面名(当前分)
- 主观平均 < 6:画面名(主观分)
- 主观分任一项 < 4:画面名(单项名 + 分)

### 下轮计划
1. (按 max(客观差距, 主观差距) 排序)
2. ...
```

如果所有画面 ≥ 8.5 客观 **且** ≥ 6 主观:
```
## Round X 完成 — 验收通过 ✅

### 最终评分
<4 维度平均 / 每画面得分表>

### 累计 commit 数
git log --oneline -n <N>
```

## 11. 已知小技巧

- 截图工具 `ui_review_screenshot.gd` 已修好,但 `_save` 函数仍然用 `get_viewport().get_texture().get_image()` — 这个调用**必须**不带 `--headless` 才能成功。
- `apply_slot_card_panel` 必须先 `set_meta("hit_button", hit)` 才能调用,否则报 `meta 'hit_button' not found`。
- `_show_view` 不切换 CampaignPanel/PreparePanel 显隐,这俩 panel 显隐由 controller `_set_node_visible` 控制。
- `NetworkClient.start_mainline` 在无后端时会 10s 超时,玩家会感觉无反应。已用 `_on_slot_new_game_pressed` 立即切 PreparePanel 绕过。

## 12. 启动指引

第一次启动时:
1. 读 `git log --oneline -n 30` 看 Round 5 已有 commit
2. `git status` 看 uncommitted 修改(应该是空的)
3. 读 `godot-client/scripts/mainline/mainline_controller.gd` 的 `_on_slot_new_game_pressed`(在 ~line 439)确认当前 mock payload 实现
4. 读 `godot-client/scripts/ui/mainline_campaign_panel.gd` 和 `mainline_prepare_panel.gd` 理解 UI 接口(已扩 _apply_responsive_layout / _refresh_content_insight)
5. 跑 smoke + 截图基线,确认环境正常
6. 进入 Loop

## 13. 主观题常见陷阱(给 codex 的反例)

避免评审 agent 在主观题上**走过场**或**和稀泥**:

1. **不要默认给 7-8 分**。如果画面平淡无特色,点击欲应该 3-4。如果画面有"wow"感,点击欲应该 9-10。
2. **直觉性必须真的盖住文字猜**。如果需要读"开始新战役"才知道做什么,直觉性 ≤ 5。
3. **品牌辨识度警惕"千篇一律"**。如果一个战棋游戏看起来像所有战棋游戏,品牌辨识度 ≤ 5。BattleBlitz 必须有独特配色(墨蓝织纹 + 金边 + 暗红封签 + parchment)才能拿高分。
4. **情绪反应词必须明确**。"还不错"这种模糊词不接受,必须从给定 8 个词里选一个。如果评审犹豫,说明画面情绪不到位,该扣分。
5. **主观分和客观分不一致是信号**。客观 9 分但主观 4 分 = "完美但无趣",比客观 6 主观 7 更该修(后者至少有意思)。

## 14. 主观题 vs 客观题的权重

当客观分和主观分冲突时,**主观分优先**(因为玩家不会分析字号,他们只看感受)。

但触发下轮修复的**任一**条件:
- 客观分 < 8.5(质量不达标)
- 主观平均 < 6(感受不达标)
- 主观任一项 < 4(单维度严重问题,如点击欲 < 4 = 玩家会立刻关掉)

---

现在你可以开始第一轮 loop。祝好运。

## 15. Codex 会话恢复与网络排障

本机若需要继续这次 UI loop，可恢复既有 Codex 会话：

```bash
codex resume 019f7093-1059-7743-8a5e-5e04171f0d86
```

只有在确认当前仓库、命令和未提交文件都可信时，才追加 `--yolo`；恢复会话本身不要求关闭审批保护。

如果 Codex 能通过 HTTPS 工作但 WebSocket 超时，或提示 provider endpoint 不可达，先运行：

```bash
codex doctor --summary
```

已知本机可用的临时代理位于 `127.0.0.1:7890`。仅在本地代理服务确实运行时，在当前终端设置：

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
export ALL_PROXY=http://127.0.0.1:7890
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"
export all_proxy="$ALL_PROXY"
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy="$NO_PROXY"
```

设置后重新运行 `codex doctor --summary`。如果代理未启动或排障结束，用以下命令清理当前终端变量：

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy
```

不要把 `codex doctor` 的整段机器路径、临时状态或未来可能出现的认证信息复制进长期项目文档；文档只保留可重复的诊断步骤。
