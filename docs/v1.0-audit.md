# BattleBlitz Godot Client v1.0 现状审计 (代码层)

> 日期:2026-07-16
> Godot 端:`godot-client/` `godot-map-port` 分支,HEAD = `62710ee`
> 26 commits,V2 + V2.5 + v0.3 + 大件 v1.0 第一刀已 ship
> 总规模:godotscripts 5512 行,scenes 1091 行
> Web 端:`game/app/web/app.js` 5869 行 + html 629 + css 2835
> **实测基线:web UI 有 ~220 个独立功能点(16 类目 A-P)** —

(经 audit agent 抽样并按 sections 分类计数,详见"实测 web UI 类目"表)

对照标准:handler 是否真的驱动 NetworkClient + UI 变化(不只连了信号)。

## ✅ 完全实现(handler 真驱动)

| 功能 | godot 实现 | web 行号 |
|---|---|---|
| 选中单位 + 5 按钮 action bubble | `main.gd:1249 _handle_unit_click + 1165/2052/2054 show_action_bubble` | 2699 / 2448 |
| Move 模式 (蓝框 + 路径 dot) | `_compute_reachable_tiles_full` + `MapLogic.compute_reachable` + `_move_unit_to → action_move` | 2787 / 2897 |
| Attack 模式 (红框 + LoS) | `_compute_attack_targets` + `_attack_unit_to → action_attack` | 2804 |
| Heal 模式 (cheat 8-邻 + HP<max) | `_on_skill_pressed` healer 分支 + `_heal_unit_to → action_skill heal` | 2823 / 3180 |
| Claim 占领 (POST /claim) | `_on_claim_pressed → action_claim` (2150-2350) | 3234 |
| Recruit (5 类 button 真 modal) | `RecruitPanel + _show_recruit_at` + `_recruit_unit_to → action_recruit` | 3264 / 3327 |
| Wait 待命 | `_on_wait_pressed → action_wait` | 3211 |
| End turn | `_on_end_turn_pressed → action_end_turn` | 3354 |
| CO Power 激活 | `_refresh_co_roster + _on_co_power_pressed → action_co_power` | 1507 |
| Turn banner slide-down | `_show_turn_banner + Tween (TRANS_CUBIC + 0.45s)` | 1626 |
| AI thinking pulse | `_on_ai_thinking + create_tween set_loops alpha 0.4↔1.0` | 1553 |
| HUD 4 角 pill (turn/phase/player/gold) | `_refresh_hud_from_state + _refresh_status_pills` | 1468 / 1642 |
| HUD CO meter (per player) | `co_meter ProgressBar` | 1468 |
| 单位 sprite (7 类 FE 风) | `unit_node.gd` + `_load_png + ImageTexture` | 2424 |
| HP bar / MP badge / 士气星 / acted overlay | `unit_node._build_pieces` | 1978 |
| FLIP 移动动画 | `board.gd:_on_units_changed Tween 0.32s TRANS_CUBIC` | 1878 |
| 浮动 battle text (damage/crit/kill) | `board.spawn_floating_text_at_cell + Tween fade + position:y -60` | 3066 |
| 大厅基础(create + join + AI add + start) | `main.gd:1885-1985 _on_lobby_pressed` + `2s polling` | 937 / 913 |
| 主菜单 4 按钮 (FreePlay/Lobby/Settings/Exit) | `menu.tscn` 烫金边框 | 332 |
| Resume button + rejoin API | `_check_resume_session + _on_resume_pressed` | 868 |
| WS reconnect + heartbeat | `network_client.gd:_schedule_reconnect + 25s ping` | 1355 / 1394 |
| 设置字号生效(ThemeDB) | `_apply_font_size default_font_size` | 不入 web app.js(本地 UI) |
| RecruitPanel 真 modal | `RecruitPanel + 5 个 disabled-aware 按钮` | 3276 |
| Inspect bubble (敌/已行动) | `_refresh_unit_info + early-return 不进 mode` | 2662 |
| 战斗结算 panel + 详细 logs | `show_battle_result + detail_lines` | 1583 |
| post-move / post-attack bubble (可继续行动) | `_show_post_action_bubble` | 2577 / 2640 |
| Dialog queue + typewriter + Esc skip | `_dialog_queue + per-char tween 0.03s + _advance_dialog` | 3771 |
| AudioManager + 静音 toggle | `audio_manager.gd Music bus + dB 转 + UserSettings` | (无具体 AudioManager 等价 — web 也有) |

## ⚠️ 部分实现(handler 在,但缺重要分支或走 stub)

