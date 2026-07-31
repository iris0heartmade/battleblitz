# Godot 界面原创美术升级与多 Agent 实施计划

日期：2026-07-31

状态：待审核

适用分支：`feat/godot-mainline-fe-ui`

关联文档：`docs/规划/主线/2026-07-28-Godot主线与装备界面美术改造方案.md`

## 1. 目标与范围

本轮目标是在不改动玩法和地图表现的前提下，统一并提升 Godot 客户端的边框、菜单、面板、按钮、页签、列表和状态反馈，使主线流程与战斗 HUD 形成一套可维护的原创视觉系统。

本轮包含：

- 主线存档、章节选择、战前准备、英雄、装备、佣兵、商店等界面容器。
- 战斗 HUD 的顶部状态条、左右信息区、单位详情、行动菜单、对话框、暂停与结算弹窗。
- `Theme`、`StyleBox`、`NinePatchRect`、布局容器和交互状态的统一。
- 原创、透明、无烘焙文字的 UI 位图资产及其来源记录。
- 1280 x 720、1600 x 900、1920 x 1080 三档截图和交互回归。

本轮明确不包含：

- 地图瓦片、地形、建筑、棋子、单位动画及棋盘渲染效果。
- 地图生成、寻路、战斗规则、后端接口与存档格式。
- 任何第三方角色、头像、Logo、徽记、字体、图标或 UI 切片。

预计改动量为中大型 UI 重构：约 8 至 14 个原创资产组、4 至 7 个 UI 脚本/场景入口、1 份来源清单、2 至 4 个截图工具或用例。公共 `main.gd` 与主题入口必须由主 Agent 独占合并，避免并行冲突。

## 2. 参考图的使用边界

`docs/参考/fe_image` 中 7 张商业游戏截图仅用于内部设计研究。它们不进入 Git、发行包、PR 截图、生图输入或对外文档。本节是工程风控约束，不替代法律意见。

### 2.1 可以提取的抽象规律

- 功能层级：主任务、次级管理、说明和输入提示如何分组。
- 通用交互：选中、悬停、按下、禁用、焦点、弹窗和返回路径。
- 信息密度：角色摘要、候选列表、物品清单、容量与状态如何被快速扫读。
- 视觉关系：暗背景与暖色强调、主次边框、留白、遮罩和局部高亮。
- 可用性指标：字号、行高、触控面积、对比度和分辨率适配。

### 2.2 禁止提取或复刻的内容

- 禁止描摹、裁切、重绘、重着色、轮廓追踪或像素级复制参考截图。
- 禁止复制角色、头像、台词、名称、Logo、阵营徽记、武器图标、专有符号和字体设计。
- 禁止复刻独特边框轮廓、中心徽记、角部花纹、菜单几何结构和整屏构图比例。
- 禁止从截图直接吸取色值，或用截图作为图生图、风格参考、ControlNet 等生成输入。
- 禁止在提示词、文件名、代码注释中使用商业游戏、系列、公司、角色或艺术家名称。
- 禁止以“像某已发行游戏”为验收标准；验收只看原创性、层级、可读性和操作反馈。

### 2.3 Clean-room 流程

1. 参考分析 Agent 是唯一允许查看 `docs/参考/fe_image` 的生产角色，只输出抽象规范。
2. 合规审查 Agent 删除可重建原图的轮廓、比例、专有母题和来源暗示，形成批准版简报。
3. 生图 Agent 只接收批准版简报和 BattleBlitz 自有设定，不读取商业截图。
4. 代码 Agent 只接触已批准资产、设计 Token 和组件规格。
5. 独立相似度审查 Agent 在最后同时查看参考与候选成品，只负责拒收，不参与生成。

现有资产中的“对称金色卷草 + 四角纹章 + 中心红色宝石”组合需要重新核验。单一元素可能通用，但组合、比例和节奏过于接近时仍可能形成显著近似。未经复核的旧资产标记为 `legacy-unverified`，不得继续扩散到新组件。

## 3. 从参考图得到的非专有设计结论

7 张参考图按文件名排序记为 R1 至 R7，仅保留以下抽象结论：

