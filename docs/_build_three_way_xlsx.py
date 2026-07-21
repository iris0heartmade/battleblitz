"""
生成 BattleBlitz 三方对比与接口覆盖分析报告 .xlsx
- 多 sheet:项目概览 / 后端接口全景 / 接口调用矩阵 / 功能模块覆盖 / 差异详解 / 未调用接口 / 死代码
- 关键:每个接口均标注「功能流程作用」(在 gameplay 链路里的位置 / 谁触发 / 副作用)
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


# ============================================================
# 样式
# ============================================================

TITLE_FILL = PatternFill("solid", fgColor="1F2937")
TITLE_FONT = Font(name="Microsoft YaHei", size=14, bold=True, color="FFFFFF")

HEADER_FILL = PatternFill("solid", fgColor="2563EB")
HEADER_FONT = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")

SECTION_FILL = PatternFill("solid", fgColor="F3F4F6")
SECTION_FONT = Font(name="Microsoft YaHei", size=11, bold=True, color="111827")

ROLE_FILL = PatternFill("solid", fgColor="ECFDF5")
ROLE_FONT = Font(name="Microsoft YaHei", size=10, color="065F46")

YES_FILL = PatternFill("solid", fgColor="DCFCE7")
YES_FONT = Font(name="Microsoft YaHei", size=10, color="166534", bold=True)

PARTIAL_FILL = PatternFill("solid", fgColor="FEF3C7")
PARTIAL_FONT = Font(name="Microsoft YaHei", size=10, color="92400E", bold=True)

NO_FILL = PatternFill("solid", fgColor="FEE2E2")
NO_FONT = Font(name="Microsoft YaHei", size=10, color="991B1B", bold=True)

NA_FILL = PatternFill("solid", fgColor="F3F4F6")
NA_FONT = Font(name="Microsoft YaHei", size=10, color="6B7280")

BODY_FONT = Font(name="Microsoft YaHei", size=10)

THIN = Side(border_style="thin", color="D1D5DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _mark(cell, text: str, kind: str) -> None:
    cell.value = text
    cell.font = BODY_FONT
    cell.alignment = WRAP
    cell.border = BORDER
    if kind == "yes":
        cell.fill = YES_FILL
        cell.font = YES_FONT
        cell.alignment = CENTER
    elif kind == "partial":
        cell.fill = PARTIAL_FILL
        cell.font = PARTIAL_FONT
        cell.alignment = CENTER
    elif kind == "no":
        cell.fill = NO_FILL
        cell.font = NO_FONT
        cell.alignment = CENTER
    elif kind == "na":
        cell.fill = NA_FILL
        cell.font = NA_FONT
        cell.alignment = CENTER


def _row(ws: Worksheet, row: int, values, header: bool = False, section: bool = False) -> None:
    for col, val in enumerate(values, start=1):
        c = ws.cell(row=row, column=col, value=val)
        c.border = BORDER
        c.alignment = WRAP
        if header:
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = CENTER
        elif section:
            c.fill = SECTION_FILL
            c.font = SECTION_FONT
            c.alignment = WRAP
        else:
            c.font = BODY_FONT


def _autosize(ws: Worksheet, widths) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _freeze(ws: Worksheet, cell: str = "B2") -> None:
    ws.freeze_panes = cell


def _sheet_title(ws: Worksheet, title: str) -> None:
    ws.merge_cells("A1:Z1")
    c = ws.cell(row=1, column=1, value=title)
    c.fill = TITLE_FILL
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30


def _role(ws: Worksheet, row: int, col: int, text: str) -> None:
    c = ws.cell(row=row, column=col, value=text)
    c.font = ROLE_FONT
    c.alignment = WRAP
    c.border = BORDER
    c.fill = ROLE_FILL


def _mark_label(kind: str) -> str:
    return {"yes": "✅", "partial": "△", "no": "❌", "na": "—"}.get(kind, "")


# ============================================================
# 端点元数据(单一来源)
# ============================================================
# 字段:method, path, prefix, req, resp, file, module, role, note

ENDPOINTS = [
    # meta
    ("GET", "/", "", "—", "—", "main.py:92", "meta",
     "重定向入口(无客户端代码消费,浏览器自动跳转)",
     "前端根路径 → /ui/"),
    ("GET", "/ui", "", "—", "—", "main.py:99", "meta",
     "重定向入口", "/ui → /ui/(带尾斜杠)"),
    ("GET", "/ui/", "", "—", "—", "main.py:104", "meta",
     "返回 SPA 单页 HTML,挂载 app.js / style.css",
     "浏览器输入 localhost:8000 → index.html → JS 接管"),
    ("GET", "/healthz", "", "—", "—", "main.py:118", "meta",
     "健康检查,运维 / 容器探针用",
     "返回 {\"status\":\"ok\"};无客户端代码消费"),
    # game.py
    ("POST", "/games", "/games", "CreateGameRequest", "GameSummaryOut(201)", "routes/game.py", "game",
     "「创建对局」入口:玩家点 '新建游戏' → 表单(map_preset / win_condition / BGM) → 服务端生成 Game 行 + capacity 自动派生 → 返回 game_id → 客户端立即 POST /games/{id}/join",
     "副作用:写 1 行 Game;capacity 来自 map.recommended_players"),
    ("GET", "/games", "/games", "query: user_name?", "List[GameSummaryOut]", "routes/game.py", "game",
     "加入房间页的房间列表:玩家进 #view-join-game → 拉到 waiting 房间渲染卡片",
     "可按 user_name 过滤;可选 query 影响存档视图"),
    ("DELETE", "/games/{game_id}", "/games", "—", "204", "routes/game.py", "game",
     "删除房间(只允许 waiting/finished 状态):WebUI 旧存档删除按钮;Godot 仅 smoke 校验存在",
     "已开始游戏则 409"),
    ("POST", "/games/{game_id}/join", "/games", "JoinGameRequest", "PlayerOut(201)", "routes/game.py", "game",
     "玩家入席:服务端 spawn 初始单位并写入 Player + Tile.occupied_unit_id;返回 PlayerOut 含 player_id 用于后续所有动作用的 caller 身份",
     "加注:role=spectator → 不 spawn 单位;team 用于胜负聚合"),
    ("PATCH", "/games/{game_id}/players/{player_id}/team", "/games", "UpdateTeamRequest",
     "dict{ok,player_id,team}", "routes/game.py", "game",
     "切换队伍:大厅下拉切 team;服务端写 player.team → 影响 win_condition 队伍聚合判断",
     "已开局改 team 一般 409"),
    ("PATCH", "/games/{game_id}/players/{player_id}/seat", "/games", "UpdateSeatRequest",
     "GameStateOut", "routes/game.py", "game",
     "改座位:Godot 大厅拖拽座位 + 多 AI 配置文件化",
     "WebUI 用 team 表达代替,不发此端点"),
    ("POST", "/games/{game_id}/rejoin", "/games", "RejoinGameRequest", "RejoinGameResponse",
     "routes/game.py", "game",
     "按 player_id 重连:浏览器刷新 / 标签页被关后玩家拿 player_id 回房间",
     "返回 GameStatus + PlayerOut"),
    ("POST", "/games/{game_id}/rejoin_by_name", "/games", "RejoinByNameRequest(内部)",
     "RejoinGameResponse", "routes/game.py", "game",
     "按 user_name 重连:本地续局 / 存档续战用,无需知道 player_id",
     "UserName 在大厅内应唯一,否则取第一个匹配"),
    ("POST", "/games/{game_id}/start", "/games", "StartGameRequest(可选)", "GameStateOut",
     "routes/game.py", "game",
     "房主开始游戏:服务端校验 MIN_PLAYERS → 写 game.status='running' + game.started_at → 返回完整 GameState(包含初始单位)",
     "人数不够 409;已开始 409"),
    ("GET", "/games/{game_id}/lobby", "/games", "—", "LobbyInfoOut",
     "routes/game.py", "game",
     "大厅轮询拿队伍聚合(teams[]):WebUI refreshLobby 每 2s 拉一次用于显示 '红队 2/2'",
     "Godot 改用 /state 解析,本端点不调"),
    ("GET", "/games/{game_id}/state", "/games", "—", "GameStateOut",
     "routes/game.py", "game",
     "完整 GameState 快照:战斗中 WS event.delta 后 200ms debounce GET;包含 tiles / players / co_states / pending_claims",
     "Godot 10 处调用;WebUI 战斗内轮询兜底"),
    ("GET", "/games/presets", "/games", "—", "PresetsResponse",
     "routes/game.py", "game",
     "地图预设元数据(大厅创建时下拉选项):包含 id / name / description / biome / size / recommended_players / notes",
     "启动时一次性拉取"),
    ("GET", "/games/skills", "/games", "—", "List[dict]", "routes/game.py", "game",
     "技能元数据(描述/动画/icon 资源 key):WebUI 启动时拉一次并缓存",
     "Godot 用 Config 镜像,不调"),
    ("GET", "/games/units", "/games", "—", "List[dict]", "routes/game.py", "game",
     "单位类型元数据(HP/ATK/DEF/MATK/MDEF/射程/技能):WebUI 启动时拉一次",
     "Godot 用 Config 镜像,不调"),
    ("POST", "/games/{game_id}/add-ai", "/games", "AddAIRequest", "PlayerOut(201)",
     "routes/game.py", "game",
     "房主加 AI:选 difficulty / agent_kind=rules|llm / personality=aggressive|balanced|conservative",
     "服务端用对应 Agent 类 spawn Unit"),
    ("DELETE", "/games/{game_id}/players/{player_id}", "/games", "—", "GameStateOut",
     "routes/game.py", "game",
     "移除玩家或 AI(等待阶段限定):WebUI '移除 AI' 按钮 + 玩家转观战步骤 1",
     "已开始游戏 409"),
    # actions
    ("POST", "/games/{game_id}/move", "/games", "MoveRequest", "MoveResult",
     "routes/actions.py", "actions",
     "移动:玩家点格子 → 服务端用 A* 按地形 MP 消耗算可达路径 → 移动单位并扣 MP → 返回 from/to/cost/castle_captured",
     "REST 主路径(WS action dispatcher 预留)"),
    ("POST", "/games/{game_id}/attack", "/games", "AttackRequest", "AttackResult",
     "routes/actions.py", "actions",
     "执行攻击:服务端按攻击方类型选 ATK/MATK 公式算伤害 + 反击 + 双击 + 暴击 + 经验 → 返回双方 HP 后",
     "Godot 攻击确认面板 ConfirmBtn"),
    ("GET", "/games/{game_id}/forecast-attack", "/games",
     "query: player_id, attacker_id, target_id", "AttackForecastOut",
     "routes/actions.py", "actions",
     "攻击预测(不改变状态):攻击目标点击 → 服务端复用攻击范围/视线/反击免疫校验 → 返回 dmg/crit/counter/counter_will_kill",
     "Godot 用作右侧信息栏的 '战斗预测' 区"),
    ("POST", "/games/{game_id}/skill", "/games", "SkillRequest", "SkillResult",
     "routes/actions.py", "actions",
     "使用主动技能:heal(治疗友军)/double_strike(连击)/snipe(弓手远程);服务端校验当前 MP 与目标合法性",
     "WASM Skill 按钮"),
    ("POST", "/games/{game_id}/wait", "/games", "WaitRequest", "WaitResult",
     "routes/actions.py", "actions",
     "待命:关闭本回合该单位行动权 → 让其他单位行动;单元 disable 行动气泡",
     "Godot WaitBtn"),
    ("POST", "/games/{game_id}/claim", "/games", "ClaimRequest", "ClaimResult",
     "routes/actions.py", "actions",
     "占领村落/城堡(2 回合完成):服务端写 PendingClaim → 跨多回合 -> 完成时翻转 Tile.owner_id 并发金币",
     "前端显示 '占领进度' UI"),
    ("POST", "/games/{game_id}/recruit", "/games", "RecruitRequest", "RecruitResult",
     "routes/actions.py", "actions",
     "兵营招募:花金币生成新单位(barracks 上必须空);服务端扣 gold 写 Unit + 占用 Tile",
     "5 种基础兵种(swordsman/archer/knight/warlock/healer)"),
    # turns
    ("POST", "/games/{game_id}/end-turn", "/games", "EndTurnRequest", "EndTurnResult",
     "routes/turns.py", "turns",
     "回合手柄:推进 current_player_index;若所有人都 end_turn 则 current_player=0+1;后台调度器在 AI 阶段自动调用",
     "WebUI/Godot EndTurnButton"),
    # editor
    ("GET", "/editor/maps", "/editor/maps", "—", "List[CustomMapListItem]",
     "routes/editor.py", "editor",
     "编辑器 '读取' 下列出所有自定义地图",
     "进入编辑器 / 保存 / 删除后刷新"),
    ("GET", "/editor/maps/{map_id}", "/editor/maps", "—", "CustomMapOut",
     "routes/editor.py", "editor",
     "编辑器加载指定地图:返回 layout / biome / size / initial_units / tile_owners",
     "LoadBtn 触发"),
    ("POST", "/editor/maps", "/editor/maps", "CustomMapSave", "CustomMapOut(201)",
     "routes/editor.py", "editor",
     "编辑器 '保存':新建或更新地图(id 缺省=新建)",
     "SaveBtn;同时支持新建/更新"),
    ("DELETE", "/editor/maps/{map_id}", "/editor/maps", "—", "204",
     "routes/editor.py", "editor",
     "编辑器 '删除单图':WebUI 无按钮;Godot DeleteBtn 触发",
     "P1:WebUI 缺按钮"),
    # profile
    ("GET", "/profile/{user_name}", "/profile", "—", "PlayerProfileOut",
     "routes/profile.py", "profile",
     "玩家档案查询:主线 ensureProfile() GET-404-then-POST 模式",
     "WebUI 用;Godot 不调"),
    ("POST", "/profile/{user_name}/mainline/start", "/profile",
     "StartMainlineRequest", "MainlineStatusOut",
     "routes/profile.py", "profile",
     "Profile-keyed 老路径(已废弃):WebUI 直接调;Godot 走新版 /mainlines/*",
     "已被 /mainlines/* 取代"),
    ("POST", "/profile/{user_name}/mainline/advance", "/profile",
     "AdvanceMainlineRequest", "MainlineStatusOut",
     "routes/profile.py", "profile",
     "Profile-keyed 老路径(已废弃):推进战役",
     "已被 /mainlines/* 取代"),
    ("POST", "/profile/{user_name}/mainline/abandon", "/profile",
     "AbandonMainlineRequest(可选)", "MainlineStatusOut",
     "routes/profile.py", "profile",
     "Profile-keyed 老路径(已废弃):放弃战役",
     "已被 /mainlines/* 取代"),
    # progression
    ("POST", "/progression/profiles", "/progression",
     "CreateProfileRequest", "PlayerProfileOut(201)", "progression/api.py",
     "progression",
     "创建玩家档案(Profile-keyed):WebUI ensureProfile 用一次;Godot 走 /profile/{name}",
     "返回 profile_id"),
    ("GET", "/progression/profiles", "/progression",
     "query: limit, offset", "List[PlayerProfileOut]", "progression/api.py",
     "progression",
     "档案列表(分页):仅测试用",
     "前端未接"),
    ("GET", "/progression/profiles/{profile_id}", "/progression", "—",
     "PlayerProfileOut", "progression/api.py", "progression",
     "单档案(用于调试/管理):仅测试用",
     "前端未接"),
    ("POST", "/progression/profiles/{profile_id}/units", "/progression",
     "CreateUnitRequest", "UnitInstanceOut(201)", "progression/api.py",
     "progression",
     "档案中新建单位(英雄/转职):服务端内部路径;主线 /mainlines/{id}/prepare 包装",
     "前端未直调"),
    ("GET", "/progression/profiles/{profile_id}/units", "/progression", "—",
     "List[UnitInstanceOut]", "progression/api.py", "progression",
     "档案的单位实例列表:仅测试用",
     "前端未接"),
    ("GET", "/progression/units/{unit_id}", "/progression", "—",
     "UnitInstanceOut", "progression/api.py", "progression",
     "单单位实例(战斗内可查询):仅测试用",
     "前端未接"),
    ("POST", "/progression/units/{unit_id}/xp", "/progression",
     "AwardXpRequest", "AwardXpResult", "progression/api.py",
     "progression",
     "颁奖 XP:服务端战斗胜利结算时内部调;前端目前无显式入口",
     "P2:考虑主线 prepare UI 暴露"),
    ("POST", "/progression/units/{unit_id}/promote", "/progression",
     "PromoteRequest", "PromoteResult", "progression/api.py",
     "progression",
     "兵阶晋升(低级→高级兵种);主线 /mainlines/{id}/prepare/promote 包装调用",
     "前端未直调"),
    ("DELETE", "/progression/units/{unit_id}", "/progression", "—",
     "204", "progression/api.py", "progression",
     "删除单位(debug 用):仅测试用",
     "前端未接"),
    # mainline
    ("GET", "/mainlines", "/mainlines", "query: user_name?",
     "List[MainlineDetailOut]", "routes/mainline.py", "mainline",
     "主线章节列表页:玩家进 #view-mainline-list → 渲染章节卡片 + 已解锁/当前进度",
     "可按 user_name 过滤当前可玩章节"),
    ("GET", "/mainlines/dialogue", "/mainlines", "query: path",
     "dict", "routes/mainline.py", "mainline",
     "读剧情 JSON 文件:pre_battle / post_battle / victory 场景;Dialog 引擎渲染",
     "WebUI/Godot 都用 5 场景类型"),
    ("GET", "/mainlines/{mainline_id}", "/mainlines", "—",
     "MainlineDetailOut", "routes/mainline.py", "mainline",
     "主线详情:BattlePreview / 胜利条件 / 推荐 CO",
     "进章节前查详情"),
    ("GET", "/mainlines/{mainline_id}/prepare", "/mainlines",
     "query: user_name", "MainlinePrepareOut", "routes/mainline.py",
     "mainline",
     "战前整备 payload:服务端读 profile → 返回 heroes[] / roster[] / inventory[] / battle_id / win_condition / bgm_meta",
     "6 个 tab 数据源"),
    ("POST", "/mainlines/{mainline_id}/prepare/promote", "/mainlines",
     "MainlinePreparePromoteRequest", "MainlinePreparePromoteOut",
     "routes/mainline.py", "mainline",
     "战前转职按钮 → 服务端调 progression/units/{id}/promote + 返回最新 hero 状态",
     "Godot main.gd:6346"),
    ("POST", "/mainlines/{mainline_id}/prepare/equipment", "/mainlines",
     "MainlinePrepareEquipmentRequest", "MainlinePrepareEquipmentOut",
     "routes/mainline.py", "mainline",
     "战前装备/卸下:服务端写单位 inventory",
     "Godot main.gd:6356"),
    ("GET", "/mainlines/{mainline_id}/shop", "/mainlines",
     "query: user_name", "MainlineShopOut", "routes/mainline.py",
     "mainline",
     "战后商店库存:服务端读 profile.unlocked_items → 列出可买商品",
     "进 #view-mainline-shop 显示"),
    ("POST", "/mainlines/{mainline_id}/shop/purchase", "/mainlines",
     "MainlineShopPurchaseRequest", "MainlineShopPurchaseOut",
     "routes/mainline.py", "mainline",
     "战后购买:扣金币写 inventory;返回新余额 + 物品详情",
     "_leavePostBattleShop 触发下一章"),
    ("POST", "/mainlines/{mainline_id}/prepare/complete", "/mainlines",
     "PrepCompleteRequest", "AutoSaveCheckpointOut", "routes/mainline.py",
     "mainline",
     "玩家点 '准备好了' → 服务端写 profile.active_prep + 触发 auto_save_checkpoint + 返回 next_battle_id",
     "Godot 实现但 UI 未触发(P0 接通)"),
    ("POST", "/mainlines/{mainline_id}/start", "/mainlines",
     "MainlineStartRequest", "MainlineStartOut(201)",
     "routes/mainline.py", "mainline",
     "开始主线战斗:服务端刷出第一章 game_id → 客户端跳 GameView",
     "Godot 含 force=true 重试"),
    ("POST", "/mainlines/{mainline_id}/advance", "/mainlines",
     "MainlineAdvanceRequest", "MainlineAdvanceOut", "routes/mainline.py",
     "mainline",
     "战斗胜利后推进:服务端结算 → 写 profile + 推 chapter 进度 → 返回 next_battle_id",
     "由 onBattleFinished WS 事件触发"),
    ("POST", "/mainlines/{mainline_id}/next-battle", "/mainlines",
     "MainlineNextBattleRequest", "MainlineNextBattleOut(201)",
     "routes/mainline.py", "mainline",
     "刷出下一场战斗(同章节内):服务端复用 chapter 进度刷新 game_id",
     "Godot main.gd:6611"),
    ("POST", "/mainlines/{mainline_id}/abandon", "/mainlines",
     "MainlineAbandonRequest", "MainlineAbandonOut", "routes/mainline.py",
     "mainline",
     "放弃章节:清理 profile.active_mainline → 客户端跳主菜单",
     "显示二次确认 modal"),
    ("GET", "/mainlines/{mainline_id}/mercenary/config", "/mainlines",
     "query: user_name", "MainlineMercenaryConfigOut",
     "routes/mainline.py", "mainline",
     "佣兵点数配置:服务端读 profile.mercenary_points → 返回当前可分配上限",
     "Godot 6-tab Mercenary"),
    ("POST", "/mainlines/{mainline_id}/mercenary/allocate", "/mainlines",
     "MainlineMercenaryAllocateRequest", "MainlineMercenaryAllocateOut",
     "routes/mainline.py", "mainline",
     "佣兵点数分配:玩家拖点数条 → 服务端写分配 → 影响战前 roster 强度",
     "Godot main.gd:6384"),
    # heroes / audio
    ("GET", "/heroes", "/heroes", "—", "List[dict]",
     "routes/heroes.py", "heroes",
     "英雄注册表:返回 sprite / portrait / crest URL / 合成属性 / 技能列表",
     "启动时一次性拉取;对话立绘/CO 立绘共用"),
    ("GET", "/audio/tracks", "/audio", "—",
     "dict{defaults, tracks}", "routes/audio.py", "audio",
     "战役 BGM 目录:进 '创建游戏' 表单时拉 → 填充曲目下拉",
     "AudioManager 解析为可播放 URL"),
    # commanders
    ("GET", "/players/me/commanders", "(根)",
     "query: user_name", "dict", "routes/commanders.py", "commanders",
     "已解锁指挥官列表 + 当前主线 CO:进 #view-mainline-list 时拉 → 渲染指挥官选择面板",
     "WebUI/Godot 都用"),
    ("POST", "/mainlines/{mainline_id}/select-commander", "(根)",
     "SelectMainlineCommanderIn", "dict", "routes/commanders.py",
     "commanders",
     "章节指挥官选择(战前):写 player.commander_id → 影响 CO meter 阈值和增益",
     "锁定后不可改"),
    ("POST", "/games/{game_id}/select-commander", "(根)",
     "SelectBattleCommanderIn", "—", "routes/commanders.py", "commanders",
     "战内改选(强制 409:commander locked):服务端埋点;战内改 CO 不允许",
     "实际两端都不调"),
    ("POST", "/games/{game_id}/co-power", "(根)",
     "FireCOPowerIn", "dict", "routes/commanders.py", "commanders",
     "发动 CO Power:当 meter 满 → 服务端对所有友军加 atk/def/移动持续 N 回合 + 返回 GameStateOut",
     "WebUI/Godot CO meter 按钮都接"),
    # save
    ("GET", "/saves", "(根)", "query: user_name",
     "SaveListOut", "routes/save.py", "save",
     "存档列表(5 槽位):玩家进存档视图 → 列出 3 手动 + 1 自动 + 1 suspend",
     "按 user_name 过滤"),
    ("POST", "/saves/save", "(根)", "SaveManualRequest",
     "SaveManualOut", "routes/save.py", "save",
     "手动存档(0/1/2 三槽):序列化当前 GameState → 写 slot JSON",
     "WebUI 有按钮;Godot 包好未触发(P0 接通)"),
    ("POST", "/saves/load", "(根)", "SaveLoadRequest",
     "SaveLoadOut", "routes/save.py", "save",
     "读档:服务端反序列化 → 新建 game_id 让玩家进 GameView",
     "LoadBtn"),
    ("POST", "/saves/load_suspend", "(根)",
     "LoadSuspendRequest", "LoadSuspendOut", "routes/save.py", "save",
     "读挂起槽(掉线/手动):WS 断线触发 → 玩家主页的 '▶ 继续中断战斗' 按钮",
     "LoadSuspendBtn"),
    ("POST", "/saves/erase", "(根)", "SaveEraseRequest",
     "SaveEraseOut", "routes/save.py", "save",
     "清除存档(单槽):玩家在存档页 '删除' 按钮 → 服务端清空 JSON",
     "EraseBtn"),
    ("POST", "/games/{game_id}/suspend", "(根)",
     "SuspendRequest", "SuspendOut", "routes/save.py", "save",
     "主动挂起当前对局:写专有 suspend 槽;WS 断线服务端自动调用",
     "Godot capture_suspend 定义未触发"),
    # WS
    ("WS", "/debug/ws/games/{game_id}", "/debug/ws", "—",
     "WS frames", "routes/debug_ws.py", "debug",
     "调试事件流(无鉴权):连接立即推 server.hello → 转发 GameEvent 为 event.delta;测试工具用",
     "两端都不调,纯调试"),
    ("WS", "/ws/games/{game_id}", "/ws",
     "query: player_id, since_seq", "WS frames", "routes/ws_gateway.py",
     "ws-gateway",
     "正式事件流:server.hello → state.snapshot → 实时 event.delta;30s server.pong 断线触发 suspend 写自动存档",
     "WebSocket 是战斗主更新通道;REST GET /state 是兜底"),
]


def build_sheet_overview(wb: Workbook) -> None:
    ws = wb.create_sheet("项目概览", 0)
    _sheet_title(ws, "BattleBlitz 三方对比 · 项目概览 (2026-07-21)")

    _row(ws, 2, ["维度", "后端 (game/app/)", "WebUI (game/app/web/)", "Godot Client (godot-client/)"],
         header=True)

    rows = [
        ["语言", "Python 3.11", "原生 HTML / CSS / JS(无框架)", "GDScript 4.7"],
        ["主要框架",
         "FastAPI + SQLAlchemy 异步 + Pydantic v2 + uvicorn",
         "无,DOM + fetch + WebSocket + localStorage",
         "Godot 4.7 SceneTree + HTTPRequest + WebSocketPeer"],
        ["入口文件", "game/app/main.py:43", "game/app/web/index.html",
         "godot-client/project.godot → scenes/main.tscn"],
        ["入口逻辑(主要行数)",
         "main.py 150 行 / 路由总 ~3k 行 / game_logic.py 977 行",
         "index.html ~700 行 + style.css 3078 行 + app.js 7239 行",
         "project.godot + main.tscn 2048 行 + main.gd 7372 行 + 7 个 autoload"],
        ["HTTP / WS 封装",
         "(后端本身无封装,导出 router)",
         "api(method, path, body) 单函数 + connectWS()(app.js:264-302, 1798)",
         "NetworkClient.request(method, path, body, callback) + connect_to_game()(network_client.gd:106, 224)"],
        ["会话持久化",
         "(服务端无状态)",
         "localStorage['battleblitz.session.v1'] + localStorage['battleblitz.settings.v1']",
         "UserSettings autoload + user://battleblitz.cfg"],
        ["资产目录",
         "42+ 张 game/maps/*.json + SQLite(battleblitz.db)",
         "game/app/web/assets/{tiles,heroes,classic,audio,crest,portrait}/*",
         "godot-client/assets/tiles/*(由 tools/sync_assets.py 拷)+ godot-ref/(参考)"],
        ["核心模型(回滚/回放/快照)",
         "FastAPI lifespan + ws_gateway since_seq 环形缓冲 + auto_save_checkpoint",
         "(无)", "NetworkClient _last_received_seq + 25s ping + since_seq 重放"],
        ["视图层",
         "REST 返回 JSON + WS 推送事件流",
         '<section class="view" hidden> + showView(name) 切换',
         "main.tscn 子 Control + visible 切换 + _show_view(name)"],
        ["棋盘渲染",
         "(后端不渲染)",
         "CSS Grid 自适应容器 + DOM 节点 + 浮动文字",
         "TileMapLayer 三层(Ground/Structure/Decor)+ UnitNode 多组件"],
        ["已注册 router 数", "13 + 4 meta 路由", "—", "—"],
        ["总端点数(估)", "73(REST 70 + WS 2 + meta 4 + 内部 helper)",
         "~50 REST + 1 WS 实调", "~45 REST + 1 WS 实调"],
        ["自动化测试/工具数", "pytest + e2e + tests/",
         "(无测试工具,但暴露 window.dialog / window.__bbState 探针)",
         "tools/ 下 22 个脚本(smoke + e2e + 截图 + 教程)"],
        ["代码体量(主代码)",
         "23 个 .py + game_logic.py 977 行",
         "app.js 7239 行",
         "main.gd 7372 行 + network_client.gd 数百行"],
    ]
    for i, r in enumerate(rows, start=3):
        _row(ws, i, r)

    _autosize(ws, [22, 50, 45, 45])
    _freeze(ws, "A3")


# ============================================================
# Sheet 2: 后端接口全景(加重 '功能流程作用' 列)
# ============================================================

def build_sheet_backend(wb: Workbook) -> None:
    ws = wb.create_sheet("后端接口全景")
    _sheet_title(ws, "后端接口全景 · 每条均标注 '功能流程作用'(在玩家体感链路里的位置)")

    headers = ["#", "HTTP 方法", "路径", "前缀", "请求 Schema", "响应 Schema",
               "路由文件", "模块", "功能流程作用", "副作用 / 备注"]
    _row(ws, 2, headers, header=True)

    for i, ep in enumerate(ENDPOINTS, start=3):
        method, path, prefix, req, resp, file, module, role, note = ep
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT

        c = ws.cell(row=i, column=2, value=method)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        c = ws.cell(row=i, column=3, value=path)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

        c = ws.cell(row=i, column=4, value=prefix)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        c = ws.cell(row=i, column=5, value=req)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

        c = ws.cell(row=i, column=6, value=resp)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

        c = ws.cell(row=i, column=7, value=file)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        c = ws.cell(row=i, column=8, value=module)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        _role(ws, i, 9, role)

        c = ws.cell(row=i, column=10, value=note)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

    _autosize(ws, [5, 7, 48, 10, 25, 27, 18, 12, 55, 50])
    _freeze(ws, "C3")


# ============================================================
# Sheet 3: 接口调用矩阵(每个接口附 '功能流程作用')
# ============================================================

# (method, path, kind_w, kind_g, kind_t, module, role, note)
MATRIX = [
    # meta
    ("GET", "/", "yes", "yes", "yes", "meta",
     "玩家浏览器输入根路径触发,自动跳 SPA",
     "两端都跟随 302"),
    ("GET", "/ui/", "yes", "yes", "na", "meta",
     "浏览器加载 SPA 单页,JS 接管后续所有交互",
     "Godot 不直接打开(HTTP 类比)"),
    ("GET", "/healthz", "no", "no", "yes", "meta",
     "健康检查,运维/容器探针触发",
     "客户端代码不消费"),
    # game.py
    ("POST", "/games", "yes", "yes", "yes", "game",
     "「创建对局」入口:写入 Game 行 + 返回 game_id",
     "→ 客户端立即 POST /join"),
    ("GET", "/games", "yes", "yes", "yes", "game",
     "加入房间页的房间列表数据源",
     "WebUI 进 #view-join-game;Godot 入大厅时拉"),
    ("DELETE", "/games/{id}", "yes", "no", "partial", "game",
     "删除房间存档(等待/结束态):WebUI 旧存档删除按钮",
     "已开始游戏 409"),
    ("POST", "/games/{id}/join", "yes", "yes", "yes", "game",
     "玩家入席:服务端 spawn 初始单位 + 返回 PlayerOut 含 player_id 后续 caller",
     "role=spectator 不 spawn 单位"),
    ("PATCH", "/games/{id}/players/{pid}/team", "yes", "yes", "yes", "game",
     "大厅下拉切队;已开局一般 409",
     "影响 win_condition 队伍聚合"),
    ("PATCH", "/games/{id}/players/{pid}/seat", "no", "yes", "yes", "game",
     "改座位:仅 Godot 拖拽座位触发",
     "WebUI 用 team 表达代替"),
    ("POST", "/games/{id}/rejoin", "yes", "yes", "yes", "game",
     "按 player_id 重连:浏览器刷新后回房间",
     "返回 GameStatus"),
    ("POST", "/games/{id}/rejoin_by_name", "yes", "yes", "yes", "game",
     "按 user_name 重连:无需 player_id;本地续局 / 主线存档续战",
     "WebUI:主菜单 '继续中断战斗';Godot resume by_name"),
    ("POST", "/games/{id}/start", "yes", "yes", "yes", "game",
     "房主开始:MIN_PLAYERS 校验 → 写 status='running' → 返回完整 GameState",
     "人数不够 409"),
    ("GET", "/games/{id}/lobby", "yes", "no", "yes", "game",
     "大厅轮询拿队伍聚合(teams[]):WebUI refreshLobby 2s 一次",
     "Godot 改用 /state 解析"),
    ("GET", "/games/{id}/state", "yes", "yes", "yes", "game",
     "完整 GameState 快照:战中 WS event.delta 后 200ms debounce GET",
     "含 tiles/players/co_states/pending_claims"),
    ("GET", "/games/presets", "yes", "yes", "yes", "game",
     "地图预设元数据:大厅创建时下拉选项",
     "启动一次性拉"),
    ("GET", "/games/skills", "yes", "no", "no", "game",
     "技能元数据:WebUI 启动拉一次缓存",
     "Godot 用 Config 镜像"),
    ("GET", "/games/units", "yes", "no", "no", "game",
     "单位类型元数据:WebUI 启动拉一次",
     "Godot 用 Config 镜像"),
    ("POST", "/games/{id}/add-ai", "yes", "yes", "yes", "game",
     "房主加 AI:选 difficulty/agent_kind/personality",
     "服务端对应 Agent 驱动"),
    ("DELETE", "/games/{id}/players/{pid}", "yes", "yes", "yes", "game",
     "移除 AI/玩家(等待阶段):WebUI '移除 AI' + 玩家转观战步骤 1",
     "已开始 409"),
    # actions
    ("POST", "/games/{id}/move", "yes", "yes", "yes", "actions",
     "移动:服务端 A* 算可达 → 移动 + 扣 MP",
     "REST 主路径;WS action dispatcher 预留"),
    ("POST", "/games/{id}/attack", "yes", "yes", "yes", "actions",
     "执行攻击:按攻击方类型选 ATK/MATK → 伤害+反击+双击+暴击+经验",
     "Godot 攻击确认 ConfirmBtn"),
    ("GET", "/games/{id}/forecast-attack", "no", "yes", "yes", "actions",
     "攻击目标点击 → 预测(不真攻击):Godot 右侧 '战斗预测'",
     "WebUI 自算;此为服务端权威"),
    ("POST", "/games/{id}/skill", "yes", "yes", "yes", "actions",
     "主动技能:heal/double_strike/snipe;服务端校验 MP 与目标合法性",
     "WASM Skill 按钮"),
    ("POST", "/games/{id}/wait", "yes", "yes", "yes", "actions",
     "待命:关本回合行动权 → 让其他单位行动",
     "Godot WaitBtn"),
    ("POST", "/games/{id}/claim", "yes", "yes", "yes", "actions",
     "占领村落/城堡(2 回合):写 PendingClaim → 翻转 Tile.owner_id",
     "前端显示 '占领进度'"),
    ("POST", "/games/{id}/recruit", "yes", "yes", "yes", "actions",
     "兵营招募:花金币生成新单位",
     "5 兵种;barracks 必须空"),
    ("POST", "/games/{id}/end-turn", "yes", "yes", "yes", "turns",
     "回合手柄:推进 current_player_index;后台调度器在 AI 阶段自动调用",
     "WebUI/Godot EndTurnButton"),
    # editor
    ("GET", "/editor/maps", "yes", "yes", "yes", "editor",
     "编辑器 '读取' 下列出所有自定义地图",
     "进入/保存/删除后刷新"),
    ("GET", "/editor/maps/{id}", "yes", "yes", "yes", "editor",
     "编辑器加载指定地图:返回 layout/biome/size/initial_units/tile_owners",
     "LoadBtn"),
    ("POST", "/editor/maps", "yes", "yes", "yes", "editor",
     "编辑器 '保存':新建或更新地图(id 缺省=新建)",
     "SaveBtn"),
    ("DELETE", "/editor/maps/{id}", "no", "yes", "yes", "editor",
     "编辑器 '删除单图':WebUI 无按钮(P1 接通)",
     "Godot DeleteBtn"),
    # profile
    ("GET", "/profile/{user_name}", "yes", "no", "yes", "profile",
     "玩家档案查询:主线 ensureProfile() GET-404-then-POST 模式",
     "Godot 走 ?user_name= 不调"),
    ("POST", "/profile/{user_name}/mainline/start", "yes", "no", "no", "profile",
     "Profile-keyed 老路径(已废弃):WebUI 直接调",
     "已被 /mainlines/* 取代"),
    ("POST", "/profile/{user_name}/mainline/advance", "yes", "no", "no", "profile",
     "Profile-keyed 老路径(已废弃):推进战役",
     "已被 /mainlines/* 取代"),
    ("POST", "/profile/{user_name}/mainline/abandon", "yes", "no", "no", "profile",
     "Profile-keyed 老路径(已废弃):放弃战役",
     "已被 /mainlines/* 取代"),
    # progression
    ("POST", "/progression/profiles", "yes", "no", "yes", "progression",
     "创建玩家档案:WebUI ensureProfile 用一次",
     "Godot 走 /profile/{name}"),
    ("GET", "/progression/profiles", "no", "no", "yes", "progression",
     "档案列表(分页):仅测试用",
     "前端未接"),
    ("GET", "/progression/profiles/{id}", "no", "no", "yes", "progression",
     "单档案(用于调试/管理):仅测试用",
     "前端未接"),
    ("POST", "/progression/profiles/{id}/units", "no", "no", "yes", "progression",
     "档案中新建单位(英雄/转职):服务端内部路径",
     "主线 /mainlines/{id}/prepare 包装"),
    ("GET", "/progression/profiles/{id}/units", "no", "no", "yes", "progression",
     "档案的单位实例列表:仅测试用",
     "前端未接"),
    ("GET", "/progression/units/{id}", "no", "no", "yes", "progression",
     "单单位实例(战斗内可查询):仅测试用",
     "前端未接"),
    ("POST", "/progression/units/{id}/xp", "no", "no", "yes", "progression",
     "颁奖 XP:服务端战斗胜利结算内部调",
     "前端无显式入口(P2 接通)"),
    ("POST", "/progression/units/{id}/promote", "no", "no", "yes", "progression",
     "兵阶晋升:主线 /mainlines/{id}/prepare/promote 包装",
     "前端未直调"),
    ("DELETE", "/progression/units/{id}", "no", "no", "yes", "progression",
     "删除单位(debug 用):仅测试用",
     "前端未接"),
    # mainline
    ("GET", "/mainlines", "yes", "yes", "yes", "mainline",
     "主线章节列表:渲染章节卡 + 已解锁/当前进度",
     "进 #view-mainline-list"),
    ("GET", "/mainlines/dialogue", "yes", "yes", "yes", "mainline",
     "读剧情 JSON:pre/post/victory 场景;Dialog 引擎渲染",
     "5 场景类型"),
    ("GET", "/mainlines/{id}", "yes", "yes", "yes", "mainline",
     "主线详情:BattlePreview/胜利条件/推荐 CO",
     "进章节前查详情"),
    ("GET", "/mainlines/{id}/prepare", "yes", "yes", "yes", "mainline",
     "战前整备 payload:heroes/roster/inventory/battle_id/win_condition/bgm_meta",
     "6 tab 数据源"),
    ("POST", "/mainlines/{id}/prepare/promote", "yes", "yes", "yes", "mainline",
     "战前转职按钮 → 调 progression/units/{id}/promote",
     "Godot main.gd:6346"),
    ("POST", "/mainlines/{id}/prepare/equipment", "yes", "yes", "yes", "mainline",
     "战前装备/卸下:写单位 inventory",
     "Godot main.gd:6356"),
    ("GET", "/mainlines/{id}/shop", "yes", "yes", "yes", "mainline",
     "战后商店库存:从 profile.unlocked_items 列出",
     "进 #view-mainline-shop"),
    ("POST", "/mainlines/{id}/shop/purchase", "yes", "yes", "yes", "mainline",
     "战后购买:扣金币 + 写 inventory → 返回新余额",
     "_leavePostBattleShop"),
    ("POST", "/mainlines/{id}/prepare/complete", "yes", "no", "yes", "mainline",
     "玩家点 '准备好了' → 写 active_prep + auto_save + 返回 next_battle_id",
     "Godot 实现但 UI 未触发(P0 接通)"),
    ("POST", "/mainlines/{id}/start", "yes", "yes", "yes", "mainline",
     "开始主线战斗:刷出第一章 game_id → 跳 GameView",
     "Godot 含 force=true 重试"),
    ("POST", "/mainlines/{id}/advance", "yes", "yes", "yes", "mainline",
     "战斗胜利推进:结算 → 写 profile + 推 chapter → 返回 next_battle_id",
     "onBattleFinished WS 事件触发"),
    ("POST", "/mainlines/{id}/next-battle", "yes", "yes", "yes", "mainline",
     "刷出下一场战斗(同章节内):刷新 game_id",
     "Godot main.gd:6611"),
    ("POST", "/mainlines/{id}/abandon", "yes", "yes", "yes", "mainline",
     "放弃章节:清理 profile.active_mainline → 跳主菜单",
     "二次确认 modal"),
    ("GET", "/mainlines/{id}/mercenary/config", "no", "yes", "yes", "mainline",
     "佣兵点数配置:从 profile.mercenary_points 读上限",
     "Godot 6-tab Mercenary"),
    ("POST", "/mainlines/{id}/mercenary/allocate", "no", "yes", "yes", "mainline",
     "佣兵点数分配:写分配 → 影响战前 roster 强度",
     "Godot main.gd:6384"),
    # heroes / audio
    ("GET", "/heroes", "yes", "yes", "yes", "heroes",
     "英雄注册表:sprite/portrait/crest URL + 技能列表",
     "启动一次性拉"),
    ("GET", "/audio/tracks", "yes", "yes", "yes", "audio",
     "战役 BGM 目录:进 '创建游戏' 表单时拉 → 曲目下拉",
     "AudioManager 解析"),
    # commanders
    ("GET", "/players/me/commanders", "yes", "yes", "yes", "commanders",
     "已解锁指挥官 + 当前主线 CO:章节列表面板渲染",
     "WebUI/Godot 都用"),
    ("POST", "/mainlines/{id}/select-commander", "yes", "yes", "yes", "commanders",
     "章节指挥官选择(战前):影响 CO meter 阈值和增益",
     "锁定后不可改"),
    ("POST", "/games/{id}/select-commander", "no", "no", "no", "commanders",
     "战内改选强制 409:服务端埋点",
     "实际两端都不调"),
    ("POST", "/games/{id}/co-power", "yes", "yes", "yes", "commanders",
     "发动 CO Power:对所有友军加 atk/def/移动持续 N 回合",
     "WebUI/Godot CO meter 按钮"),
    # save
    ("GET", "/saves", "yes", "yes", "yes", "save",
     "存档列表(5 槽位):3 手动 + 1 自动 + 1 suspend",
     "按 user_name 过滤"),
    ("POST", "/saves/save", "yes", "no", "partial", "save",
     "手动存档(0/1/2 三槽):序列化 GameState → 写 slot JSON",
     "WebUI 有按钮;Godot 包好未触发(P0)"),
    ("POST", "/saves/load", "yes", "yes", "yes", "save",
     "读档:反序列化 → 新建 game_id → 进 GameView",
     "LoadBtn"),
    ("POST", "/saves/load_suspend", "yes", "yes", "yes", "save",
     "读挂起槽:WS 断线触发 → 主菜单 '▶ 继续中断战斗'",
     "LoadSuspendBtn"),
    ("POST", "/saves/erase", "yes", "yes", "yes", "save",
     "清除存档(单槽):存档页 '删除' 按钮",
     "EraseBtn"),
    ("POST", "/games/{id}/suspend", "yes", "no", "partial", "save",
     "主动挂起当前对局:写专有 suspend 槽;WS 断线服务端自动调",
     "Godot capture_suspend 未触发"),
    # WS
    ("WS", "/debug/ws/games/{id}", "no", "no", "yes", "debug",
     "调试事件流(无鉴权):测试工具用",
     "纯调试,两端都不调"),
    ("WS", "/ws/games/{id}", "yes", "yes", "yes", "ws-gateway",
     "正式事件流:server.hello → state.snapshot → event.delta;30s pong;断线自动写 suspend",
     "WS 是战斗中更新主通道;REST GET /state 是兜底"),
]


def build_sheet_matrix(wb: Workbook) -> None:
    ws = wb.create_sheet("接口调用矩阵")
    _sheet_title(ws, "接口调用矩阵 · 全接口 × 三端(W=WebUI / G=Godot / T=Tests/Tools)+ 功能流程作用")

    headers = ["#", "HTTP 方法", "路径", "W", "G", "T", "模块", "功能流程作用", "副作用 / 备注"]
    _row(ws, 2, headers, header=True)

    for i, row in enumerate(MATRIX, start=3):
        method, path, kw, kg, kt, mod, role, note = row

        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT

        c = ws.cell(row=i, column=2, value=method)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        c = ws.cell(row=i, column=3, value=path)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

        _mark(ws.cell(row=i, column=4), _mark_label(kw), kw)
        _mark(ws.cell(row=i, column=5), _mark_label(kg), kg)
        _mark(ws.cell(row=i, column=6), _mark_label(kt), kt)

        c = ws.cell(row=i, column=7, value=mod)
        c.font = BODY_FONT
        c.alignment = CENTER
        c.border = BORDER

        _role(ws, i, 8, role)

        c = ws.cell(row=i, column=9, value=note)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

    _autosize(ws, [5, 7, 50, 6, 6, 6, 12, 50, 38])
    _freeze(ws, "D3")


# ============================================================
# Sheet 4: 功能模块覆盖对比
# ============================================================

def build_sheet_feature_coverage(wb: Workbook) -> None:
    ws = wb.create_sheet("功能模块覆盖")
    _sheet_title(ws, "功能模块覆盖对比 · WebUI vs Godot Client(含功能作用 / 关键端点)")

    headers = ["#", "功能模块", "W", "G", "客户端功能作用", "关键后端端点", "差异说明"]
    _row(ws, 2, headers, header=True)

    features = [
        ("主菜单 / 设置", "yes", "partial",
         "玩家进游戏首屏:resume / 6 个主入口 / 主线优先",
         "GET /games, GET /profile/{name}", "Godot 主菜单 SettingsButton disabled=true"),
        ("设置 · 字号/颜色/主题", "yes", "partial",
         "用户偏好:字号 3 档 + 颜色 4 色 + 主题 3 套;持久化 localStorage",
         "—(纯本地)无后端端点",
         "Godot 4 项存但 SettingsButton disabled"),
        ("设置 · 玩家名(nickname)", "yes", "yes",
         "玩家身份标识,所有 endpoint caller / 存档 owner 都用",
         "GET /profile/{name}, ?user_name= query",
         "Godot 改走 ?user_name= 不用 ensureProfile"),
        ("帮助页 / Reference Panel",
         "yes", "no",
         "玩家查询规则:伤害公式 / 兵种相克 / 反击 / 占领 / CO Power 触发条件",
         "GET /games/units, /games/skills, /games/presets",
         "WebUI 含伤害公式抽屉;Godot 无 Help 按钮触发,死代码"),
        ("创建游戏表单",
         "yes", "yes",
         "玩家首次开房:选 preset/seed/CO/BGM/胜负条件 → 入 room",
         "POST /games",
         "双方齐全;Godot 多 reap 配置 AI 和指挥官"),
        ("加入游戏",
         "yes", "yes",
         "玩家浏览 waiting 房间 → 选 team / role → 入席",
         "GET /games + POST /games/{id}/join",
         "一致;WebUI 多 reach/defend 表单"),
        ("大厅(房主 + AI + 观战)",
         "yes", "yes",
         "房主配置 AI / 切队员 / 观战切换;拉队友聚合决定开始按钮是否可用",
         "GET /games/{id}/state, /lobby;POST /add-ai;DELETE /players/{pid};PATCH /team",
         "基本一致"),
        ("观战 / 转观战",
         "yes", "yes",
         "观战者入席:role=spectator + 不 spawn 单位 + 不参与胜负",
         "DELETE /games/{id}/players/{pid} + POST /games/{id}/join{role:'spectator'}",
         "DELETE + re-JOIN"),
        ("棋盘渲染",
         "yes", "yes",
         "战斗时的核心视图:terrain/unit/HP/MP/士气/acted overlay/浮动文字",
         "GET /games/{id}/state",
         "CSS Grid vs TileMapLayer"),
        ("战斗 7 动作 + CO Power",
         "yes", "yes",
         "回合内玩家所有选项:move/attack/skill/wait/claim/recruit/end-turn/co-power",
         "POST /games/{id}/{move,attack,skill,wait,claim,recruit,end-turn,co-power}",
         "REST 1:1"),
        ("战斗预测(forecast-attack)",
         "no", "yes",
         "攻击目标点击 → 不真攻击的服务端预测伤害展示",
         "GET /games/{id}/forecast-attack",
         "WebUI 自算;Godot 服务端权威"),
        ("WS 实时事件流",
         "yes", "yes",
         "战斗中真实更新通道:服务端 actions 后 push state.snapshot/event.delta",
         "WS /ws/games/{id}?player_id=&since_seq=",
         "WebUI 5-15s 安全网;Godot 25s ping + since_seq 重放"),
        ("存读档(3+1+1)",
         "yes", "partial",
         "玩家随时保存 / 加载当前对局;WE-style 三手动槽 + 自动 + 挂起",
         "GET /saves, POST /saves/{save,load,load_suspend,erase}",
         "WebUI 含手动存档按钮;Godot save_manual 定义未接"),
        ("中断恢复(suspend 续局)",
         "yes", "yes",
         "WS 断线后服务端自动写 suspend 槽 → 主菜单 '▶ 继续中断战斗'",
         "POST /games/{id}/suspend + POST /saves/load_suspend + POST /games/{id}/rejoin_by_name",
         "一致"),
        ("主线章节列表",
         "yes", "yes",
         "玩家选章节:看解锁 / 选 CO / 加载进度",
         "GET /mainlines, GET /players/me/commanders",
         "一致"),
        ("主线战前整备",
         "yes", "yes",
         "战斗前可转职 / 装备 / 选上阵单位 / 调佣兵点数",
         "GET /mainlines/{id}/prepare + POST /mainlines/{id}/prepare/{promote,equipment,allocate}",
         "WebUI 3 tab;Godot 6 tab"),
        ("主线对话(5 场景)",
         "yes", "yes",
         "pre_battle / post_battle / victory 三时机 + 5 场景类型",
         "GET /mainlines/dialogue",
         "WebUI 5 场景类型;Godot 多 choice 选项"),
        ("主线战后推进 / 下一战 / 弃章",
         "yes", "partial",
         "胜利 → 推进 chapter → 下一战或弃章",
         "POST /mainlines/{id}/{advance,next-battle,abandon}",
         "Godot MainlineNextBtn visible=false 未启用"),
        ("主线战前 complete(自动存档)",
         "yes", "no",
         "玩家点 '准备好了' → 写 active_prep + auto_save_checkpoint",
         "POST /mainlines/{id}/prepare/complete",
         "WebUI 调;Godot 实现但 UI 未触发"),
        ("主线商店",
         "yes", "yes",
         "战后买道具:列 shop → 选品 → 扣金币 + 写 inventory",
         "GET /mainlines/{id}/shop + POST /mainlines/{id}/shop/purchase",
         "一致"),
        ("主线指挥官选择 / 已解锁查询",
         "yes", "yes",
         "章节 CO 选择(战前);锁定后不可改",
         "GET /players/me/commanders + POST /mainlines/{id}/select-commander",
         "一致"),
        ("地图编辑器",
         "yes", "yes",
         "玩家自定义地图:画地形 / 放单位 / 配归属 / 保存 / 加载 / 删除",
         "GET/POST/DELETE /editor/maps + POST /games{id}?map_preset=",
         "WebUI 多 fill/line/select 高级工具;Godot 多 tile_owners"),
        ("地图编辑器单图删除",
         "no", "yes",
         "玩家在编辑器列表选图 → 删除",
         "DELETE /editor/maps/{id}",
         "WebUI 无按钮(P1 接通)"),
        ("BGM 选择器 + 播放",
         "yes", "yes",
         "进 '创建游戏' 选曲目 + 进战斗时 AudioManager 播",
         "GET /audio/tracks",
         "Godot 多 M7 crossfade"),
        ("对话框(剧情)",
         "yes", "yes",
         "Dialog 引擎:dialogue/narration/choice/battle_ref/wait 五类型",
         "GET /mainlines/dialogue, GET /heroes",
         "Godot 多 typewriter / choice / 立绘"),
        ("WS 重连 / 心跳",
         "yes", "yes",
         "断线后自动 reconnect + 心跳保活 + since_seq 回放",
         "WS /ws/games/{id}?since_seq=",
         "WebUI 1-30s;Godot 0.5-30s + since_seq"),
        ("AI 评论消费(commentary.text/audio)",
         "yes", "no",
         "战斗 AI 推回评论显示在 chat panel(无发送端点)",
         "WS event.delta[ai_commentary]",
         "WebUI chat-panel;Godot WS 类型 no-op"),
        ("AI 评论发送(玩家)",
         "no", "no",
         "玩家主动发消息 — 后端无对应端点",
         "—",
         "后端无 /chat/..."),
        ("教学引导 Tutorial bubble",
         "yes", "yes",
         "首次进入游戏指导玩家基本操作",
         "—", "双方都本地写死"),
        ("BattleResultPanel + MainlineNextBtn",
         "yes", "partial",
         "战斗结果详细 + 主线下一战按钮触发下一章",
         "POST /mainlines/{id}/next-battle",
         "Godot 节点埋好但 visible=false"),
        ("Lobby 自动轮询(Timer)",
         "yes", "yes",
         "大厅视图每 2s 拉一次 state/lobby 拿最新队友",
         "GET /games/{id}/state", "WebUI setInterval 2s vs Godot Timer 2s"),
        ("Pause 暂停面板",
         "yes", "yes",
         "战斗中按 Esc 暂停 + 选项",
         "WS /ws/games/{id} 断开不影响暂停", "一致"),
        ("Toast(中央上浮)",
         "yes", "no",
         "屏幕中上提示玩家错误 / 信息",
         "—", "WebUI app.js:320-326 toast();Godot 无"),
        ("Settings Reference Drawer",
         "yes", "no",
         "战斗中右下角 ? 抽屉:地形/单位/技能/胜利条件/CO Power",
         "GET /games/units, /games/skills",
         "WebUI 抽屉完整;Godot 缺"),
        ("Commanders 战斗内刷新",
         "yes", "no",
         "战斗中观战模式可看其他玩家 CO meter",
         "GET /players/me/commanders",
         "WebUI 进 view-game 后再刷;Godot 仅 Lobby/Mainline 进入时拉"),
        ("editor 单图 POST 覆盖保存",
         "yes", "yes",
         "编辑器保存:同一 id 覆盖更新;新 id 创建",
         "POST /editor/maps",
         "一致"),
        ("指挥官 thumbnail / 立绘",
         "yes", "yes",
         "玩家 CO 进游戏前选 / 战中显示 sprite + 立绘",
         "GET /heroes",
         "WebUI /ui/assets/heroes/{id}.png + crest;Godot ImageTexture"),
        ("WS 25s 客户端 ping",
         "no", "yes",
         "客户端主动心跳保活 + 协助服务端检测僵尸连接",
         "WS /ws/games/{id} + client.ping",
         "Godot 多客户端 ping(WebUI 只跟服务端 pong)"),
        ("tiles 大版本戳 / 资产 cache-bust",
         "yes", "no",
         "绕过浏览器永久缓存:同文件名 PNG 替换后立刻生效",
         "—(纯本地)",
         "WebUI TILE_ASSET_VERSION ?v="),
        ("suspend 主动挂起",
         "yes", "no",
         "玩家主动退出 → 服务端写挂起槽,稍后能恢复",
         "POST /games/{id}/suspend",
         "WebUI 调;Godot 仅 WS 断线自动"),
        ("/games/{id}/players/{pid}/seat 修改座位",
         "no", "yes",
         "Godot 大厅多 AI 配置文件化要求独立座位",
         "PATCH /games/{id}/players/{pid}/seat",
         "仅 Godot(WebUI 用 team 表达代替)"),
        ("Lobby Remove AI 按钮",
         "yes", "yes",
         "房主移除 AI 玩家(等待阶段)",
         "DELETE /games/{id}/players/{pid}",
         "一致"),
        ("Player chat panel",
         "yes", "no",
         "战斗中显示 AI 推回的 commentary 文字",
         "WS event.delta[ai_commentary]",
         "WebUI 单向显示;Godot no-op"),
        ("Hero hero_id sprite 切换",
         "yes", "yes",
         "当 player_unit.hero_id 有值时显示英雄立绘而非默认 sprite",
         "GET /heroes, UnitOut.hero_id",
         "WebUI /ui/assets/heroes/{hero_id}.png;Godot ImageTexture"),
        ("Progression xp/promote 暴露到 UI",
         "no", "no",
         "P2:把 progression/units/{id}/{xp,promote} 暴露给主线 prepare UI",
         "POST /progression/units/{id}/{xp,promote}",
         "仅测试用;主线 prepare 是独立路径"),
        ("Mainline 头像 portrait 显示",
         "yes", "yes",
         "剧情对话中显示角色立绘:肩膀裁切版本",
         "GET /heroes, GET /mainlines/dialogue",
         "WebUI /ui/assets/portrait_*.png;Godot PortraitLabel"),
        ("编辑器高级工具(fill/line/select)",
         "yes", "no",
         "地图编辑器批量工具:P1 缺口",
         "POST /editor/maps",
         "WebUI 完整;Godot 编辑器 P1 缺口"),
        ("3D / 模型预览",
         "no", "no",
         "后端无对应端点", "—", "未规划"),
    ]

    for i, (mod, kw, kg, role, endpoints, note) in enumerate(features, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        c = ws.cell(row=i, column=2, value=mod)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER
        _mark(ws.cell(row=i, column=3), _mark_label(kw), kw)
        _mark(ws.cell(row=i, column=4), _mark_label(kg), kg)
        _role(ws, i, 5, role)
        c = ws.cell(row=i, column=6, value=endpoints)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER
        c = ws.cell(row=i, column=7, value=note)
        c.font = BODY_FONT
        c.alignment = WRAP
        c.border = BORDER

    _autosize(ws, [5, 38, 6, 6, 50, 50, 45])
    _freeze(ws, "C3")


# ============================================================
# Sheet 5: 差异详解
# ============================================================

def build_sheet_diff(wb: Workbook) -> None:
    ws = wb.create_sheet("差异详解")
    _sheet_title(ws, "差异详解 · WebUI 独有 / Godot Client 独有 / 共享但做法不同(每条标注该接口的功能作用)")

    _row(ws, 2, ["WebUI 独有(只在 WebUI 实现,Godot 缺)"], section=True)
    ws.merge_cells("A2:F2")
    headers = ["#", "功能", "WebUI 锚点", "后端端点", "接口的功能作用", "备注"]
    _row(ws, 3, headers, header=True)

    webui_only = [
        ("Help / Reference Panel(地形/单位/技能/胜利条件/CO Power)",
         "app.js:4692+ + index.html #view-help + 抽屉 #ref-drawer",
         "GET /games/units, /games/skills, /games/presets",
         "玩家查询规则:伤害公式/相克/反击/CO Power 触发条件(阅读型 UI,无状态副作用)",
         "内容详细"),
        ("Toast 系统(中央上浮提示)", "app.js:320-326 toast()", "—",
         "玩家提示信息展示层(纯 UI,与后端无交互)",
         "屏幕中上提示"),
        ("reach/defend 胜利条件表单保留", "index.html:setupWinConditionUI", "POST /games",
         "玩家选 win_condition 时的 UI 字段",
         "后端只支持 rout+seize;UI 保留但不发"),
        ("ensureProfile 并发锁", "app.js:4785+", "GET/POST /profile/{name}",
         "玩家档案创建 / 幂等互斥,避免狂点导致创建多个 profile",
         "Godot 不需要:走 ?user_name= query"),
        ("玩家 Profile 老路径 3 个端点",
         "app.js:4821+", "/profile/{user_name}/mainline/{start,advance,abandon}",
         "WebUI 老的 profile-keyed 主线入口(已被 /mainlines/* 取代,只是后向兼容)",
         "Godot 不调"),
        ("战斗内 chat-panel 显示 WS 推回 AI commentary",
         "app.js:6120+", "WS event.delta[ai_commentary]",
         "AI 评论推送展示(单向,无发送端点)",
         "Godot 消费但 no-op"),
        ("棋子详情 Tooltip 含归属/占领进度",
         "app.js:renderBoard + showTileInfo",
         "GET /games/{id}/state 含 pending_claims + tile.owner_id",
         "悬停鼠标时显示格子详情 + 占领进度",
         "Godot 缺失(P2)"),
        ("WebUI 旧存档 DELETE /games/{id}", "app.js:save-delete handler",
         "DELETE /games/{id}",
         "玩家删除已结束的对局存档(仅 waiting/finished 状态)",
         "WebUI 有按钮;Godot 无"),
        ("Lobby win_condition 通用提示语", "app.js:setupWinConditionUI",
         "CreateGameRequest.win_condition",
         "大厅创建房间时胜利条件表单字段",
         "保留 UI 表单"),
        ("编辑器 select/move/recolor 高级工具",
         "app.js:editorState.fill/line/select",
         "POST /editor/maps",
         "编辑器批量操作工具(也写地图用)",
         "WebUI 完整;Godot P1 缺口"),
    ]
    for i, r in enumerate(webui_only, start=4):
        ws.cell(row=i, column=1, value=str(i - 3)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    start = 4 + len(webui_only) + 1

    ws.merge_cells(start_row=start, start_column=1, end_row=start, end_column=6)
    _row(ws, start, ["Godot Client 独有(只在 Godot 实现,WebUI 缺)"], section=True)
    _row(ws, start + 1, headers, header=True)

    godot_only = [
        ("服务端攻击预测(forecast-attack)", "main.gd:6948",
         "GET /games/{id}/forecast-attack",
         "攻击目标点击 → 服务端不真攻击只算伤害,返回 dmg/crit/counter",
         "WebUI 自算;Godot 服务端权威"),
        ("佣兵配置主线 Tab", "main.gd:5825/6419/6384",
         "GET /mainlines/{id}/mercenary/config + POST /mercenary/allocate",
         "主线战前整备 Tab:玩家分配点数 → 影响战前 roster 强度",
         "WebUI 无此 tab"),
        ("408 重试 + force=true 重试 + 409 auto-abandon-then-restart",
         "main.gd:5839 force=true", "POST /mainlines/{id}/start",
         "主线开始失败的鲁棒路径:服务端报 409 时自动 abandon 再 start",
         "鲁棒性更强;已写进 MEMORY.md"),
        ("since_seq WS 回放机制", "network_client.gd:349",
         "WS /ws/games/{id}?since_seq=",
         "WS 重连时携带最后收到的 seq,服务端从环形缓冲补发漏 event.delta",
         "断线重连回放"),
        ("AI thinking pulse(Tween alpha 0.4↔1.0)",
         "main.gd:1553", "WS event.delta[ai_thinking]",
         "AI 思考中 HUD 闪烁效果(纯前端)",
         "UI 显示 AI 思考中"),
        ("MainlineNextBtn 节点已埋",
         "main.tscn 节点", "POST /mainlines/{id}/next-battle",
         "BattleResultPanel 中:胜利 → 下一战按钮触发同章节内下一场",
         "待 BattleResultPanel 接入主线流程"),
        ("GBA 风三主题(烫金/暗绿/深蓝)",
         "ui/menu_theme.gd + main.gd:2863/2905", "—",
         "玩家切换 UI 主题(纯前端 UI)",
         "WebUI 不切主题"),
        ("25s client.ping 心跳", "network_client.gd:335",
         "WS /ws/games/{id}",
         "客户端主动心跳保活 + 协助服务端检测僵尸连接",
         "客户端主动心跳"),
        ("tile_owners(颜色归属)编辑器支持", "main.gd:editor mode",
         "POST /editor/maps",
         "玩家编辑地图时给地表建筑配归属:开始游戏时按颜色解析到 player_id",
         "WebUI 支持但 Godot 显式三部署模式"),
        ("BattleResultPanel + PausePanel", "main.gd 节点",
         "WS event.delta[match_ended]",
         "战斗结算详细 UI + 暂停面板",
         "战斗结果详细 + 暂停"),
        ("TutorialBubble 一次性触发",
         "main.gd:_trigger_first_tutorial", "—",
         "首次进入教学气泡(纯本地)",
         "首次进入教学"),
        ("动态指令气泡(按单位能力显隐)",
         "main.gd:1249+", "—",
         "战斗 UI 优化:单位行动上下文决定哪些按钮显示(纯 UI,不重算合法性)",
         "移动后语境不同"),
        ("tile 子属性渲染",
         "core/tile_set_builder.gd + core/map_theme.gd", "TileOut.subtype",
         "5 种 castle 子地形视觉与防御加成读取",
         "双方都支持"),
        ("NetworkClient HTTPRequest 串行队列",
         "network_client.gd:106", "—",
         "客户端 HTTP 单连接串行化,避免并发 race(架构层)",
         "一次一个请求"),
        ("Lobby 多 AI 配置文件化",
         "main.gd:4311 多 AI 配置",
         "POST /games/{id}/add-ai × N + PATCH /players/{pid}/seat",
         "玩家一次性加 N 个 AI 玩家(选各自的 seat+personality+difficulty)",
         "WebUI 单 AI 为主"),
        ("Lobby 拖拽座位", "main.gd:4284/4972",
         "PATCH /games/{id}/players/{pid}/seat",
         "玩家拖动 AI 换座位",
         "WebUI 仅下拉"),
        ("Player chat 烟泡 头像 emoji",
         "main.gd:DialogPanel + PortraitLabel",
         "GET /heroes",
         "剧情对话立绘面板(对话时显示)",
         "暂无发送端点"),
        ("tools/ 22 个自动化脚本(smoke + e2e + 截图 + 教程)",
         "tools/*", "—",
         "开发自检 / CI 截图",
         "e2e + screenshot + chapter 验证"),
        ("Player nickname 多端统一",
         "UserSettings.get_user_name()",
         "X-Player-Id + ?user_name=",
         "所有动作用 ?user_name= query,后端按 username 解析为 player_id",
         "Godot 一处入口"),
        ("战斗内 CO meter 多玩家并列",
         "main.gd:_refresh_co_roster",
         "GameStateOut.co_states[]",
         "战斗中为每人显示 CO meter 与激活状态",
         "WebUI 单 CO 为主"),
    ]
    for i, r in enumerate(godot_only, start=start + 2):
        ws.cell(row=i, column=1, value=str(i - (start + 1))).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    start = start + 2 + len(godot_only) + 1

    ws.merge_cells(start_row=start, start_column=1, end_row=start, end_column=6)
    _row(ws, start, ["共享但做法不同(同一功能在两端的实现差异)"], section=True)
    headers3 = ["#", "维度", "WebUI 做法", "Godot 做法", "功能作用", "差异说明"]
    _row(ws, start + 1, headers3, header=True)

    shared_diff = [
        ("会话持久化",
         "localStorage['battleblitz.session.v1']",
         "UserSettings + user://battleblitz.cfg",
         "玩家偏好与对局会话本地化(纯前端)",
         "两端各自;都支持玩家名/字号/颜色"),
        ("WS 心跳机制",
         "30s 服务端 pong + 用户配置秒数安全网",
         "25s 客户端 ping + since_seq 回放",
         "断线重连探测 + 漏事件补发",
         "Godot 双向 + 回放"),
        ("REST 兜底轮询",
         "WS 在线 5-15s + WS 断线 400ms",
         "WS 后 200ms debounce 主动 GET /state",
         "WS 漏事件兜底,确保客户端追上服务端状态",
         "WebUI 在 WS 断线时加速;Godot 主动 GET"),
        ("棋盘渲染",
         "CSS Grid 自适应容器 + DOM 节点 + 浮动文字",
         "TileMapLayer 三层 + UnitNode 单组件",
         "战斗时 grid 渲染 + 单位 sprite + 反馈(完全两套实现)",
         "等效 UI"),
        ("移动动画",
         "CSS transition", "Tween TRANS_CUBIC 0.32s",
         "玩家点格子 → 单位平滑位移(纯前端)",
         "Godot 略精准可控制"),
        ("伤害浮动文字",
         "DOM 节点 + CSS animation",
         "_process spawn + Tween 上浮 60px + 0.8s fade",
         "战斗反馈:伤害数字 / 治疗 / 暴击 / 升级",
         "等效 UI"),
        ("单位样式",
         "sprite + DOM styled div",
         "sprite + ImageTexture + HP/MP/士气/acted 多层 overlay",
         "单位渲染(HP/MP/士气/已行动 等状态可见)",
         "等效 UI"),
        ("视图切换",
         "showView(name) + section show/hide",
         "_show_view(name) + Control visible",
         "玩家点主菜单切换页面(纯前端)",
         "Godot 用信号集中监听"),
        ("Bgm 渐入",
         "AudioManager.applyBattleConfig",
         "AudioManager.apply_battle_bgm() crossfade M7",
         "进战斗时 BGM 平滑切换(纯前端音频)",
         "Godot 多 crossfade"),
        ("存档体系",
         "全部 5 端点 + 旧存档 DELETE /games/{id}",
         "全 5 端点;手动存档按钮缺",
         "玩家随时保存 / 加载当前对局",
         "WebUI 多手动存档 UI"),
        ("编辑器",
         "9 地形 + 5 单位 + 高级工具(fill/line/select) + undo",
         "3 部署模式 + 50 步 undo + tile_owners + delete",
         "玩家自定义地图与保存到服务端",
         "部分差异互补"),
        ("WS 客户端重连",
         "1-30s 指数退避",
         "0.5-30s 指数退避 + since_seq 回放",
         "断线后自动重连 + 漏事件补发",
         "Godot 重连恢复数据更强"),
        ("剧情五场景类型",
         "Dialog.play 五类型",
         "DialogPanel + choice 选项 + typewriter",
         "剧情播放:5 类型场景 + 立绘 + 选项",
         "WebUI 五类型"),
        ("攻击确认",
         "DOM modal + 自算 forecast",
         "AttackConfirmPanel + 服务端 forecast 调用",
         "玩家点攻击目标 → 确认前看伤害数字",
         "Godot 引入服务端权威,WebUI 自算"),
        ("战斗结果/结算",
         "WebUI + MainlineNextBtn (在面板上)",
         "BattleResultPanel + MainlineNextBtn visible=false",
         "战斗结束 → 玩家点后续按钮(下一战/再战/退出)",
         "Godot 节点埋好未启用"),
    ]
    for i, r in enumerate(shared_diff, start=start + 2):
        ws.cell(row=i, column=1, value=str(i - (start + 1))).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 45, 38, 38, 50, 35])
    _freeze(ws, "A3")


# ============================================================
# Sheet 6: 未调用接口清单(每条接口附设计意图 + 功能作用)
# ============================================================

def build_sheet_uncalled(wb: Workbook) -> None:
    ws = wb.create_sheet("未调用接口清单")
    _sheet_title(ws, "未调用接口清单 · 后端存在但无客户端调用的接口 + 原本设计的功能作用")

    ws.merge_cells("A2:G2")
    _row(ws, 2, ["A. 两端都不调(仅测试 / 调试)"], section=True)
    headers = ["#", "HTTP 方法", "路径", "模块", "原设计功能作用", "实际使用者", "备注"]
    _row(ws, 3, headers, header=True)

    a = [
        ("GET", "/healthz", "meta",
         "容器 / 运维探针:确认服务存活",
         "tests/ + 容器", "前端代码不消费"),
        ("GET", "/progression/profiles", "progression",
         "列出所有玩家档案(分页,管理面板用)",
         "tests/", "前端未接;如需 → 后台管理 UI"),
        ("GET", "/progression/profiles/{id}", "progression",
         "按 id 查单个档案(战斗内查对手)",
         "tests/", "前端未接"),
        ("POST", "/progression/profiles/{id}/units", "progression",
         "档案中新建单位:主线 prepare / 商店购买的内部路径",
         "tests/ + 服务端内部(mainline.prepare 包装)",
         "前端未直调,但实际 UI 数据流走的这条"),
        ("GET", "/progression/profiles/{id}/units", "progression",
         "档案的单位实例列表(展示 profile 拥有的英雄)",
         "tests/", "前端未接"),
        ("GET", "/progression/units/{id}", "progression",
         "单单位实例(战斗中查升级路径)",
         "tests/", "前端未接"),
        ("POST", "/progression/units/{id}/xp", "progression",
         "为单位颁奖 XP:战斗胜利结算时服务端内部调",
         "tests/ + 服务端内部(mainline.advance 包装)",
         "前端无显式入口(P2 接通)"),
        ("POST", "/progression/units/{id}/promote", "progression",
         "兵阶晋升:低级→高级兵种",
         "tests/ + 服务端内部(mainline.prepare/promote 包装)",
         "前端未直调,但 prepare/promote UI 已接"),
        ("DELETE", "/progression/units/{id}", "progression",
         "删除单位(管理员 debug)",
         "tests/", "debug 端点"),
        ("POST", "/games/{id}/select-commander", "commanders",
         "战内改 CO(强制 409:已锁定)", "无",
         "两端都不调;服务端埋点保护;前端已用 commander locked UI 提示"),
        ("WS", "/debug/ws/games/{id}", "debug",
         "调试事件流(无鉴权):测试工具拉所有 event.delta", "tests/ + tools",
         "纯调试;无客户端消费"),
    ]
    for i, r in enumerate(a, start=4):
        ws.cell(row=i, column=1, value=str(i - 3)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    start = 4 + len(a) + 1

    ws.merge_cells(start_row=start, start_column=1, end_row=start, end_column=7)
    _row(ws, start, ["B. 仅 WebUI 调(Godot 不调 / 定义但 UI 未接)"], section=True)
    _row(ws, start + 1, headers, header=True)

    b = [
        ("GET", "/profile/{user_name}", "profile",
         "查询玩家档案:主线 ensureProfile() GET-404-then-POST 模式",
         "WebUI",
         "Godot 走 ?user_name= query,不调此端点"),
        ("POST", "/profile/{user_name}/mainline/start", "profile",
         "Profile-keyed 老路径(已废弃):开始战役",
         "WebUI", "已被 /mainlines/* 取代,Godot 走新路径"),
        ("POST", "/profile/{user_name}/mainline/advance", "profile",
         "Profile-keyed 老路径(已废弃):推进战役",
         "WebUI", "已被 /mainlines/* 取代"),
        ("POST", "/profile/{user_name}/mainline/abandon", "profile",
         "Profile-keyed 老路径(已废弃):放弃战役",
         "WebUI", "已被 /mainlines/* 取代"),
        ("POST", "/mainlines/{id}/prepare/complete", "mainline",
         "玩家点 '准备好了':写 active_prep + auto_save + 启下一战",
         "WebUI",
         "Godot 实现但 UI 未触发(P0 接通)"),
        ("POST", "/games/{id}/suspend", "save",
         "主动挂起当前对局:写专有 suspend 槽",
         "WebUI + 服务端 WS 断线自动",
         "Godot capture_suspend 定义未触发"),
        ("DELETE", "/games/{id}", "game",
         "删除对局存档(等待/结束态):旧存档删除按钮",
         "WebUI",
         "Godot 仅 smoke_test 校验存在"),
        ("GET", "/games/{id}/lobby", "game",
         "大厅轮询拿队伍聚合(teams[])",
         "WebUI",
         "Godot 改用 /state 解析"),
    ]
    for i, r in enumerate(b, start=start + 2):
        ws.cell(row=i, column=1, value=str(i - (start + 1))).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    start = start + 2 + len(b) + 1

    ws.merge_cells(start_row=start, start_column=1, end_row=start, end_column=7)
    _row(ws, start, ["C. 仅 Godot 调(WebUI 不调 / 自算)"], section=True)
    _row(ws, start + 1, headers, header=True)

    c = [
        ("GET", "/games/{id}/forecast-attack", "actions",
         "攻击目标点击 → 服务端预测(不真攻击)",
         "Godot main.gd:6948",
         "WebUI 自算;Godot 用服务端权威"),
        ("PATCH", "/games/{id}/players/{pid}/seat", "game",
         "改座位:Godot 大厅拖拽座位 + 多 AI 配置文件化",
         "Godot main.gd:4284/4972",
         "WebUI 用 team 表达代替"),
        ("GET", "/mainlines/{id}/mercenary/config", "mainline",
         "佣兵点数配置:从 profile.mercenary_points 读上限",
         "Godot main.gd:5825/6419",
         "WebUI 无佣兵 tab"),
        ("POST", "/mainlines/{id}/mercenary/allocate", "mainline",
         "佣兵点数分配:写分配 → 影响战前 roster 强度",
         "Godot main.gd:6384",
         "WebUI 无佣兵 tab"),
    ]
    for i, r in enumerate(c, start=start + 2):
        ws.cell(row=i, column=1, value=str(i - (start + 1))).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 7, 50, 16, 50, 35, 35])
    _freeze(ws, "A3")


# ============================================================
# Sheet 7: 死代码清单
# ============================================================

def build_sheet_deadcode(wb: Workbook) -> None:
    ws = wb.create_sheet("死代码清单")
    _sheet_title(ws, "死代码 / 未连接按钮 / 未用资产(含对应接口原本的功能作用)")

    headers = ["#", "类型", "项目", "锚点", "对应接口原本的功能作用", "说明"]
    _row(ws, 2, headers, header=True)

    items = [
        ("未连接表单 / 表单残留", "WebUI",
         "app.js:setupWinConditionUI", "—",
         "胜利条件表单;reach_tile + defend_turns 已停用,后端只支持 rout+seize"),
        ("编辑器缺删除按钮", "WebUI",
         "app.js:editorState", "DELETE /editor/maps/{id}",
         "玩家删除自定义地图",
         "只能 POST 覆盖;P1 接通"),
        ("Tile/资产 cache-bust", "WebUI",
         "index.html + app.js:TILE_ASSET_VERSION", "—",
         "绕过浏览器永久缓存",
         "TILE_ASSET_VERSION = '2026-07-03-p24-snow-peak' 绕过 Chrome 永久缓存"),
        ("NetworkClient 包装方法", "Godot",
         "network_client.gd:464 delete_game", "DELETE /games/{id}",
         "玩家删除已结束的对局存档", "仅 smoke_test 校验存在,UI 未触发"),
        ("NetworkClient 包装方法", "Godot",
         "network_client.gd:get_lobby", "GET /games/{id}/lobby",
         "大厅轮询拿队伍聚合", "定义存在;UI 改用 /state 解析"),
        ("NetworkClient 包装方法", "Godot",
         "network_client.gd:save_manual", "POST /saves/save",
         "玩家主动写存档到三槽之一", "定义存在;手动存档按钮未接"),
        ("NetworkClient 包装方法", "Godot",
         "network_client.gd:capture_suspend", "POST /games/{id}/suspend",
         "玩家主动挂起当前对局", "主动挂起未接;WS 断线服务端自动写"),
        ("NetworkClient 包装方法", "Godot",
         "network_client.gd:complete_mainline_prepare", "POST /mainlines/{id}/prepare/complete",
         "主线整备完成,启自动存档与下一战", "主线 '准备好了' 按钮未接"),
        ("NetworkClient 死包装", "Godot",
         "network_client.gd:380-386 ws_connect(raw_url) / ws_send(type, payload)",
         "WS /ws/games/{id} client.action.*",
         "未来可能用 WS 推玩家动作", "网关不消费 client.action.*;所有动作走 REST"),
        ("主菜单死按钮", "Godot",
         "main.tscn: JoinByCodeButton",
         "POST /games/{id}/join(按邀请码)",
         "玩家用邀请码加入房间",
         "disabled=true,无 handler"),
        ("主菜单死按钮", "Godot",
         "main.tscn: SettingsButton",
         "—", "玩家切换偏好设置",
         "disabled=true,走 in-game SettingsPanel"),
        ("函数在未 connect", "Godot",
         "main.gd:1797 _on_toggle_mute_pressed",
         "—", "玩家切静音",
         "_ready 未 connect 任何按钮,不可触达"),
        ("Help 触发按钮", "Godot",
         "main.gd:1831/1890 show_help/hide_help",
         "GET /games/units, /games/skills, /games/presets",
         "玩家查询游戏规则(伤害公式/相克)",
         "main.tscn 无 HelpButton;Panel 运行时 Panel.new() 加入 root;死代码"),
        ("BattleResultPanel 死节点", "Godot",
         "main.tscn: BattleResultPanel/ResultBtnRow/MainlineNextBtn",
         "POST /mainlines/{id}/next-battle",
         "主线胜利后跳下一战",
         "visible=false;无调用方传 mainline_next=true"),
        ("EditorSurfaceOption 重复节点", "Godot",
         "main.tscn 行 323 与 374",
         "POST /editor/maps",
         "编辑器地表所有方选项(城堡/村/兵营/城门)",
         "重复声明,只有后者 @onready 引用;场景 bug"),
        ("_start_quick_ai_game 死包装", "Godot",
         "main.gd:826 / network_client.gd:826",
         "POST /games + join + add-ai + start",
         "开发自检快速开 AI 对局",
         "唯一绕过 typed wrapper 直接调 NetworkClient.request 的地方"),
        ("WS 类型 no-op", "Godot",
         "network_client.gd:_dispatch_ws_message",
         "WS event.commentary.text / event.commentary.audio",
         "战斗中显示 AI 评论(WS 推送)",
         "AI 评论 WS 类型已分发但 Godot no-op 未接战报"),
        ("turn.advance", "Godot",
         "network_client.gd", "WS /ws/games/{id}",
         "回合推进",
         "已转发但 UI 未单独订阅,主要靠 state.snapshot 触发"),
        ("后端内部 helper(不挂路由)", "后端",
         "save.py:auto_save_checkpoint(...)",
         "—", "内部调:写自动存档到 slot 1",
         "mainline 在 /advance 与 /prepare/complete 时调用;不直接对外"),
        ("Lobby 通用提示语", "WebUI",
         "app.js:setupWinConditionUI",
         "POST /games (CreateGameRequest.win_condition)",
         "玩家选胜利条件",
         "通用 '占领 HQ 或消灭' 标语保留显示"),
        ("编辑器高级工具缺口", "WebUI",
         "app.js:editorState fill/line/select",
         "POST /editor/maps",
         "编辑器批量操作工具",
         "WebUI 完整;Godot 编辑器 P1 缺口"),
        ("Tiles 死资源", "WebUI / Godot",
         "game/app/web/assets/tiles/*",
         "GET /games/presets + TileOut.terrain/subtype",
         "渲染地形 PNG",
         "需逐张检查被 sprites 引用的 PNG"),
        ("玩家登录/注册/找回", "WebUI / Godot",
         "ensureProfile() 用 prompt 弹昵称",
         "GET/POST /profile/{name} 仅当 registry 用",
         "无登录 / 找回端点",
         "后端无对应 endpoint;产品未规划"),
        ("AI 玩家发消息(chat 发送)", "WebUI / Godot",
         "WS event.delta[ai_commentary] 仅消费",
         "—", "玩家发消息到当前房间",
         "后端无 /chat/... 端点"),
        ("replay scrubber", "—", "—", "—",
         "回放对局", "后端无;未规划"),
        ("3D 预览 / 模型预览", "—", "—", "—",
         "单位 3D 模型预览", "后端无;未规划"),
    ]

    for i, r in enumerate(items, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 30, 12, 45, 50, 45])
    _freeze(ws, "A3")


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    wb = Workbook()
    wb.remove(wb.active)

    build_sheet_overview(wb)
    build_sheet_backend(wb)
    build_sheet_matrix(wb)
    build_sheet_feature_coverage(wb)
    build_sheet_diff(wb)
    build_sheet_uncalled(wb)
    build_sheet_deadcode(wb)

    out = Path(__file__).parent / "三方对比与接口覆盖分析报告.xlsx"
    wb.save(str(out))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
