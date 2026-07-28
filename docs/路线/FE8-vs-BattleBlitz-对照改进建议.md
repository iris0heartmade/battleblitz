# FE8 反编译项目 vs BattleBlitz 对照 · 可改进点

> **生成日期**:2026-07-22  
> **数据源**:
> - `docs/三方对比与接口覆盖分析报告.md`(2026-07-21 snapshot)
> - `docs/架构/Godot客户端功能调查报告.md`
> - `docs/架构/Godot按钮-后端接口对照表.md`
> - `docs/参考/Godot客户端后端接口.md`
> - `docs/路线/fireemblem8u-借鉴报告.md`(v2,2026-07-13)
>
> **对比基准**:FE8 8 系统(fireemblem8u decomp) + FreeWars + Advance-Wars-v2

---

## 0. TL;DR(30 秒读完)

1. BattleBlitz **后端架构已经成熟**(13 router / 73 endpoint / 服务端权威),不缺"接口",**缺 FE8 类的纵向策略深度**(胜利条件 / 武器三角 / 脚本化 AI / 章节 multiplier)。
2. **客户端隐藏的"可改进金矿"**:Godot 端 14 个死按钮 + NetworkClient 7 个已实现未触发的 typed method + WS `commentary.*` 接到 UI 即可白送功能 = **全部能在不写新后端的前提下做出 1-2 周的可见进度**。
3. **真正需要后端扩的事**:多胜利条件(只有 rout+seize)、武器三角 / 追击(战斗公式扩展)、脚本化 AI。文档里 fireemblem8u 借鉴报告已经标好 P0/P1/P2。

---

## 1. FE8 8 大子系统 × BattleBlitz 现状

| FE8 子系统 | BattleBlitz 现状 | 评级 | 差距描述 |
|---|---|---|---|
| 🗺️ **地图 / 2 层 tile** | TileMapLayer 多层 + 字符→terrain 查表 | ⭐⭐⭐ | 已借鉴 BFS / sentinel,基本够用。2 层 tile 抽象不必搬 |
| ⚔️ **战斗 8 公式 + 武器三角 + 1RN/2RN** | 单公式 `attack-defense`,无三角,统一 RNG | ⭐⭐ | **明显落后**:没追击阈值 4、没 2RN、没 brave;完全为 5 兵种简化 |
| 🧑‍⚔️ **三层人物(Hero 限定)** | Hero 子集 3-8 个 | ⭐⭐ | 设计上走"佣兵为主",三段模型非必须 |
| 🤖 **AI(28 op 脚本 VM + 22+19 人格)** | 5 档难度 + 3-4 种 personality 硬编码 | ⭐⭐ | **最大可改进点**:AI 用 if-else 山,不做新内容就要重写 |
| 🛡️ **装备(22 位属性 / 武器熟练度)** | 5 类兵,无武器 / 无熟练度 | ⭐ | MVP 不必要;但 mainline "Hero 装备"已开通了入口 |
| 📜 **事件(90+ op / 17 触发器 / 5 胜利条件)** | 5 种 dialogue 类型,胜利仅 rout+seize | ⭐⭐⭐ | **多胜利条件是文档明确的 P0**;事件字节码太重不必搬 |
| 🌫️ **雾战** | 无 | ⭐ | 可 P2 引入(rot.js shadow casting) |
| 🚶 **移动(BFS+剩余 MP)** | MapLogic BFS+剩余 MP,已搬 | ⭐⭐⭐ | 已借鉴,警戒范围未触发(THREAT highlight mode 死码) |

## 2. FreeWars + AW 双线借鉴(双轨制核心)

| 模式 | 来源 | BattleBlitz 现状 | ROI |
|---|---|---|---|
| **章节难度 multiplier**(6 旋钮 + targetTurnsCount) | FreeWars | 无独立字段,难度写死 unit 数据 | 🔥🔥🔥 |
| **100 点技能点分配** | FreeWars | Mercenary 配置已通(allocate),点数 UI 未做 | 🔥🔥🔥 |
| **4 个 CO modifier** | AW-v2 | commander.py 有,但只 1-2 个 modifier 生效 | 🔥🔥 |
| **Veteran 击杀升级**(Mercenary 可选) | FreeWars | 无 | 💎 |
| **中立佣兵招募 + 数值生成** | 自研(无现成参考) | mainline 已有 `mercenary/allocate`,招募 UI/数值衰减未做 | 💎 |

