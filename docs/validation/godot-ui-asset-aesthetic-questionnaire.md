# Godot UI 资产美观度问卷

本问卷用于把“好不好看”转换成可复查的资产级决策。评审时必须同时打开资产原图和
1280×720、1600×900、1920×1080 三档运行截图；只看原图或只看单一分辨率的评分无效。

## 填写信息

- 评审人：________________
- 日期：________________
- 提交：________________
- 显示器缩放：________________
- 三档截图是否齐全：□ 是　□ 否

## 评分方法

每项 1–10 分，允许 0.5 分。总分为六项算术平均值。

| 维度 | 10 分标准 |
| --- | --- |
| 造型与辨识 | 轮廓有记忆点，缩小后仍能识别用途，不依赖文字解释 |
| 材质与配色 | 黑钢、旧金、深海军蓝、档案纸材质统一，明暗关系稳定 |
| 细节完成度 | 边缘干净，无抠图毛边、色键残留、伪文字、水印或生成瑕疵 |
| 拉伸与适配 | 九宫格角部不变形，三档分辨率无糊边、裁切、接缝或纹理变密 |
| 内容承载 | 装饰不抢文字，安全区明确，对中文字号和长文本友好 |
| 系统一致性 | 与相邻按钮、面板、图标和战场像素美术属于同一视觉系统 |

决策阈值：`< 7.0` 立即替换；`7.0–8.4` 进入本轮修正；`8.5–8.9` 可保留但不能支撑
9 分目标；`≥ 9.0` 才可标记为旗舰资产。任何一项低于 8 分，即使平均分较高也不能标记旗舰。

## 逐资产评分表

状态说明：`现役` 表示运行时或主题直接使用；`候选` 表示仓库中有替代稿但尚未接入；
`备用` 表示资源入口保留、当前截图未必出现；`旧版` 表示历史兼容资产。

### 原创主题：基础框架与底纹

| 资产 | 状态 | 造型 | 材质 | 细节 | 适配 | 承载 | 一致 | 总分 | 决策 / 缺陷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `original_v2/base/primary_page_frame_9slice.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/secondary_panel_frame_9slice.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/character_summary_card.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/item_value_summary_card.png` | 备用 |  |  |  |  |  |  |  |  |
| `original_v2/base/ink_navy_weave_tile.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/warm_gray_archive_paper_tile.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/smoke_black_steel_tile.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/base/modal_overlay_tile.png` | 现役 |  |  |  |  |  |  |  |  |

### 原创主题：控件图集

| 资产 | 状态 | 造型 | 材质 | 细节 | 适配 | 承载 | 一致 | 总分 | 决策 / 缺陷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `original_v2/controls/button_states.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/tab_states.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/list_row_states.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/title_nameplates.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/section_divider.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/status_frames.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/bar_components.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/scrollbar_components.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/controls/input_hint_capsules.png` | 备用 |  |  |  |  |  |  |  |  |
| `original_v2/controls/function_icons.png` | 现役 |  |  |  |  |  |  |  |  |

### 原创主题：战斗界面

| 资产 | 状态 | 造型 | 材质 | 细节 | 适配 | 承载 | 一致 | 总分 | 决策 / 缺陷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `original_v2/battle/top_battle_status_bar.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/top_battle_status_bar_refined_v3.png` | 现役/新稿 |  |  |  |  |  |  |  |  |
| `original_v2/battle/battle_sidebar_drawer.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/battle_sidebar_drawer_refined_v3.png` | 现役/新稿 |  |  |  |  |  |  |  |  |
| `original_v2/battle/action_menu_panel.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/dialogue_panel.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/nameplate.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/compact_status_plate.png` | 现役 |  |  |  |  |  |  |  |  |
| `original_v2/battle/chapter_result_title.png` | 现役 |  |  |  |  |  |  |  |  |

### 重制候选与小图标

| 资产 | 状态 | 造型 | 材质 | 细节 | 适配 | 承载 | 一致 | 总分 | 决策 / 缺陷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `rebuild/battle/top_status_rail_clean_1000x96_v2.png` | 候选 |  |  |  |  |  |  |  |  |
| `rebuild/battle/compact_hud_plaque_180x72_v1.png` | 候选 |  |  |  |  |  |  |  |  |
| `rebuild/battle/panel_frame_9slice_384_v1.png` | 候选 |  |  |  |  |  |  |  |  |
| `rebuild/navy_gold_frame_9slice.png` | 候选 |  |  |  |  |  |  |  |  |
| `rebuild/navy_gold_frame_overlay_9slice.png` | 候选 |  |  |  |  |  |  |  |  |
| `rebuild/stat_heart_24.png` | 现役 |  |  |  |  |  |  |  |  |
| `rebuild/stat_sword_24.png` | 现役 |  |  |  |  |  |  |  |  |
| `rebuild/stat_shield_24.png` | 现役 |  |  |  |  |  |  |  |  |
| `rebuild/equipment_sword_48.png` | 现役 |  |  |  |  |  |  |  |  |
| `rebuild/equipment_armor_48.png` | 现役 |  |  |  |  |  |  |  |  |
| `rebuild/equipment_accessory_48.png` | 现役 |  |  |  |  |  |  |  |  |