| 参考组 | 可安全采用的规律 | BattleBlitz 的原创转译 |
|---|---|---|
| R1 | 主视觉与单侧菜单分离，选中项同时依赖亮度和局部强调 | 主菜单采用“边境夜巡”氛围背景，单侧军令列表；不用原图人物、光带形状和比例 |
| R2 | 章节过场只保留标题、阶段和材质背景 | 使用项目自有“军情封签”与行军坐标刻线；不用原图徽记、皮革压纹和构图 |
| R3/R5 | 一级任务与二级管理分层，背景压暗，当前项反馈强 | 采用非对称“军议签条 + 侧向抽屉”，不用圆盘式结构和特征性旋转动效 |
| R4/R6 | 当前角色摘要与候选列表构成主从关系，整行选中反馈 | 采用军籍卡、纵向名册和固定行高，不复制头像尺寸、栏位比例和装饰 |
| R7 | 双栏管理页使用一致的列表语法，数量右对齐 | 装备页采用“随身装备 / 军需仓”双栏，使用项目原创图标和档案纸纹理 |

统一原则是三层分离：场景氛围层负责世界感，功能容器层负责信息组织，即时反馈层负责操作确认。装饰不能代替层级，也不能压过地图和正文。

## 4. 原创视觉方向：边境军议档案

本项目不继续追求外部作品的视觉相似度，而从 BattleBlitz 自身的边境、城堡、军团和远征概念建立“边境军议档案”语言。

### 4.1 材质与母题

- 主材质：墨蓝织纹、烟黑氧化钢、旧黄铜、暗红封签、暖灰档案纸。
- 原创母题：城垛缺口、行军路线折线、地图坐标刻度、铆钉、旗杆绳结、方形封签。
- 禁用母题：翼形王室徽饰、中心宝石徽记、对称卷草花边、圆形仪盘、可识别宗教或学院纹章。
- 一级页面只使用宽框和少量角饰；二级面板使用细边和单侧标记；三级控件只保留简洁描边。

### 4.2 设计 Token

Token 的最终色值由第一轮截图校准后冻结，禁止直接从参考图取色。

| Token | 用途 | 初始方向 |
|---|---|---|
| `surface/base` | 全屏底层 | 近黑墨蓝 |
| `surface/panel` | 主要容器 | 低饱和深蓝织纹 |
| `surface/paper` | 清单与装备明细 | 暖灰档案纸 |
| `line/primary` | 一级框线 | 哑光旧黄铜 |
| `line/secondary` | 二级分隔 | 深灰钢 |
| `accent/focus` | 当前焦点 | 琥珀亮边 |
| `accent/ally` | 友军与确认 | 青绿色 |
| `accent/enemy` | 敌军与危险 | 暗绯红 |
| `text/primary` | 正文 | 暖灰白 |
| `text/muted` | 次要信息 | 灰蓝 |

焦点状态至少组合两种反馈，例如亮边加 2 px 位移、色条加图标、背景带加字号变化；不能只改颜色。动效限制在 120 至 220 ms 的淡入、滑入和描边扫光，不使用特征性旋转菜单。

## 5. 现状与代码落点

### 5.1 已有可复用资产

- `godot-client/assets/ui/rebuild/battle/panel_frame_9slice_384_v1.png`
- `godot-client/assets/ui/rebuild/battle/compact_hud_plaque_180x72_v1.png`
- `godot-client/assets/ui/rebuild/battle/top_status_rail_clean_1000x96_v2.png`
- `godot-client/assets/ui/rebuild/equipment_*.png`
- `godot-client/assets/ui/rebuild/stat_*.png`
- `godot-client/assets/ui/chapter_banner_v1.png`

这些资产在接入前必须完成来源复核、透明边距检查、NinePatch 安全区检查和近似风险审查。现有 `godot-client/assets/ui/rebuild/README.md` 继续作为运行时用法说明，但来源信息迁移到新的资产清单。

### 5.2 主线与装备入口