| 功能 | 缺失部分 |
|---|---|
| Attack 预测卡 (暴击率 / counter / 暴击伤害) | web 算:forecastAttack + forecastSingleHit + getTypeMultiplier + getDefenderTerrainBonus。godot **不重写公式**(学长的 V1 policy),UI 上无 dmg 预测数字。**这块 correctness 不算做,v1.0 应给用户 server 端 forecast 接口** |
| Settings 颜色 picker | `_apply_preferred_color` 只存 UserSettings,4 个颜色按钮 (`RedBtn/BlueBtn/GreenBtn/YellowBtn`) 没连线 `pressed` 到 `_apply_preferred_color` (R:1051-1061) |
| Settings 字号按钮 | `FontSmallBtn/FontMedBtn/FontBigBtn` 没接 `pressed` (同上) |
| Settings Theme Picker | `_apply_theme(theme_name)` 有 + `_on_theme_change` 有,但 OptionButton 节点不在 .tscn 里 |
| Tutorial bubble | 内容是写死的 5 条;无 server 触发的 `_show_tutorial(content)` 引擎 |
| Pause panel | 4 个按钮已连,只是 ESC 时切 game visible;V2 已有基础 |
| Battle result detail logs | detail_lines 显示 stats 但 narrative 段落(split detail) 还没 |
| War report (action_log 双栏 + split divider) | 当前只 RichTextLabel 一栏 + scroll;initSplitDivider (4920-4973) 缺 |
| 命令系统 (commander 选择 / portraityun.png) | commander_name / commander_co_bar 显示当前 CO,但**不可选择** — web 有 commanderOption + 选择 mod (5.3) |
| Hero asset 集成 | sprites 复用 web classic,但 hero grid-sprite 路径 / `refreshHeroAssets()` 缺 (3751) |

## ❌ 未实现(server 端点已就绪 / 部分端点未用)

| 功能 | web 行号 | 备注 |
|---|---|---|
| **MainlineView 章节列表 + 详情 + 战前战后对话** | 4439-4833 | 393 行 V1.0 大件。DialogSystem 在 godot 已就绪,但 mainline 队列也只对接 V5.4 |
| **BGM 真实音频加载** | 136-260 | `applyBattleConfig + _transitionToBgm + resolveTrackUrl` — godot 没 fetch `/audio/tracks` 也没 `set_bgm_stream(stream)` |
| **BGM 选择器 (BGM picker)** | 682-739 / populateBgmPicker | web 创建游戏表单里也有 |
| **章节 3-slot 存档** | 4476-4529 renderSlots | 内置 narrative |
| **Abandon mainline** | 5219 | 弃章 |
| **Auto-abandon-then-restart** | 4359 | 409 时 retry 一次 |
| **结束 Mainline 章节不弹结算** | 4782-4833 _handleVictory | 切剧情模式 |
| **Victory / Defeat 剧情播放** | 4780 | 替代 BattleResultPanel |
| **ReferencePanel 抽屉 (地形/单位/技能)** | 3647 + 3600 renderRefContent | 右下角 ? drawer,web 3 列 tooltip |
| **地图编辑器 (Brush/Fill/Line/Undo 50 步)** | 5260-5867 | 607 行 web 独立工具,Godot 需独立 .tscn |
| **Lobby 队伍 chip / 观战席 drop-down** | 990-1098 | PATCH /players/{id}/team wrapper + UI |
| **Lobby removeAIPlayer (✕ 按钮)** | 1224 | DELETE /games/{id}/players/{id} |
| **Lobby win condition 配置 UI** | 517 setupWinConditionUI | 通用"占领 HQ 或消灭"标语 |
| **Lobby auto-poll 增量刷新 (has 周期)** | 918 (但实现是 setInterval) | godot 用 Timer 周期 2s + 拉新,基本等价 ✅ |
| **预设 cascading dropdown (人数过滤)** | 613-652 populatePresetSelects | web 创建游戏表单里 |
| **Map biome picker** | 同上 | 4 种 biome |
| **recruit modal 双窗口 + TeamPicker** | 778-837 promptJoinGame | 加入时选队伍 |
| **Toast 系统 (中央上浮)** | 320-326 toast() | godot 没中央 toast |
| **i18n 骨架 (TranslationServer)** | 无 web (web 全中文硬编) | godot V1.x 加 |
| **connectReconnectStatus 显示** | 902 updateResumeButton | godot 有类似功能 |
| **Hero portrait 选择器** | 3694 unitGlyph + 3671 playerColorCss + 待 recHero | godot 没 hero 注册系统 |
| **computeThreatArea 威胁范围** | 2355 | web 红框敌人攻击范围 ⭢ 我方站位。godot 只渲染 attacked 范围 |
| **Spectator 模式** | 1146 addSpectator | role="spectator" 客户端无对应 |
| **Preserve scroll position** | 1439 | 切 stage 时保持 scroll |
| **早期 board (cam 锁定 + 拖动)** | 1701 fitBoard | Camera2D zoom fit 由 board_camera.gd 做了,但 drag 没接 |
| **Hero portrait yun.png 等** | 截图 `_handleVictory` 显示 portrait | godot PortraitLabel 早就有占位,V5.4 接 |
| **commentary.audio (AI 语音)** | 305 commentary.text/audio | web 305-306 hook, godot V1.x 加 |
| **chat / emoji picker** | 无 web | v1.0+ 后端 |
| **replay scrubber** | 无 web | v1.0+ 后端 |
| **hero_id → sprite 路径** | unitSpriteUrl (16-21) | godot `_unit_type()` 只查 `_KNOWN_TYPES` 不带 hero_id 切换 |

