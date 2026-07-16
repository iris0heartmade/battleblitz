# BattleBlitz Web UI ↔ Godot Client 差异 + M3-M7 工作计划

> 日期:2026-07-16
> 对比源:`game/app/web/app.js` (5869 行) + `index.html` + `style.css` (共 9333 行)
> Godot 客户端:`godot-client/` 当前 V2 收官 + WS 接入完毕
> 目的:列出 web UI 已实现但 Godot 客户端还缺的功能,排到 M3-M7 工作计划

---

## 一、对比矩阵总览

| 类别 | Web UI 功能数 | Godot 已实现 | Godot 缺 | 优先级 |
|---|---|---|---|---|
| 主菜单 / 创建 / 加入 | ~10 | 基础 4 按钮 | 创建表单 / 加入列表 / 存档 | 🔴 高 |
| 大厅(lobby) | ~10 | ❌ | 整个 lobby 视图 | 🔴 高 |
| 棋盘渲染 | ~18 | 基础 tile+unit | HP/MP/士气/路径/动画 | 🔴 高 |
| 战斗交互(移动/攻击/技能) | ~16 | 5 按钮气泡(无逻辑) | 全套模式 + 预测卡 | 🔴 高 |
| 回合/阶段指示 + AI 动画 | ~5 | HUD 4 角 pill | turn banner / AI 思考动效 | 🟡 中 |
| CO 指挥官系统 | ~5 | ❌ | 完整 | 🔴 高 |
| 章节剧情(Mainline) | ~10 | ❌ | 章节列表 + 剧情 | 🟠 中 |
| 对话系统 | ~9 | 骨架 | typewriter + choice + portrait | 🟠 中 |
| 战斗结算 | ~5 | 骨架 | mainline 联动 + 详细战报 | 🟡 中 |
| 战报 + AI commentary | ~4 | 浮动面板 | 双栏 + 拖动分隔条 | 🟡 中 |
| 观战者模式 | ~7 | ❌ | 完整 | 🟠 中 |
| 存档 / Resume | ~9 | ❌ | 3 槽 / 重连 | 🔴 高 |
| BGM / SFX / 静音 | ~5 | ❌ | 整套 | 🟢 后 |
| 多语言 i18n | 0(全中文硬编) | 0 | 0(后续) | ⚪ 远 |
| 字号 / 主题实际生效 | 设置有但没接 | 设置有但没接 | 接 theme / font_size | 🟡 中 |
| 地图编辑器 | ~14 | ❌ | 独立工具 | ⚪ 远 |
| 玩家聊天 / 表情 | ~3 | ❌ | 0 | ⚪ 远 |
| 连接诊断(延迟/丢包) | 0(没有) | 0(没有) | 0 | ⚪ 远 |
| 回放 / Replay | 0(没有) | 0(没有) | 0 | ⚪ 远 |
| 参考面板(地形/单位/技能) | ~3 | ❌ | drawer | 🟢 后 |

> **核心结论**:web UI 大约有 **80+ 项独立功能**,Godot 客户端 V2 已实现约 **30%**(基础 UI 框架 + 战斗循环 0 逻辑 + WS 接入),剩下 70% 缺失项分布在 M3-M7。

---

## 二、缺的功能 — 按 M 阶段排序

### M3 — 大厅 + 创建/加入 + 队伍选择 + 观战 + 存档(基础联机闭环)