- `godot-client/scenes/ui/mainline_campaign_panel.tscn`：章节/存档三栏结构。
- `godot-client/scripts/ui/mainline_campaign_panel.gd`：章节选择、预览和操作状态。
- `godot-client/scenes/ui/mainline_prepare_panel.tscn`：名册、内容、任务摘要和底部操作条。
- `godot-client/scripts/ui/mainline_prepare_panel.gd`：英雄、装备和准备内容渲染。
- `godot-client/scripts/ui/mainline_theme.gd`：主线按钮、页签、下拉框和面板主题。
- `godot-client/scenes/main.tscn`、`godot-client/scripts/main.gd`：旧主线节点兼容和总路由；公共入口只由主 Agent 修改。

运行时事实：`mainline_controller.gd::_set_mainline_page()` 切换上述两个拆分面板，旧 `MainlineView/MLFrame` 被强制隐藏。因此旧节点上的 `chapter_banner_v1.png` 和旧布局即使仍在场景文件中，也不代表玩家能够看到。当前两个运行时面板主要使用 `MainlineTheme` 生成的 `StyleBoxFlat`，准备页只接入 3 个 48 px 装备图标，尚未真正接入九宫格框、页签和按钮位图。

`mainline_theme.gd::apply_frame()` 目前会清理名为 `ArtSkin` 的节点。Phase 0 必须先取消这种“主题应用时删除美术节点”的策略，改成确定的单一样式所有者，否则继续添加资产仍可能在运行时消失。

### 5.3 战斗 UI 入口

- `godot-client/scenes/main.tscn` 的 `GameView/HUD`：顶部状态、左右翼、单位详情、行动菜单、对话、暂停和结算。
- `godot-client/scripts/ui/battle_theme.gd`：战斗面板、按钮、标题和指挥官行主题。
- `godot-client/scripts/ui/hud_theme.gd`：HUD 节点的主题编排与资源接入。
- `godot-client/scripts/main.gd`：HUD 数据刷新、显示/隐藏和交互路由；公共入口只由主 Agent 修改。

战斗 HUD 已接入顶部状态条、紧凑状态牌和面板九宫格，但仍存在隐藏或弱化：`InfoPanel/OrnateFrame` 当前不可见，左翼装饰透明度较低；`hud_theme.gd` 与 `battle_theme.gd` 会对相同节点重复注入样式，`apply_floating_panel()` 也会清理 `ArtSkin`。Phase 0 需要先确定场景资源与代码主题的唯一所有者，再调整可见性和响应式布局。

## 6. 原创资产生产清单

所有 PNG 必须透明、无文字、无角色、无 Logo；中心内容区留空，中文和数值继续由 Godot 控件渲染。

| 资产组 | 建议规格 | Godot 用法 | 优先级 |
|---|---:|---|---|
| 一级页面边框 | 384 x 384 或 512 x 512 | `NinePatchRect`，四边安全区 48 至 72 px | P0 |
| 二级面板边框 | 256 x 256 | `NinePatchRect`，窄装饰 | P0 |
| 紧凑状态牌 | 240 x 80 | 顶部状态、回合、金币、提示 | P0 |
| 按钮状态组 | 320 x 72，5 态 | 默认、悬停、按下、焦点、禁用 | P0 |
| 页签状态组 | 220 x 64，4 态 | 默认、悬停、当前、禁用 | P0 |
| 列表行状态组 | 640 x 72，4 态 | 默认、悬停、选中、不可用 | P0 |
| 标题铭牌 | 640 x 96 / 320 x 72 | 页面与分节标题 | P1 |
| 角色/物品摘要卡 | 512 x 640 / 512 x 240 | 主从布局的摘要区 | P1 |
| 战斗顶部状态条 | 1200 x 112 | 阵营、指挥官与资源状态 | P1 |
| 战斗侧栏与抽屉 | 384 x 720 | 单位详情和任务信息 | P1 |
| 行动菜单底板 | 320 x 420 | 可拖动/按需出现的行动列表 | P1 |
| 对话框与姓名牌 | 1200 x 300 / 260 x 64 | 剧情对话与输入提示 | P1 |
| 遮罩与轻纹理 | 256 x 256 可平铺 | 弹窗背景、墨蓝织纹、档案纸 | P2 |
| 通用功能图标 | 32 / 48 px | 装备、部队、商店、存档、返回等 | P2 |