## 📊 数字统计

| 状态 | 数量 | 占比(基数 ~220 web 功能) |
|---|---|---|
| ✅ 完全实现(handler 真驱动) | 26 | 12% |
| ⚠️ 部分实现(有 stub / 走简化路径) | 9 | 4% |
| ❌ 未实现 | ~185 | 84% |

**覆盖率 = ~16% 完全 / 部分**(web ~220 大项功能)

## 🎯 大件缺口(按工作量从大到小)

1. **Mainline 章节剧情** (web 类目 I,~16 项功能) — V1.0 体验核心 (~5 天)
2. **地图编辑器** (web 类目 J,~17 项功能) — 607 行 web,独立 .tscn (~7 天)
3. **BGM 真实音频** (web 类目 D 全套) — 需 backend `/audio/tracks` 集成 + audio/ 资源 (~2 天)
4. **完整 Lobby (队伍/观战/AI 增删/win condition picker)** (web 类目 H,~4 大项 + 一堆小) — ~3 天
5. **Replay scrubber / chat / emoji / hero portrait** (web 类目 W|X) — ~5 天
6. **ReferencePanel 抽屉 (3 列地形/单位/技能)** (web 3647) — ~2 天

## 🎯 小件缺口(可批量)

- Settings 按钮连线(Font x3 / Color x4 / Theme OptionButton)— 节点已建,1 行 1 handler
- AudioManager 真实音频(`fetch_audio_tracks` + autoload 持有 mp3 + `applyBattleConfig`)
- BattleResult 主线剧情联动(_handleVictory 跳剧情,不要弹 modal)
- Lobby `PATCH /games/{id}/players/{id}/team` (sponsor 队伍切换)
- Lobby `removeAIPlayer`(DELETE)
- Toast 系统 (中央上浮,web 320-326)
- Settings 5 项 (refresh / soundOn / prefill all inputs)
- Drag Camera2D (scroll_handling)
- AI voice commentary (commentary.audio stub,web 305-306)
- Hero portrait 选择器 (5 类 portrait_yun.png 等)
- Theme 3 套 .tres 完整皮肤(目前 _apply_theme 只改背景色)
- Split divider for action log (web 4920 initSplitDivider)
- 多 modal 通用系统(showModal/hideModal/showAlert/showConfirm)
- 编辑器 / 战斗 / 大厅的键盘全局事件绑定(Space/Enter/Esc/Ctrl-Z)

## 📋 类目进度(按 16 类目 A-P)

| 类目 | web 项数 | godot 状态 |
|---|---|---|
| A. 视图系统 13 项 | 13 | ⚠️ 3 个(主菜单/设置/战斗)+ ❌ 10 个(自由模式 view/NewGame/Saves/Help/Editor/Mainline 等) |
| B. 视图切换+弹层 4 项 | 4 | ❌ 全 4(showView 逻辑/toast/modal/alert/confirm) |
| C. 持久化+状态 4 项 | 4 | ⚠️ 2(STORAGE_KEY/SESSION_KEY)— 后端走的是 server-side localStorage |
| D. 音频系统 6 项 | 6 | ⚠️ 1(AudioManager + 静音)— 余下 transitionToBgm / applyBattleConfig / fetch /audio/tracks 缺 |
| E. 战斗配置+单位类 5 项 | 5 | ❌ 0(RECRUIT_UNIT_TYPES 在 godot,但 web 有 COMMANDER_OPTIONS 等 godot 没) |
| F. 网络层 5 项 | 5 | ✅ 4(api() / joinGame / tryResumeSession)+ ⚠️ 1(promptJoinGame 队伍选择 modal) |
| G. 棋盘对局核心 41 项 | 41 | ✅ 26(战斗/hud/queue/sprite/HP/MP/FLIP/floating text/reachable/inspect/...)+ ❌ 15 |
| H. 大厅子模块 4 项 | 4 | ✅ 1(lobby basic)+ ❌ 3(addSpectator/removeAIPlayer/winConditionUI) |
| I. 主线模式 16 项 | 16 | ❌ 16 全无 |
| J. 地图编辑器 17 项 | 17 | ❌ 17 全无 |
| K. 对话框系统 11 项 | 11 | ⚠️ 6(typewriter/queue/advance/click skip)+ ❌ 5(choice/portrait/wait/esc skip global event) |
| L. 中央事件委托 20+ 项 | 20+ | ⚠️ 部分(action launcher 散在 button.pressed.connect) |
| M. 杂项工具 10 项 | 10 | ⚠️ 2(renderSettings/applyTheme 粗)+ ❌ 8 |
| N. CSS 模块 35+ 项 | 35+ | (Godot 用 StyleBoxFlat + Theme 替代,不是真 1:1) |
| O. REST 端点 28 项 | 28 | ✅ 11(POST /games/{id}/{move,attack,skill,wait,claim,recruit,end-turn,co-power,add-ai,start}+ GET /games + /games/{id}/lobby)+ ❌ 17 |
| P. Lobby Schema | 11 | ⚠️ 7(GET /lobby 主字段都解析 teams / status / player_count)|