| # | 功能 | 来源 | 备注 |
|---|---|---|---|
| 3.1 | 主菜单"联机大厅"按钮 enable | `MainlineView` / `app.js:5225` | V2 已经 disabled,改成 enabled |
| 3.2 | **大厅视图** `lobby.tscn` | `renderLobby` 937-1144 | 玩家列表 + 队伍 chip + 观战席 |
| 3.3 | 房间列表 `join_list.tscn`(从主菜单进) | `renderJoinList` 473-512 | 看 waiting rooms + 👀 观战 |
| 3.4 | **创建游戏表单** `create_game.tscn` | `createGame` 524-569 | 房间名 / 人数(2/3/4) / 队伍 / 指挥官 / map preset / seed / BGM |
| 3.5 | Map preset cascading dropdown | `populatePresetSelects` 613-652 | 按玩家人数过滤 |
| 3.6 | BGM picker | `populateBgmPicker` 682-739 | GET /audio/tracks |
| 3.7 | 队伍 picker modal | `promptJoinGame` 778-837 | 加入大厅后选队 |
| 3.8 | 添加 AI(选 kind/personality) | `addAIPlayer` 1207-1222 | POST /games/{id}/add-ai |
| 3.9 | 移除 AI(✕ 按钮) | `removeAIPlayer` 1224-1234 | DELETE /games/{id}/players/{id} |
| 3.10 | 添加观战(从大厅) | `addSpectator` 1146-1205 | POST /games/{id}/join role="spectator" |
| 3.11 | 自降为观战(队下拉) | 1018-1020, 1054-1077 | 自己的行有特殊项 |
| 3.12 | 队友 PATCH(team 切换) | 1005-1098 | PATCH /games/{id}/players/{id}/team |
| 3.13 | 启动游戏按钮 | `start` 1105-1108 | ≥2 玩家才能 start |
| 3.14 | 大厅 auto-polling(2s) | 918 | 进入 lobby 后定时拉 |
| 3.15 | 存档列表(`saves.tscn`) | `renderSavesView` 427-447 | GET /games?user_name=X |
| 3.16 | 存档删除 | 5043-5056 | DELETE /games/{id} |
| 3.17 | Resume 上次游戏 | `tryResumeSession` 868-900 | POST /games/{id}/rejoin |
| 3.18 | 重连 + 失败提示 | `connectWS` 1355-1392 | WS 自动重连 |

### M4 — 战斗交互实装(让 5 按钮气泡真正能玩)+ 视觉精修

| # | 功能 | 来源 | 备注 |
|---|---|---|---|
| 4.1 | **移动模式** (己方单位 → 移动 → 蓝色可达高亮 → 路径 dots → 确认 → POST) | `enterMoveMode` 2787-2802 / `showMoveConfirmBubble` 2499-2525 | 用 `MapLogic.compute_reachable` |
| 4.2 | **攻击模式** (己方单位 → 攻击 → 红色高亮 → 战斗预测卡 → 确认 → POST) | `enterAttackMode` 2804-2821 / `showAttackConfirmBubble` 2527-2575 | 预测含暴击率 / 反伤 / 类型倍率 |
| 4.3 | **治疗模式** (healer → 友军) | `enterHealMode` 2823-2836 | POST /skill skill="heal" |
| 4.4 | **占领** (中立建筑 2 回合) | `doClaim` 3234-3262 | POST /games/{id}/claim |
| 4.5 | **招募 modal** (5 种单位 + 金够/不够灰显) | `showRecruitModal` 3276-3325 | POST /games/{id}/recruit |
| 4.6 | **射程查看** (threat map, 范围红) | `computeThreatArea` 2355-2390 | 点击行动气泡"射程"按钮 |
| 4.7 | **HP bar / MP badge / 士气星** 渲染到 unit | 1978-2024 | TileMapLayer 上加 Label overlay |
| 4.8 | **tile owner 标记** | 1944-1963 | 顶部双色块(team / player) |
| 4.9 | **claim 进度 badge** | 1918-1935 | 占领中的 tile 显示 X/Y |
| 4.10 | **path dots** 中间步 / 终点环 | `updatePathPreview` 2897-2918 | 蓝绿小点 + 橙色终点 |
| 4.11 | **FLIP 移动动画** | `renderBoard` 1878-2091 | capture → invert → play, 320ms ease |
| 4.12 | **棋盘 shake / float battle text** | `showFloatingText` 3066-3084 | damage / crit / heal / kill |
| 4.13 | **Post-move bubble** (移动完可继续攻击/移动/待命) | `showPostMoveBubble` 2577-2638 | can_move_after_action |
| 4.14 | **Post-attack bubble** | `showPostAttackBubble` 2640-2660 | 如果还能移动 |
| 4.15 | **Inspect bubble** (敌方/已行动单位) | `showInspectBubble` 2662-2678 | 完整信息卡 |
| 4.16 | **End-turn button** 实装 | `endTurn` 3354-3375 | POST /games/{id}/end-turn |
| 4.17 | **Turn banner slide-down** (3s 动画) | `showTurnBanner` 1626-1640 | 切玩家时弹 |
| 4.18 | **AI thinking pulse** 动效 | 1553 + CSS | 🤖 思考中 pulse 动画 |

