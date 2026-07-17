# Godot Client Parity Audit (2026-07-17)

> Date: 2026-07-17
> Branch: `godot-map-port`
> Scope: compare the current Godot client against the original Web UI (`game/app/web/app.js` + `index.html`) and identify remaining gaps.
> Supersedes: `2026-07-16-godot-client-parity-audit.md` (written before the autoload WS-wiring fix and the live e2e gate; this pass re-audits against current code).
> Method: two parallel deep-reads of the full web UI (app.js 5869 lines) and the full Godot client (main.gd 4197 lines + autoloads + board + core), then a category-by-category cross-diff.

## Current Status

The Godot client can now complete a real game end-to-end against the backend (verified by `tools/e2e_one_game.gd`: rout game, 105.8s, AI win, 8 end_turns). The autoload WS-wiring bug (`b53a745`) is fixed, so the real client actually receives WS snapshots now. Smoke test: 184/0.

What the Godot client already covers (parity with web): menu/entry + view switching, free-play one-click flow, room list (list/select/join), create room (name/preset/commander/BGM/team/join-mode), lobby polling + player list + team update + add/remove AI + AI config + start, save management (open/mainline grouping + resume + delete + refresh), mainline (list/detail/start/advance/next-battle/abandon/commander select), battle HUD (turn/phase/player badges, gold, CO roster + power, action bubble, attack confirm, war report, action log, info panel, turn banner, AI-thinking, battle result with stats, floating text, tutorial, dialog typewriter), combat (select/move-range/path-preview/attack-range/attack-targets/move/attack/heal-skill/recruit/wait/claim/end-turn/co-power/post-action-bubble), map editor (paint/biome/resize/place/erase/new/save/load/delete/list/custom->lobby-upsert), settings (name/font-size/color-pref/theme), audio (BGM player + manager + mute/volume API), network (full REST surface + WS with reconnect/heartbeat/since-seq + GameState event dispatch).

## Progress (2026-07-17 session)

P0 work done this session (smoke 184/0 throughout; **no backend changes**):

- **P0#1 攻击伤害预测** - DEFERRED per user decision (three-way constraint conflict; see "Deferred Gaps" below). Tracked in-repo.
- **P0#2 多技能系统** - DONE. Generalized the skill button from hardcoded `heal` to active-skill dispatch via `_active_skill_of` + `_enter_arcane_mode`. Now supports `heal` (healer) and `arcane_strike` (hero yun). Passive skills (snipe/double_strike) still auto-apply via the attack endpoint. (Note: web's bubble also only exposes heal; arcane_strike was unreachable in BOTH clients - Godot now leads.)
- **P0#3 主线 3 存档格** - DONE. Added `MLSlotsContainer` to MainlineView; fetches the user's `mainline:`-prefixed saves, renders up to 3 slots (occupied = resume/delete, empty = placeholder). Resume via `rejoin_game_by_name`, delete via `delete_game`.
- **P0#4 Dialog 系统升级** - DONE. Added `show_dialog_scene` dispatching on server scene `type`: dialogue/narration/choice/battle_ref/wait. Choice renders option buttons; battle_ref/wait skip. Fixed a pre-existing bug where `_on_mainline_dialogue_response` read `body as Array` but the server returns `{"scenes":[...]}` (so mainline dialogue never played). Added `_play_dialogue_scenes` handling Array / {scenes:[...]} / single-dict shapes. Speaker color applied to the name label.
- **P0#5 立绘/crest 系统** - DONE. Added `NetworkClient.list_heroes` (GET /heroes) + `_hero_speaker_map` (dialogue_name -> portrait path). Copied hero portraits/crests to `godot-client/assets/heroes/`. `_set_dialog_portrait` loads the portrait via `Image.load` into a dynamic TextureRect over the existing Portrait panel; unknown speakers keep the 👤 placeholder.
- **P0#6 BGM 音频** - DONE (core). Copied `sample_battle_01.mp3` (+ alias `1.mp3`) to `godot-client/audio/` and ran `--import` to generate .import files. The existing `_on_state_updated` -> `AudioManager.apply_battle_bgm(bgm)` trigger now resolves the track. Crossfade (web `_transitionToBgm`) remains a polish gap; Godot swaps the stream without fade.