生图提示词必须以项目自身需求开头，例如“BattleBlitz 边境军议终端、原创非对称路线刻线、深蓝氧化钢、哑光黄铜、透明背景、无文字、适合 NinePatch”。负面约束必须包含：无角色、无文字、无 Logo、无徽章、无王室纹章、无中心宝石、无卷草花边、无现有游戏 UI、无艺术家风格模仿。

## 7. 多 Agent 分工与波次

最多 4 个并发槽，采用“主 Agent + 3 个子 Agent”分波推进；每波结束后合并和验收，不让多个 Agent 同时编辑 `main.gd`、`main.tscn` 或公共主题入口。

### 波次 0：运行时真源与测试基线

| 角色 | 工作内容 | 输出 |
|---|---|---|
| A 主线审计 | 确认拆分面板、旧节点和 `ArtSkin` 清理路径 | 主线运行时节点真源表 |
| B 战斗审计 | 梳理 `hud_theme.gd` 与 `battle_theme.gd` 的重复注入 | HUD 样式所有权表 |
| C 测试审计 | 区分真实回归、旧契约断言和截图环境问题 | 可执行基线与失败清单 |
| 主 Agent | 冻结公共入口 | 禁止并行编辑文件清单与修复顺序 |

完成条件：运行时不再删除已批准的美术节点；同一组件只有一个主题所有者；现有测试失败被修复或登记为有依据的基线变更。

### 波次 1：规范与基线

| 角色 | 输入 | 输出 |
|---|---|---|
| A 参考分析 | 7 张本地参考图 | 无专有元素的抽象设计规范 |
| B 代码盘点 | 当前 Godot 场景、脚本、资产 | 文件/节点/测试落点表 |
| C 合规审查 | 抽象规范与旧资产 | 禁用清单、来源模板、旧资产风险状态 |
| 主 Agent | A/B/C 输出 | 冻结本计划、截图基线、组件边界 |

### 波次 2：原创资产

| 角色 | 独占范围 | 输出 |
|---|---|---|
| A 基础皮肤 | 页面框、二级面板、轻纹理 | NinePatch 候选与安全区表 |
| B 控件状态 | 按钮、页签、列表、焦点框 | 完整状态组，不含文字 |
| C HUD 专用 | 顶部状态、侧栏、行动菜单、对话框 | 战斗专用候选资产 |
| 主 Agent | 清单与初筛 | 文件命名、尺寸、透明度、来源记录 |

### 波次 3：代码集成

| 角色 | 独占文件范围 | 工作内容 |
|---|---|---|
| A 主线章节 | `mainline_campaign_panel.*` | 存档/章节列表、预览、主操作与空态 |
| B 准备装备 | `mainline_prepare_panel.*` | 英雄摘要、装备清单、数值比较、底部操作区 |
| C 战斗 HUD | 独立 HUD 组件或约定节点段 | 顶部条、侧栏、行动菜单、对话/暂停面板 |
| 主 Agent | `main.gd`、`main.tscn`、公共主题 | 资源接线、冲突处理、路由与兼容层 |

### 波次 4：测试与独立审查

| 角色 | 工作内容 | 通过条件 |
|---|---|---|
| A 功能回归 | Godot smoke、主线与战斗流程 | 0 failed，关键按钮与回调可用 |
| B 视觉矩阵 | 三档分辨率截图、长文本、空态、禁用态 | 无重叠、裁切、越界和焦点丢失 |
| C 原创审查 | 同时比较参考和候选成品 | 无专有元素；相似度阈值通过 |
| 主 Agent | 汇总与提交 | 资产清单完整，可按提交回滚 |

## 8. 资产来源与相似度门禁

新增 `godot-client/assets/ui/asset_manifest.yaml`，每个资产记录：

```yaml
asset_id:
path:
purpose:
authoring_method:
reference_access: false
prompt:
negative_prompt:
tool_model_version:
generated_at:
postprocess:
source_inputs:
sha256:
usage_terms:
creator_agent:
similarity_reviewer:
review_status:
review_notes:
```