---

## 3. 客户端隐藏可改进金矿(对接即可)

这一类是 **不写新后端** 就能出成果的项,直接看 `docs/架构/Godot按钮-后端接口对照表.md`:

| 改进项 | 当前状态 | 修复 = 什么 | 预计工作量 |
|---|---|---|---|
| **Manual Save 按钮缺失**(P0) | `save_manual` API 写好,UI 没接 | main.tscn 加 save_new_btn + Saves tab 写盘按钮 | 30 min |
| **`/mainlines/{id}/prepare/complete` 不触发** | `complete_mainline_prepare` 实现完 | 在准备页加"✅ 准备好了"按钮 | 15 min |
| **`MainlineNextBtn` 不亮** | 节点埋好 `visible=false`,无调用方传 `mainline_next=true` | 在 BattleResultPanel 加触发线 | 20 min |
| **`get_lobby` / `delete_game` / `delete_editor_map` 包好未触** | NetworkClient 包好,UI 不调 | 接对应 UI 节点 | 各 30 min |
| **`capture_suspend` 主动挂起 UI 没接** | 节点 / handler 都缺 | 加"PausePanel 中断退出"按钮 | 30 min |
| **`/games/{id}` DELETE 没接** | WebUI 调,Godot 不调 | 房间列表加删除按钮 | 15 min |
| **Commentary WS no-op** | `commentary.text/audio` 类型接好,UI no-op | 接 WarReportPanel 旁挂"AI 评论"标签 | 1 h |
| **Help/Reference Panel** | `show_help()` 实现完,无触发按钮 | main.tscn 加 ❓ 按钮 | 20 min |
| **静音 toggle 死** | `_on_toggle_mute_pressed` 函数存在,无 connect | SettingsPanel 加按钮 | 10 min |
| **`JoinByCodeButton` / 主菜单 `SettingsButton` disabled** | 节点存在 | 删掉 or 接 handler | 10 min |
| **Bug:`gs.set("is_connected")` 字段名错** | 应是 `ws_connected` | 改 2 行 | 1 min |
| **`EditorSurfaceOption` 重复声明**(场景 bug) | main.tscn 行 323 + 374 两次 | 删前者 | 5 min |
| **WebUI `reach_tile/defend_turns` 历史表单保留** | 后端只支持 rout+seize,UI 还留 | 删 / 标弃用 / 加 P0 多胜利条件后端实现 | 30 min |

**合计 ~半天工作量** 可以清掉 13 条 P0/P1 死代码。

---

## 4. 后端真正需要扩的 FE8 设计点(按 ROI)

### 🔥 P0 — 一周内可做,影响主线可玩性

| 设计点 | FE8 / FreeWars 出处 | 后端要做的 | 客户端要做的 |
|---|---|---|---|
| **多胜利条件**(5 种 OR) | FE8 `GOAL_TYPE_*` | `/mainline` schema 加 `victory_conditions: List[VCType]` + 逐章配 | Web 创房表单 / Godot 创房表单 |
| **追击阈值 4** | FE8 `\|spdA - spdB\| >= 4` | `damage` 公式加 `followup` 判定 | WarReportPanel 显示追击数 |
| **1RN / 2RN RNG 区分** | FE8 `Roll2RN` | rng helper 加 2RN 模式 | 无 |
| **章节难度 multiplier**(6 旋钮) | FreeWars | 每章 JSON 加 `advanced_settings:{atk/def/income/move/vision/recruitCost}` | Godot 章卡预览展示 |
| **100 点技能点分配(准备页 UI)** | FreeWars | mainline prepare 增加 `commander_points: dict` | 准备页加 CommanderPoints 表 |

### ⭐ P1 — 两周内可做,深化 AI/UX