Caveat: smoke is the automated gate for these UI changes (the live e2e is a passive free-play game and does not click skills / open mainline / play dialogue, so it would not exercise most of the above). Manual playtest recommended to confirm runtime behavior of skills, mainline slots, dialogue scenes, portraits, and BGM.

Files touched: `scripts/main.gd`, `scripts/autoload/network_client.gd`, `scenes/main.tscn`, this doc, new `assets/heroes/*`, new `audio/*.mp3`.

## Remaining Gaps

### P0 - 重大缺失 (blocks core combat / mainline experience)

1. **攻击伤害预测 (attack damage forecast).** *DEFERRED 2026-07-17 - see "Deferred Gaps" below.*
   Web `forecastAttack` + `forecastSingleHit` (app.js:2291 / 2242) mirror the server `calculate_damage` to preview main damage / crit rate / crit damage / type-advantage multiplier / target remaining HP / kill-or-not / counter damage / attacker HP after counter. Godot's attack-confirm panel only shows attacker/target/distance/HP - no damage preview at all.

2. **技能系统不全 (multi-skill system).**
   Web `doSkill` (app.js:3180) is generic but the action bubble only wires `heal` (`showUnitActionBubble` only adds a heal button; `onBubbleClick` only has a "heal" case). Server has 4 skills: `heal` (active, healer), `snipe` (passive, archer +1 range), `double_strike` (passive, knight 2 hits), `arcane_strike` (active, hero yun). The passive skills auto-apply via the attack endpoint. Godot only implements heal. **Real gap:** `arcane_strike` (yun's active skill) is unreachable in BOTH clients - generalize Godot's skill button to dispatch on the unit's actual active skill (covers heal + arcane_strike).

3. **主线 3 存档格系统 (mainline save slots).**
   Web `MainlineView.renderSlots` (app.js:4476) with `MAINLINE_SLOT_COUNT=3`: occupied slots (chapter name / turn / #id / resume / delete) + empty slots, slot resume via `rejoin_by_name`, slot delete via `DELETE /games/{id}`. Godot has no slot concept; mainline progress only advances via `advance` with no multi-slot.

4. **Dialog 系统升级 (Dialog system upgrade).**
   Web `Dialog` (app.js:3771) supports scene types dialogue / narration / choice / wait / battle_ref, typewriter with configurable cps (40 dialogue / 25 narration), speaker crest. Godot's `show_dialog` (main.gd:2013) only has typewriter + Continue - no choice / wait / battle_ref, no crest.

5. **立绘 / crest 系统 (portrait system).**
   Web `refreshHeroAssets` (app.js:3751) calls `GET /heroes` to fill `CHARACTER_ASSETS`, and the Dialog shows a portrait panel (`_setPortraitPanel` app.js:3968). Godot has no `/heroes` call and no portrait system.

6. **BGM 实际音频 (BGM audio assets).**
   Web serves real tracks from `/ui/assets/audio/bgm/` with cross-track crossfade (`_transitionToBgm` app.js:188), per-track volume / fade_in / fade_out. Godot's `godot-client/audio/` directory does not exist - BGM is a silent fallback (`audio_manager.gd` comment), no crossfade.

### P1 - 重要缺失 (parity / experience)

7. **观战完整流程 (spectator flow).** Web: per-room "👀 观战" button on the join list, lobby "加入观战者" two-choice modal (join-as-spectator / convert - convert currently toast-only), team-dropdown "切换为观战" (DELETE + POST join spectator), spectator hints (waiting-for-host / seat X/Y / max 8), spectator view limits (grey swatch / player card "观战中-无单位" / end-turn renamed "✅ 确认(继续)" / phase text / hide join button for spectators). Godot: only `join_mode` option + "👀 观战" phase badge.

8. **大厅房主行级控制 (host row-level lobby controls).** Web host sees everyone's (incl. AI) team dropdown + "➕ 新建队伍" + (self row only) "切换为观战". Godot: self team update + AI removal only, no host row-level controls.

9. **主线指挥官锁定原因 + Profile 防御 (commander lock reasons + profile ensure).** Web shows lock reasons (active_mainline / not-unlocked / current / selectable) and `ensureProfile` (`GET /profile/{name}` probe, 404 -> `POST /progression/profiles`, 409 ok). Godot: all chapters shown as clickable, no lock reasons, no profile endpoint.

10. **主线开始防狂点 / 409 重试 / 战败 modal / victory 对话.** Web: start button loading + 409 `mainline_already_active` auto-abandon-and-retry + dedicated "⚔️ 主线战败" modal + `victory.json` dialogue. Godot: none of these.

11. **射程查看 action + 地形 tooltip (range action + terrain tooltip).** Web: bubble "射程" action shows full threat area (`computeThreatArea`), cell `title` terrain tooltip (unit stats / owner / claim progress). Godot: no range action, no terrain tooltip (unit info only on unit click).

12. **AI 点评聊天 (AI commentary chat).** Web routes `commentary.text` / `ai_turn` WS to a chat panel with mood emoji. Godot: `commentary.*` WS is no-op (`network_client.gd:329`).

13. **创建房间选项 (create-room options).** Web: player count (2/3/4 cascades preset filter) + map seed (classic random) + BGM meta row (category / volume / fade) + map description + designer notes. Godot: hardcoded rout, no count/seed/BGM-meta/desc.

14. **参考 / 帮助 panel (reference / help panel).** Web: reference panel (terrain / units / skills tabs) + help view (objectives / terrain / units / turn flow / combat formula). Godot: `show_help` defined but no button wired, never called.

15. **占领进度 + 地块归属标记 (claim progress + tile owner marker).** Web: `tile-claim-progress` badge + progress bar + `tile-owner-marker` (team color + player color gradient). Godot: has claim action, no progress badge / bar / owner marker.

16. **阶段感知轮询 + 事件合并 + WS 安全网 (phase-aware polling + event coalescing + WS safety net).** Web: `adjustPollInterval` (accelerates for ai/animating/spectator) + `_wsSoftRefresh` 200ms debounce + WS-online 15s safety-net poll. Godot: fixed 2s lobby poll, no phase awareness, no debounce, no safety net.

17. **地图编辑器撤销 / 填充 / 画线 / 选择 (editor undo / fill / line / select).** Web: undo/redo (50 snapshots + Ctrl+Z/Y/Shift+Z) + BFS flood fill + Bresenham line + select tool (move / recolor units). Godot: no undo/redo, no fill, no line, no select tool (only Place/Erase).

18. **章节所需职业显示 (chapter required-class display).** Web: chapter card shows required classes. Godot: only battles count + synopsis tooltip.

### P2 - 轻微差异 (detail / polish)

19. 单位 sprite `hero_id` 分支: web uses `heroes/{id}.png` when hero_id present; Godot only `classic/{type}.png`.
20. 单位 / 技能 / 价格表动态拉取: web from `/games/units` + `/games/skills`; Godot hardcodes (mirrored in `Config.gd`, needs manual sync).
21. 设置: web has auto-refresh seconds (1-30) + sound checkbox; Godot hardcoded 2s poll, no sound UI (mute fn exists, no button).
22. 战报清空按钮: web has `clear-action-log`; Godot none.
23. CO 面板维度: web per `co_state` row (avatar / energy threshold / ⚡ active); Godot per player (emoji + name + energy bar + Power button).
24. HP 条颜色分级: web <35% red / <70% orange; Godot has HP bar, grading unconfirmed.
25. 左列分隔条拖拽: web `initSplitDivider` + localStorage; Godot none.
26. endTurn 浮动 Lv↑ / claim toast: web floats "Lv↑" on leveled units + "还需 X 回合" claim toast; Godot has level_up event but no float, claim no toast.
27. 撤销移动回 action bubble: web `cancel-move` (client) returns to bubble; Godot has `_cancel_action_mode`, post-move return-to-bubble unconfirmed.
28. 新日志 income toast: web detects income log -> toast; Godot none.
29. 房间列表 created_at 时间: web shows creation time; Godot only `#id name [preset] cap:N`.

### Godot 反向多出 (not gaps - Godot has, web doesn't)

- 教程气泡(首次自由对局 5 条提示)
- 字号三档设置(12/14/16)
- 三套主题(deep_gba / metal_silver / minimal_light)
- 自定义编辑器地图 -> 大厅预设自动 upsert(web 未接通)
- 编辑器内 DELETE 地图(web 走存档管理)
- AI 指挥官配置(虽仅 seat 2)
- HTTP serial queue(防并发)
- 心跳 `client.ping` 25s
- DEV 钩子:`BB_AUTO_PLAY` / `BB_AUTO_QUIT` / `BB_ATTACK_FORCE_RANGE`
- 战斗结算面板丰富统计(击杀/被击杀/占领/CO 峰值/回合/技能/原因 + 最近 12 条日志)
- 自动重连 0.5s 起步(web 1s)

## Suggested Next Development Order

Driven by the standing goal "complete the view system, combat system, and full games":

1. **P0#2** - multi-skill (generalize skill button to active-skill dispatch; covers heal + arcane_strike). P0#1 deferred.
2. **P0#3 + P0#4 + P0#5** - mainline save slots + Dialog upgrade + portrait system. Mainline narrative completeness (the three are coupled: portrait is part of Dialog, slots wrap the mainline flow).
3. **P0#6** - BGM audio. Likely a matter of locating the web audio assets and wiring them in.
4. **P1#7 + P1#8** - spectator flow + host row-level controls. "Full game" social completeness.
5. **P1#17 + P1#14** - editor undo/fill/line/select + help panel. Editor parity + onboarding.
6. Remaining P1/P2 in descending impact.

## Deferred Gaps (tracked)

### P0#1 - 攻击伤害预测 (DEFERRED 2026-07-17)

**Decision:** skip on Godot for now; leave as a known parity gap. Tracked here (and as a GitHub issue once `gh` is installed / a token is available - `gh` CLI is not currently installed on this machine).

**Why deferred:** three constraints conflict and all three cannot hold simultaneously -
- Web parity requires a pre-attack damage forecast (web `forecastAttack` / `forecastSingleHit`, app.js:2291 / 2242).
- Project memory `server-authority-no-duplicate-logic` forbids mirroring the damage formula on the client (user previously stopped a `_forecast_attack_simple` that reimplemented `calculate_damage`).
- "后端代码别动" forbids adding the `GET /forecast-attack` endpoint the memory recommends.

Verified 2026-07-17: server has NO forecast endpoint (`game/app/routes/actions.py` only exposes move/attack/skill/wait/claim/recruit). The web forecast is a pure client-side mirror of `calculate_damage`.

**Options when revisited (pick one):**
1. Add read-only `GET /games/{id}/forecast-attack` reusing existing server `calculate_damage` (honors server-authority; the only "backend change" is a read endpoint that adds no game logic). Requires lifting "后端别动" for this one endpoint.
2. Keep skipping (current state).
3. Port `forecastSingleHit` to GDScript like web (violates the server-authority memory).

**Current Godot behavior:** attack-confirm panel shows attacker/target/distance/HP only (`main.gd:3915`). Actual damage is still shown post-attack via the `unit_attacked` event delta - only the pre-attack forecast is missing.

## Files To Watch

- `godot-client/scripts/main.gd` - most UI orchestration and response handling.
- `godot-client/scripts/autoload/network_client.gd` - typed REST/WebSocket API wrapper.
- `godot-client/scripts/autoload/game_state.gd` - snapshot cache + event dispatch.
- `godot-client/scripts/autoload/config.gd` - game-constant mirror (where hardcoded unit/skill/price tables live).
- `godot-client/scripts/autoload/audio_manager.gd` - BGM / mute / volume.
- `godot-client/scripts/board/unit_node.gd` - unit visuals (sprite / HP / MP / morale / acted).
- `godot-client/scripts/core/map_logic.gd` - client-side BFS / pathfind / LoS mirror.
- `godot-client/tools/e2e_one_game.gd` - live backend e2e gate.
- `game/app/web/app.js` + `index.html` - source of truth for remaining parity.