### M5 — CO 指挥官 + Mainline 剧情 + 对话系统 + 战斗结算联动

| # | 功能 | 来源 | 备注 |
|---|---|---|---|
| 5.1 | **CO meter 头部 pill 行** (全玩家) | `renderCOMeters` 1468-1505 | 头像 + 能量条 + 发动按钮 |
| 5.2 | **CO Power 激活** (弹激活动画 + 切 active 状态) | `fireCOPower` 1507-1515 | POST /games/{id}/co-power |
| 5.3 | **指挥官选择** (创建游戏 + 章节) | `renderCommanderSelection` 4531-4604 | 云 / 安娜 + passive + CO Power 文案 |
| 5.4 | **Mainline 章节列表** `mainline_list.tscn` | `MainlineView.renderList` 4439-4467 | GET /mainlines |
| 5.5 | **章节详情 + 指挥官选 + 开始** | `MainlineView.renderDetail` | 进入剧情前 |
| 5.6 | **Pre-battle dialogue 自动播放** | `_enterPlayView` 4677-4692 | GET /mainlines/dialogue |
| 5.7 | **Post-battle dialogue** | `onBattleFinished` 4782-4791 | 战斗后剧情 |
| 5.8 | **Next-battle 自动请求** | `_requestNextBattle` 4835-4862 | POST /mainlines/{id}/next-battle |
| 5.9 | **Victory / Defeat 剧情模式** | `_handleVictory` 4805-4833 | 不弹 native 弹窗,播剧情 |
| 5.10 | **Dialogue 系统完整版** | `Dialog` 3771-4179 | typewriter + choice + narration + portrait + queue |
| 5.11 | **Esc skip dialogue** | 4167-4169 | 全屏跳关 |
| 5.12 | **Mainline 3-slot 存档** | `renderSlots` 4476-4529 | 按 id-order 分配 1/2/3 |
| 5.13 | **Abandon mainline** 按钮 | 5219-5221 | 放弃当前章节 |
| 5.14 | **Auto-abandon-then-restart** (409 自动重试) | `start` 4359-4384 | 409 → 自动 abandon + retry once |
| 5.15 | **战斗结算 mainline 联动** | 1583-1592 | 不弹 native modal,触发 MainlineView |

### M6 — 视听 + 设置实装 + 信息面板精修