| 设计点 | 出处 | 后端 / 客户端 |
|---|---|---|
| **脚本化 AI**(28 op / 数据驱动) | FE8 `cp_script.c` | AI helper 改 JSON 驱动 + 心情切换 |
| **危险图 / 警戒范围多源叠加** | FE8 `gBmMapOther` | `/state` 返回 danger_map[y][x] | Godot THREAT highlight 已埋模式 |
| **CO Modifier 4 模式** | AW-v2 | commander schema 加 4 modifier | 准备页 UI 滑块 |
| **8 邻居移动 / 斜向**(可选) | FE8 | MapLogic BFS 加对角 | highlights 重画路径 |

### 💎 P2 — 一个月内可做,长期可玩性

| 设计点 | 出处 |
|---|---|
| **雾战三态** | FE8(Fog VM,rot.js shadow casting) |
| **Hero 转职系统**(FE8 promotion) | 现 progression/units/{id}/promote 接口已有,UI 缺 |
| **Veteran 击杀升级(Mercenary 可选)** | FreeWars Promotable |
| **Boss 多阶段 AI 切换** | FE8 `AI_SET_AI` |
| **完整 ItemData 系统**(M4 之后) | FE8 22 位属性 + 8 武器熟练度 |

---

## 5. 接口层面 — 14 个仅测试用的端点怎么"激活"

来自三方报告 §8.1,这些接口后端都做了但前端不用:

| 端点族 | 建议激活方向 |
|---|---|
| `progression/profiles/{id}/units` | 准备页 "我的单位" Tab 显式按 profile 列 / Hero detail |
| `progression/units/{id}/xp` | 主线 `advance` 之后增量加经验(MVP) |
| `progression/units/{id}/promote` | 主线准备页 Hero L10/L20 转职按钮(P2) |
| `/profile/{user_name}/mainline/{start,advance,abandon}` | 标记 deprecated,只在 409 fallback 用 |
| `WS /debug/ws/games/{id}` | 留着,开发期好用;生产禁用 |

---

## 6. 一句话总结 + 三步走

> **BattleBlitz 当前最该做的是 "先消化已实现的(半天清 13 条死代码),再补 FE8 模式里最有商业价值的两块(多胜利条件 + 章节 multiplier),最后才是 AI 脚本化和雾战"**。

### 三步走

1. **第 1 周(纯客户端清理)**:接通 manual save / prepare complete / MainlineNextBtn / commentary UI / Help 按钮 / 静音 / 修复 network_client.gd 字段名 bug — 直接吃 13 条 P0/P1。
2. **第 2-3 周(后端扩 FE8 P0)**:
   - 加多胜利条件(seize / defeat_all / defeat_boss / defense / special)→ 创房 schema / 章配置
   - 加追击阈值 + 1RN / 2RN → 战斗公式扩展
   - 章节 multiplier JSON → FreeWars 6 旋钮
3. **第 4-6 周(双轨制定型)**:
   - 100 点技能点分配 UI 端到端
   - 脚本化 AI 替换 if-else 山
   - 危险图 + THREAT highlight 模式激活(Godot 已埋 mode)

---

## 附录:对应锚点速查

| 主题 | 锚点 |
|---|---|
| FE8 借鉴 P0 列表 | `docs/路线/fireemblem8u-借鉴报告.md:1138-1143` |
| Godot 死按钮 14 个 | `docs/架构/Godot按钮-后端接口对照表.md:62-77` |
| 三方未调 endpoint 14 个 | `docs/三方对比与接口覆盖分析报告.md:198-222` |
| WebUI 独有功能 | `docs/三方对比与接口覆盖分析报告.md:268-284` |
| Godot 独有功能 | `docs/三方对比与接口覆盖分析报告.md:286-304` |
| FE8 战斗公式 | `docs/路线/fireemblem8u-借鉴报告.md:144-180` |
| FE8 AI 系统 | `docs/路线/fireemblem8u-借鉴报告.md:309-380` |
| FreeWars 章节 multiplier | `docs/路线/fireemblem8u-借鉴报告.md:755-870` |
| FreeWars 100 点技能 | `docs/路线/fireemblem8u-借鉴报告.md:875-940` |

---

> 报告完。