独立审查按以下五项各评 0 至 4 分：外轮廓与分区比例、内部装饰节奏、中心与角部造型、配色材质组合、整屏构图。出现角色、Logo、专有徽记或描摹痕迹直接拒收；任一项达到 3 分，或总分超过 5 分，退回重做。感知哈希和 SSIM 只能辅助发现直接复制，不能替代人工审查。

## 9. 测试矩阵与验收标准

### 9.1 自动测试

- `godot-client/tools/smoke_test.tscn`：资源存在、节点存在、主题状态与关键回调。
- `godot-client/tools/battle_ui_review_screenshot.tscn`：无需后端的确定性战斗 HUD 截图。
- `godot-client/tools/mainline_flow_screenshot.tscn`：有后端时覆盖主线进入、加载、返回和重入。
- 必要时新增纯本地主线/装备 mock 截图场景，避免网络状态阻塞视觉验收。

当前基线并非全绿，实施时不得掩盖：

- Godot smoke 当前先出现 3 个“移动后继续行动”失败，随后在 `smoke_test.gd:710` 因 `_set_unit_info_portrait` 参数类型不匹配中止。
- `game/tests/test_godot_client_contract.py` 当前为 25 passed、11 failed；多数失败来自 controller 拆分后的旧静态断言，另有英雄立绘锚点不一致，需要逐项判断应修实现还是更新契约。
- `--headless` 的 dummy renderer 无法稳定获取 viewport 截图；功能 smoke 可用 headless，正式截图应使用 Godot 图形模式或 Xvfb。

建议命令：

```bash
/home/youko/下载/Godot_v4.7-stable_linux.x86_64 \
  --headless --path godot-client res://tools/smoke_test.tscn

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 game/venv/bin/python -m pytest -q \
  game/tests/test_godot_client_contract.py
```

### 9.2 截图矩阵

每档分辨率至少覆盖：主线空存档、已有存档、章节详情、英雄页、装备页、战斗默认态、单位选中、行动菜单、对话、暂停、结算。

| 分辨率 | 重点 |
|---:|---|
| 1280 x 720 | 最小安全字号、按钮高度、三栏收缩、无重叠 |
| 1600 x 900 | 默认布局节奏、边框比例、地图不被过度遮挡 |
| 1920 x 1080 | 留白控制、边缘 HUD 密度、纹理不过度放大 |

### 9.3 完成定义

- 地图、棋子和地形相关目录无改动。
- 参考截图未进入 Git、构建包、PR 附件或生图输入。
- 所有新资产有来源、提示词、哈希和审查状态。
- 生图与代码 Agent 声明未查看商业参考图。
- 按钮具备默认、悬停、按下、禁用、焦点状态；选中态不只依赖颜色。
- 三档分辨率无资源加载错误、控件重叠、文字裁切、点击穿透和焦点丢失。
- 地图始终是战斗主视觉，默认 HUD 不遮挡关键棋盘区域；详情按需展开。
- 功能测试 0 failed，主线存档、准备、装备和开战流程无回归。
- 至少 3 名独立评审对“层级、可读性、一致性、反馈、原创性”五项平均分达到 8.5/10。
- 相似度审查无单项 3 分以上风险，且总分不超过 5。

## 10. 提交策略与回滚

建议按可独立回滚的边界提交：

1. `docs(ui): define clean-room visual upgrade plan`
2. `style(godot-ui): add original ui tokens and asset manifest`
3. `style(godot-ui): add original scalable control assets`
4. `refactor(godot-ui): skin mainline campaign and preparation panels`
5. `refactor(godot-ui): skin battle hud and modal menus`
6. `test(godot-ui): add responsive visual regression coverage`

位图资产、主题接入、结构重排和测试不要混在同一提交。若某组资产未通过原创性审查，只回滚对应资产与主题接线，不影响功能代码和地图分支。

## 11. 审核决策

开始实施前需要确认：

1. 接受“边境军议档案”作为原创方向，不以接近参考游戏为目标。
2. 接受对现有红宝石、对称卷草和四角纹章资产重新审查，必要时替换。
3. 接受默认 HUD 克制、详情按需展开，而不是用装饰边框覆盖整个战场。
4. 接受按四波推进，并在每波结束后先截图与原创性验收再进入下一波。