| # | 功能 | 来源 | 备注 |
|---|---|---|---|
| 6.1 | **BGM 系统** (AudioStreamPlayer + 切换/渐入渐出) | `AudioManager` 136-260 | GET /audio/tracks + battle_config |
| 6.2 | **SFX** 移动 / 攻击 / 治疗 / 占领 音效 | n/a(没实现) | 自行选 sound assets |
| 6.3 | **静音设置** (实际生效) | `save-settings` 5118-5128 | AudioManager.setEnabled |
| 6.4 | **字号实际生效** (HUD/战斗文字) | n/a | theme override 接到 UserSettings |
| 6.5 | **主题切换** (GBA / 高战 / 极简 多套) | CSS 36-50 | Godot 多套 StyleBox 切换 |
| 6.6 | **多语言骨架** (i18n) | n/a | 用 TranslationServer + POT 文件 |
| 6.7 | **参考面板(地形/单位/技能) drawer** | `toggleRefPanel` 3647-3651 + render | 右侧弹出 |
| 6.8 | **可拖动分割条** (战报 / commentary) | `initSplitDivider` 4920-4973 | VBoxContainer / HBoxContainer + 鼠标事件 |
| 6.9 | **AI commentary 双栏 + 心情 emoji** | `renderActionLog` 3529-3557 | [mood/text] 前缀解析 |
| 6.10 | **Toast 提示** (中央上浮,多行) | `toast` 320-326 | 各种操作反馈 |
| 6.11 | **战报 compact 格式** (🗡/↩/💀击杀) | `compactLogDescription` 3438-3527 | 解析后端 desc 字符串 |
| 6.12 | **手动刷新按钮** 🔄 | dispatcher 5111-5114 | 立即拉 /state |
| 6.13 | **Help 静态指南** | `index.html` 182-230 | game rules / 战斗公式 |
| 6.14 | **Resume button** (主菜单,SessionStorage) | `updateResumeButton` 902-911 | 接 M3.17 |
| 6.15 | **连接状态指示** (🟢 connected / 🟡 reconnecting) | n/a | 加在 HUD TopLeft |

### M7 — 高级 / 工具(可选,工作量最大)

| # | 功能 | 来源 | 备注 |
|---|---|---|---|
| 7.1 | **地图编辑器** (完整工具) | 5260-5867 | 独立 .tscn,Brush / Fill / Line / Undo(50 步)/ Save / Load |
| 7.2 | **玩家聊天 + emoji picker** | n/a | WebSocket chat 通道 |
| 7.3 | **连接诊断** (延迟 / 丢包率 / pong 时间) | n/a | HUD 加统计 |
| 7.4 | **回放 / Replay scrubber** | n/a | action log + timeline 拖动 |
| 7.5 | **导出 save** | n/a | GET /games/{id}/export |
| 7.6 | **多主题完整切换** | n/a | theme system + 渐变过渡 |
| 7.7 | **Hero asset 完整集成** | `refreshHeroAssets` 3751-3769 | GET /heroes + 立绘 PNG |

---

## 三、工作时间估算(粗略)

| 阶段 | 工作量 | 包含项 |
|---|---|---|
| M3 — 基础联机闭环 | **大**(3-5 天) | 17 项 lobby / 创建 / 加入 / 队伍 / 观战 / 存档 |
| M4 — 战斗实装 | **大**(5-7 天) | 18 项移动 / 攻击 / 技能 / 战斗反馈 + 棋盘装饰 |
| M5 — CO + Mainline + 对话 | **中**(4-6 天) | 15 项 CO / 章节 / 对话 / 结算 |
| M6 — 视听精修 | **中**(3-4 天) | 15 项 BGM / SFX / 设置生效 / 多语言 / 参考面板 |
| M7 — 高级工具 | **超大**(每项 2-5 天) | 7 项编辑器 / 聊天 / 诊断 / 回放 / 导出 |

**总计剩余**:约 **16-23 天** 工作量。

---

## 四、建议路线

### 优先级路线

**如果你想"能联机对战"**:
```
M3 (大厅) → M4 (战斗) → M5 (CO + Mainline)
```

**如果你想"先有剧情体验"**:
```
M5.4-M5.10 (Mainline + Dialogue) → M3 (大厅) → M4 (战斗)
```

**如果你想"视听大升级"**:
```
M6 (BGM/SFX/i18n/设置生效) → M4 (战斗) → M3 (大厅)
```

### 推荐路线:战斗先于大厅

> 个人建议:**M4 战斗实装先做,M3 大厅后做**。
>
> 理由:
> 1. M4 是 Godot 客户端核心价值(战棋就是玩战斗),没战斗 = 只有空大厅
> 2. M4 能直接复用现有 NetworkClient + GameState + MapLogic,工作量小但价值高
> 3. M3 主要是 UI 流程(创建/加入/队伍),技术难度不高,放在后面收尾
> 4. M4 完成后,Godot 客户端已经可以"单机 vs AI 玩一局",具备演示能力