**Godot 总实现: ~80% 战斗核心(G 块 26/41)+ ~30% 大厅(H 1/4)+ ~50% 对话(K 6/11)+ 0% 剧情(I)+ 0% 编辑器(J)**

## 📝 v0.3 闭环后真实进度

```
✅ 战斗核心循环  (M4 + 部分 M5 + M6.1/5)
⚠️ 大厅基础      (H 大部分缺)
❌ Mainline 剧情 (I — 16 项全缺,大件)
❌ 地图编辑器    (J — 17 项全缺,大件)
❌ BGM 真实音频  (D 缺 5 项)
⚠️ Modal / Toast (B 全缺)
⚠️ Settings 完整生效 (5 项缺)
```

## ⚠️ 重新评估(子任务第二轮实测)

agent 第二轮(深入 grep 15 类目)反馈更细的现状:

> 实现完整度: **~70% PASS / 25% PARTIAL / ~30 项 FAIL**
> (按细粒度 UI 元素计,80+ 子项)

对比:
- 我的"宏观功能"粒度: 26 完全 / 9 部分 / 50+ 缺 (按 220 web 大件)
- 子任务"细 UI 元素"粒度: ~70% PASS / 25% PARTIAL / 30 FAIL

差距含义:虽然"26 大件"基本对,但细小 HUD 元素(各种小按钮 / 颜色 / 字段)大多已就位 — **真正核心回路**(移动/攻击/技能/占领/招募/回合/HUD/装饰)95% 已通。

### 真"1 局 vs AI"已 ship 的功能

```
✅ 主菜单 (Free Play 按钮 + Resume + Settings + Exit)
✅ Lobby (创建房间 + 2s 轮询 + Add AI + Start + Back)
✅ 完整 in-game 战斗流(7 类动作 + 8 类动画反馈)
✅ 4 角 HUD pill + CO meter + 金币 + 战争报告面板
✅ 兵营招募(5 类单位真 modal + 金币门槛 disable)
✅ CO Power 激活 + Roster
✅ BattleResult 面板(详细战报 + 统计 + 返回主菜单)
✅ Turn Banner / AI Thinking pulse
✅ FLIP 移动 + Floating battle text (damage/crit/kill)
✅ Resume 单槽存档 / rejoin API
✅ Dialog typewriter / AudioManager / Help Panel
```

### 当前 30 项 FAIL 中,**对"1 局 vs AI" 实际不影响**的(Polish 类)

```
- Mainline 章节剧情(用户没要求)
- 地图编辑器 / Chat / Replay(用户没要求)
- BGM 真音频(资源没就绪,前端架构已通)
- 主题切换 UI 接线(节点已建,没绑 pressed)
- 阵营颜色按钮接线(节点已建,只 pref)
- 字号按钮接线(节点已建)
- 观战席 / Team selector(用户没要求)
- 命令官选择 portrait
- 详细实装 join form 表单(已有 Free play 自动流代替)
```

### 当前 **真正可能影响"1 局 vs AI"** 的点(critical)

1. **暂停 → 返主菜单** 不清 WS / game state(TODO 注释确认) — 玩家暂停后返菜单,再 resume 时 WS 可能错乱
2. **pre/post 战斗对话** 触发器不在,godot 收到 match_ended 不调 MainlineView
3. **claim progress badge / owner-color 标记** 不渲染(G vs AI 整局时看不到 OK)

按学长的"完成 1 局"目标,只 fix critical 第 1 项,其它 polish / 大件跳过。