### 历史兼容资产

| 资产 | 状态 | 造型 | 材质 | 细节 | 适配 | 承载 | 一致 | 总分 | 决策 / 缺陷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `chapter_banner_v1.png` | 旧版/现役 |  |  |  |  |  |  |  |  |
| `mainline_panel_skin_v1.png` | 旧版 |  |  |  |  |  |  |  |  |
| `equipment_icons_v1.png` | 旧版 |  |  |  |  |  |  |  |  |
| `battle_hud_frame_v1.png` | 旧版 |  |  |  |  |  |  |  |  |
| `battle_hud_icon_atlas_v1.png` | 旧版 |  |  |  |  |  |  |  |  |
| `battle_side_panel_v1.png` | 旧版 |  |  |  |  |  |  |  |  |
| `battle_side_panel_translucent_v1.png` | 旧版 |  |  |  |  |  |  |  |  |

## 首轮审计摘要（维护者填写）

| 资产 | 当前分 | 结论 | 可观察问题 | 本轮动作 |
| --- | ---: | --- | --- | --- |
| `top_battle_status_bar.png` | 8.2 | 修正 | 控件再次叠放后切割感重，1280 宽度下顶部碎片化 | 生成结构更完整、留白更清晰的同风格替代稿 |
| `battle_sidebar_drawer.png` | 8.4 | 修正 | 外轮廓优秀，但宽边框和内层面板重复，信息区显得沉重 | 保留轮廓，减轻内框与空区重量 |
| `compact_status_plate.png` | 8.3 | 修正 | 小尺寸下装饰占比偏高，数字安全区不足 | 扩大内容安全区并降低角饰对比 |
| `rebuild/top_status_rail_clean_1000x96_v2.png` | 7.2 | 不接入 | 亮金、宝石和纯色蓝与黑钢档案系统不一致 | 保留为反例候选，不替换现役资产 |
| `rebuild/panel_frame_9slice_384_v1.png` | 6.8 | 淘汰 | 高饱和金蓝和尖角语言偏手游魔法风，黑色空心过硬 | 不接入；后续清理需单独授权 |
| `equipment_*_48.png` | 8.1 | 修正 | 小图标读得懂，但写实描边与像素战场、档案面板连接较弱 | 统一底板与边缘光，不改道具语义 |
| `top_battle_status_bar_refined_v3.png` | 9.2 | 接入 | 连续黑钢外框、深蓝安全区和克制角饰统一了顶部状态轨 | 已替换场景直引与 `SkinAssets` 入口；等待三档终验 |
| `battle_sidebar_drawer_refined_v3.png` | 9.1 | 接入 | 保留阶梯轮廓与封蜡识别点，边框更薄、正文承载面积更大 | 已替换左右战术翼板；等待三档终验 |

## 开放题

1. 第一眼最像“临时占位符”的三个资产是什么？为什么？
2. 哪个资产最抢正文或操作按钮的注意力？请写出出现它的截图名称。
3. 哪个资产在 1280×720 下损失最大？是模糊、裁切、拉伸还是安全区不足？
4. 哪组资产最像来自另一款游戏？应向哪一个现役资产看齐？
5. 如果本轮只能替换一个资产，哪个替换对整屏观感提升最大？
6. 是否发现伪文字、水印、色键残留或 AI 生成瑕疵？请写精确路径和位置。
7. 你愿意把哪些资产标为 `≥9.0` 的旗舰资产？每项必须给一句理由。

## 替换闭环

低分资产只有同时满足以下条件才能从替换队列移除：

- 新文件使用新名称接入，旧文件先保留，方便 A/B 与回退；
- 原图通过透明边缘、色键残留和尺寸检查；
- 33 张运行截图完整生成；
- 相关画面六维平均均 ≥ 9.0，且没有单项低于 8.5；
- Godot 烟测与中文文案扫描零失败；
- 问卷中记录替换前后分数、截图证据和最终资产路径。