### 最小可用产品(MVP)定义

完成 M3 + M4 的核心(共 ~10 项)+ 几项 M5 必修 = 可发布 v0.3:

- 创建游戏表单(简化版:只要 name + map_preset)
- 大厅基本视图(玩家列表 + 启动按钮)
- 移动/攻击/待命实装
- HP bar / 路径预览 / 攻击预测卡
- 战斗结算面板实装
- 存档 / Resume

---

## 五、立即可执行的"M4 第一刀"

不需要等 M3 完整,可以直接开始 M4 的部分工作:

```
最小可执行(2-3 天):
- 4.7 HP bar / MP badge / 士气星 — 加到 Board 的 UnitLayer
- 4.10 path dots — HighlightLayer 加路径预览
- 4.16 End-turn 实装 — 已写好的 end_turn button 接 POST /end-turn
- 4.17 Turn banner slide-down — 已写的 turn_banner 接 animate

中等(3-5 天):
- 4.1 移动模式(蓝色高亮 + 路径 + 确认)
- 4.2 攻击模式(红色高亮 + 战斗预测卡 + 确认)
- 4.5 招募 modal

需要 M3 配合:
- M3.2 大厅视图(创建/加入后才能开始游戏)
- M3.17 Resume 上次游戏
```

---

## 六、当前可立即使用的功能 ✅

虽然缺 70% 功能,但 Godot 客户端**目前已经能**:

- ✅ 起后端 + 起客户端 + 走通"创建 → 加入 → 加 AI → 开始"
- ✅ 真实 WS 收到 state.snapshot + 持续推 event.delta
- ✅ 棋盘正确渲染 15×15 地图
- ✅ HUD 4 角 pill 实时显示回合 / 阶段 / 玩家 / 金
- ✅ InfoPanel 显示当前指挥官 + 选中单位 + 玩家列表
- ✅ 行动气泡能打开,5 按钮能点(待命已实装)
- ✅ 战报浮动面板 toggle
- ✅ 设置 / 暂停 / ESC 监听
- ✅ 教程气泡 + 对话框 + 战斗结算(骨架)

**最低可用度评估**:⭐⭐☆☆☆ — 视觉 60% / 交互 20%

要走通"完整一局游戏"还需要 M4 战斗实装。

---

## 七、Action:选路线 + 开工

等你拍板走哪条路线,我接下来按优先级开干。建议:
- 路线 A(战斗优先):进 M4,从 4.7 / 4.10 / 4.16 / 4.17 入手(无依赖,2-3 天)
- 路线 B(大厅优先):进 M3,从 3.2 / 3.4 / 3.15 入手
- 路线 C(Mainline 优先):进 M5,从 5.4-5.10 入手

你拍板喵~ 🛡⚔

---

# Phase 2 — v0.3 + v1.0 端到端可玩路线图

> 日期:2026-07-16
> 起点:godot-client 已经完成 UI V2(7 轮)+ WS 接入 + M4 第 1 刀
> (16/17/7/10/18 + M4.1 移动 + M4.tiny 单位 sprite)。3 个 commit:
> `ccb3455` (M4 4 项) / `a05cf95` (M4.1 移动) / `3c8120b` (单位 sprite)。
> 完成度:⭐⭐⭐☆☆ — 视觉 70% / 端到端可玩 25%
> 优先维度:**端到端"完整 1 局 vs AI"**
> 目标跨度:**v0.3 ≈ 25 天 → v1.0 ≈ 60+ 天**

## 0. 已完成(对照 Phase 1 减去已 ship)

| 原 # | 工作 | Commit | 备注 |
|---|---|---|---|
| M4.7 | HP bar / MP badge / 士气星 | `ccb3455` | unit_node.gd 重写 |
| M4.10 | path dots / reachable 高亮 | `ccb3455` | MapLogic.compute_reachable + Highlights.MOVE |
| M4.16 | End-turn button enable/disable | `ccb3455` | M2.5 之前已接 |
| M4.17 | Turn banner slide-down | `ccb3455` | Panel 烫金边 + 玩家色 emoji |
| M4.18 | AI thinking pulse 动效 | `ccb3455` | alpha 0.4↔1.0 循环 Tween |
| M4.1  | 移动模式 (POST /move 跑通) | `a05cf95` | UnitOut schema player_id 字段修正 |
| M4.tiny| 单位 sprite 复用 web classic | `3c8120b` | 7 类 PNG + ImageTexture |

加上 V2 收官的 ~10 个 commit,Phase 1 累计已 ship 13 个 commits。

## 1. 当前状态总结(对比 web UI 实际行号)

| 域 | web app.js 行号 | godot 实现度 | 备注 |
|---|---|---|---|
| 主菜单 | 332-407 | ✅ 90% | 已支持 4 按钮,只是多入口 disabled |
| 创建/加入表单 | 522-739 | ❌ 0% | NetworkClient.create_game/join_game 已接,UI 表单缺 |
| 大厅视图 | 937-1245 | ❌ 0% | 整个大厅场景未建 |
| 房间列表 | 473-512 | ❌ 0% | 从主菜单进 |
| 队伍+观战 | 1005-1115 | ❌ 0% | PATCH /players/{id}/team 封装已具备 |
| 存档/Resume | 427-447 / 868-911 | ❌ 0% | GET /games?user_name + DELETE /games/{id} |
| 棋盘渲染 | 1878-2091 | ⚠️ 30% | 静态 OK,HP/MP/路径做了,FLIP 动画缺 |
| 移动/攻击模式 | 2787-2836 | ✅ 移动 100% / ❌ 攻击 0% | 进入+reachable+POST 已通;攻击模式缺 |
| 治疗/占领/招募 | 3234-3325 | ❌ 0% | NetworkClient.action_skill/claim/recruit 已有 |
| End-turn / AI / turn banner | 1338-1640 | ⚠️ 部分 | banner slide 已做;AI thinking 在动;turn skip 缺 |
| CO meter / CO Power | 1468-1515 | ⚠️ 仅显示 | CO meter 在顶部 pill;FireCOPower 未接 |
| 主线章节 | 4439-4833 | ❌ 0% | 整段未做 |
| 对话系统 | 3771-4179 | ⚠️ 骨架 | DialogPanel 存在,typewriter/queue/choice 未接 |
| 战斗结算 | 1583-1592 / 4780-4833 | ⚠️ 骨架 | BattleResultPanel 存在,mainline 联动缺 |
| 战报 + commentary | 4920-4973 | ⚠️ 浮动面板 | ActionLog 已有;双栏+拖动分隔条 缺 |
| 观战者 | 1146-1205 | ❌ 0% | role="spectator" 接到 join_game 但 UI 未区分 |
| BGM/SFX | 136-260 (AudioManager) | ❌ 0% | 整体缺 |
| 字号/主题实际生效 | 5118-5128 | ⚠️ stub | 设置面板存在,接 backend 缺 |
| 地图编辑器 | 5260-5867 | ❌ 0% | 607 行 web 代码,工具要做 |
| 玩家聊天/表情 | n/a | ❌ 0% | websocket chat 通道未建 |
| 连接诊断 | n/a | ❌ 0% | 自做 ping/pong HUD |
| 回放/Replay | n/a | ❌ 0% | 需 server-side 或者 cache 完整 event log |
| 参考面板 | 3647-3651 | ❌ 0% | drawer 抽屉未做 |

**总判断**:还差的功能里有 **20+ 项需要新建场景/页面**(大厅、创建游戏、加入、存档、章节列表、章节详情、参考面板 drawer、地图编辑器、聊天窗口),**30+ 项需要把已有的 NetworkClient 函数接到 UI handler**(attack/heal/claim/recruit/CO Power/team patch/etc),**15+ 项需要 BGM/SFX/特效**(AudioStreamPlayer + sprite anim + flip anim)。

## 2. 路线图 — **端到端可玩优先**(从"1 局游戏"反推)

我的策略:"完成 1 局 vs AI"是 v0.3 的里程碑 — 所有"无依赖可串起来的"打包发,**把大厅/CO/Mainline 全部推后到 v1.0**。

### v0.3 — 端到端可玩 (≈ 25 天)

| # | 包 | 内容 | 估时 | 依赖 |
|---|---|---|---|---|
| **3.1** | **战斗动作完成** | M4.2 攻击模式(攻击范围 + 战斗预测卡 + POST /attack)、M4.3 治疗、M4.4 占领、M4.5 招募 | 5 天 | NetworkClient 全套方法已有,只接 |
| **3.2** | **战斗反馈动效** | FLIP 移动动画(4.11)、浮动 battle text(4.12)、棋盘 shake、Post-move / Post-attack bubble(4.13/14)、AI thinking pulse 已在,view feedback 完善 | 4 天 | 依赖 3.1 |
| **3.3** | **Inspector + 完整 1 局** | 4.15 inspect bubble、4.16/17/18 已做 + 完整 1 局可玩 vs AI | 3 天 | 依赖 3.2 |
| **3.4** | **基础大厅** | 3.1 联机大厅 enable、3.4 创建游戏表单(name+map_preset)、3.13 启动按钮、3.18 自动重连 | 5 天 | 弱依赖 3.1 |
| **3.5** | **战斗结算完整闭环** | match_ended 检测 + BattleResultPanel + 详细战报 + 重新开局按钮 | 3 天 | 依赖 3.3 |
| **3.6** | **基础设置生效** | 字号 / 静音 / 玩家名 接到 GameState | 2 天 | 弱依赖 |
| **3.7** | **存档 / Resume (单槽)** | 3.15 / 3.17 + GET /games?user_name 简单实现 | 3 天 | 依赖 3.4 |
| **3.8** | **路线集成验证** | "主菜单 → 自由对局 → vs AI 一局战 + 结束后存档" 端到端人工测试 + 截图 | 1 天 | 依赖 3.7 |

**v0.3 演示场景**:用户点主菜单"自由对局" → 红色 + AI 蓝色 vs 战斗 15 回合 → 一方 HP/rout 触发 → 弹结算 → "再来一次/回主菜单"。

### v1.0 — 大厅/CO/Mainline + 视听精修 (≈ 35 天)

| # | 包 | 内容 | 估时 | 依赖 |
|---|---|---|---|---|
| **5.1** | CO meter 完整 + CO Power 激活 | 5.1/5.2 + 5.3 指挥官选择 | 5 天 | 弱依赖 |
| **5.2** | 大厅功能完整 | 3.2/3.3/3.5-3.11/3.14 (玩家列表 + 队伍 chip + 观战席 + auto-poll + 移除 AI) | 4 天 | 依赖 3.4 |
| **5.3** | Mainline 章节 | 5.4/5.5/5.6/5.7/5.8/5.9 (列表+详情+战前对话+战结算剧情) | 6 天 | 依赖 v0.3 |
| **5.4** | 对话系统完整 | 5.10/5.11 (typewriter + choice + portrait + Esc skip) | 4 天 | 依赖 5.3 |
| **5.5** | BGM + SFX | 6.1/6.2 + 6.3 静音生效 | 3 天 | 独立 |
| **5.6** | 视觉精修 | 6.5 多主题 + 6.8 可拖分割条 + 6.9 commentary 双栏 + 6.10 Toast | 5 天 | 弱依赖 5.5 |
| **5.7** | i18n 骨架 | 6.6 TranslationServer + POT 文件 + 抽取 strings | 3 天 | 独立 |
| **5.8** | 参考面板 + Help | 6.7/6.13 参考面板 drawer + Help 静态指南 | 2 天 | 独立 |
| **5.9** | 路线集成 | "主菜单 → 创建 → 大厅 → 加 AI → 启动 → 战斗 → 结算" 演示 | 3 天 | 依赖 5.6 |

### v1.0+ — 高级工具(可选)

| # | 包 | 内容 | 估时 | 备注 |
|---|---|---|---|---|
| 7.1 | 地图编辑器 | 完整 .tscn (Brush/Fill/Line/Undo 50 步/Save/Load) | 5 天 | 独立,但需 EditorMode 区分 |
| 7.2 | 聊天 | WS chat + emoji picker | 3 天 | 独立 |
| 7.3 | 连接诊断 | HUD 延迟/丢包统计 | 2 天 | 依赖 NetworkClient |
| 7.4 | Replay | action log cache + 拖动 scrubber | 5 天 | 大件 |
| 7.5 | 多人对战 | seed 同步 + 公平性 hash | 2 天 | 后端依赖 |
| 7.6 | Hero asset | heroes/<id>.png 集成 + portrait 选择器 | 2 天 | 数据驱动 |
| 7.7 | 导出 save | GET /games/{id}/export + .zip 下载 | 1 天 | 简单 |

**总计 v1.0+**:约 15-20 天附加。

## 3. 端到端优先的反向逻辑(为什么这样排)

| 决策 | 反向选项 | 取舍 |
|---|---|---|
| 把 攻击/治疗/占领/招募 提前 | 全部 M3 大厅先 | 战斗函数已具备 wrapper,只需接 handler;大厅是 UI 工程但不带"实际玩"。学长的"端到端可玩"明确指这 |
| FLIP animation / 浮动 text 优先 | BGM/SFX 优先 | 视觉特效先做能直接提升 demo 体验;音频等 BGM 资源还没准备 |
| CO / Mainline 放 v1.0 | 提前 | CO 复杂(state model + UI);Mainline 章节需要对话系统先做 |
| 大厅功能分两批 | 整批做 | v0.3 先做基础大厅(创建+加入+启动)v1.0 做完整(队伍/观战/AI) |
| 主题/字号 留到 v1.0 | 先做 | v0.3 接字号够了,主题等 i18n 一起搞 |
| 地图编辑器排最后 | 提前 | 大件(607 行 web 代码),只在 v1.0+;前面工作不阻塞 |

## 4. Phase 2 立即可执行(5 步最近)

```
接下来(未来 1-2 周):
D1: M4.2 攻击模式(可达成 MVP 核心循环)
D2-3: M4.3 治疗 + M4.4 占领 + M4.5 招募(批量接 action_* wrapper)
D4-5: 4.11 FLIP 移动动画 + 4.12 浮动 battle text
D6-7: 4.13/14 Post-move / Post-attack bubble
D8-9: 完整 1 局 vs AI 实战 + 截图
```

每个 D 单元独立 commit + screenshot,不打包。

## 5. 风险与对策

| 风险 | 应对 |
|---|---|
| PathFinder 计算慢(纯 BFS 25×25 还行,如果棋盘更大) | 抽离到 worker thread (Task API) |
| WS 断线后 GameState 损坏 | 已有 GameState._on_state_snapshot 全量刷新,可断线后强制 pull /state |
| BGM/SFX 资源没选 | 可先用 procedural AudioStreamWAV 临时占位 |
| 网络抖动影响移动动画 | 用 server-driven 帧时间,client 不预测 |
| 14 个不同作战动作(bubble 选项)在 Godot 排版 | 用 HBoxContainer + WrapContainer 自适应 |

## 6. 验收标准(每阶段有 demo)

- **v0.3 终**:📹 录一段 5 分钟视频(从主菜单到 1 局 vs AI 完成),展示 战斗实装 + 基础大厅 + 结算。
- **v1.0 终**:📹 完整演示(多人 + Mainline + CO Power + 战斗反馈 + BGM + 设置生效)。

## 7. Action — 等学长拍下一刀

继续按 4. 顺序走 D1(攻击模式),还是先做别的 3.4 大厅基础?

你拍板喵~(=^・ω・^=) 🛡⚔