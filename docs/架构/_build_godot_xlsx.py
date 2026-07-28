"""
生成 BattleBlitz Godot 客户端功能调查报告 .xlsx
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


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
DEAD_FILL = PatternFill("solid", fgColor="FFE4E6")
DEAD_FONT = Font(name="Microsoft YaHei", size=10, color="9F1239", bold=True)
BUG_FILL = PatternFill("solid", fgColor="FEF3C7")
BUG_FONT = Font(name="Microsoft YaHei", size=10, color="92400E", bold=True)

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
    if kind in ("yes", "partial", "no", "na", "dead", "bug"):
        cell.alignment = CENTER
    if kind == "yes":
        cell.fill = YES_FILL
        cell.font = YES_FONT
    elif kind == "partial":
        cell.fill = PARTIAL_FILL
        cell.font = PARTIAL_FONT
    elif kind == "no":
        cell.fill = NO_FILL
        cell.font = NO_FONT
    elif kind == "na":
        cell.fill = NA_FILL
        cell.font = NA_FONT
    elif kind == "dead":
        cell.fill = DEAD_FILL
        cell.font = DEAD_FONT
    elif kind == "bug":
        cell.fill = BUG_FILL
        cell.font = BUG_FONT


def _mark_label(kind: str) -> str:
    return {
        "yes": "✅",
        "partial": "△",
        "no": "❌",
        "na": "—",
        "dead": "💀",
        "bug": "🐞",
    }.get(kind, "")


def _row(ws, row, values, header=False, section=False):
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
        else:
            c.font = BODY_FONT


def _autosize(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _freeze(ws, cell="B2"):
    ws.freeze_panes = cell


def _title(ws, title, span=26):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    c = ws.cell(row=1, column=1, value=title)
    c.fill = TITLE_FILL
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30


def _role(ws, row, col, text):
    c = ws.cell(row=row, column=col, value=text)
    c.font = ROLE_FONT
    c.alignment = WRAP
    c.border = BORDER
    c.fill = ROLE_FILL


# ============================================================
# Sheet 1: 项目概览
# ============================================================

def build_sheet_overview(wb):
    ws = wb.create_sheet("项目概览", 0)
    _title(ws, "BattleBlitz Godot 客户端 · 项目概览(2026-07-21)")

    _row(ws, 2, ["维度", "数值 / 内容", "锚点 / 文件"], header=True)
    rows = [
        ["主场景", "scenes/main.tscn,2048 行,所有视图都是其子 Control", "scenes/main.tscn"],
        ["棋盘场景", "scenes/board.tscn,899B,被 GameView + EditorView 各实例化 1 次", "scenes/board.tscn"],
        ["主控脚本", "scripts/main.gd,7372 行,**几乎所有视图逻辑都内联在同一类**", "scripts/main.gd"],
        ["Autoload 单例", "Config / UserSettings / GameState / InputState / NetworkClient / AudioManager",
         "scripts/autoload/*.gd"],
        ["tools/ 脚本", "26 个:1 smoke + 5 e2e + 17 截图 + 2 辅助 + 2 启动", "tools/"],
        ["资产", "70 tiles + 6 classic + 5 hero portrait/crest + 2 BGM = 83 PNG",
         "assets/{tiles,classic,heroes,audio}/"],
        ["网络通讯", "HTTPRequest 串行队列 + WS 25s ping + 0.5-30s 重连 + since_seq 回放",
         "network_client.gd:106-180"],
        ["NetworkClient API", "约 50 个 typed methods(7 类 REST + 6 存档 + 18 主线 + WS)",
         "network_client.gd:391-714"],
        ["GameState 信号", "27 个 typed signals(7 snapshot-level + 18 event-delta + 2 connection)",
         "game_state.gd:20-47"],
        ["地图尺寸支持", "任意 15-45 + {width, height} 非方形",
         "map_metrics.gd:11-21"],
        ["TileSet", "当前走 legacy per-terrain(`USE_FE8_ATLAS=false`),FE8 master atlas 预留",
         "tile_set_builder.gd:54-97"],
        ["自动化测试", "smoke_test 269 断言 + chapter_06_* 3 工具 + e2e_one_game + ws_e2e.py",
         "tools/*.gd"],
        ["测试覆盖", "约 **72-78%** 可玩流程加权综合", "smoke_test.gd"],
        ["Bug 标记", "`gs.set(\"is_connected\")` 字段名错(应 `ws_connected`)",
         "network_client.gd:95-96"],
        ["InputState", "M2 占位 — 3 signals 定义但 0 个 connect", "input_state.gd:11-13"],
        ["回调签名铁律", "callback 必须 `(body, code)` 2 参(MEMORY.md)",
         "callback-signature-match.md"],
        ["autoload 顺序陷阱", "GameState._ready 留空,wiring 让 NetworkClient._ready 做",
         "autoload-order-ws-wiring.md"],
        ["服务端 WS 缺口", "end_turn / 回合 / 对局结束不发 WS,客户端靠 REST GET /state",
         "server-ws-events-gap.md"],
        ["服务端权威", "所有玩家动作 POST REST,客户端不重算 damage / 战斗规则",
         "server-authority-no-duplicate-logic.md"],
    ]
    for i, r in enumerate(rows, start=3):
        _row(ws, i, r)

    _autosize(ws, [22, 50, 32])
    _freeze(ws, "A3")


# ============================================================
# Sheet 2: autoload 信号
# ============================================================

def build_sheet_autoloads(wb):
    ws = wb.create_sheet("autoload 与信号")
    _title(ws, "6 个 Autoload × 全部 typed signals + 主要字段 + 触发时机")

    headers = ["#", "Autoload", "类型", "名称 / 信号", "Payload", "触发场景", "锚点"]
    _row(ws, 2, headers, header=True)

    rows = [
        # Config
        ("Config", "镜像常量", "TERRAIN_MOVE_COST/DEF_BONUS/RECRUIT_COST/MORALE_MAX/BASE_CRIT_RATE/COUNTER_DAMAGE_MULT/CLAIM_TURNS_REQUIRED",
         "Dictionary / int / float", "全局 UI 镜像,服务端权威", "config.gd:13-217"),
        ("Config", "helpers", "is_passable / pick_tile_variant / tile_asset_basename / player_color / has_castle_subtype",
         "—", "全局调用", "config.gd:226-264"),
        # UserSettings
        ("UserSettings", "持久化文件", "user://battleblitz.cfg", "ConfigFile",
         "退出时写盘,启动时 _load() 读盘", "user_settings.gd:12"),
        ("UserSettings", "getter", "get_value / set_value / get_api_base / get_ws_base", "Variant/String",
         "其他模块订阅", "user_settings.gd:40-62"),
        # GameState
        ("GameState", "field", "latest_snapshot / game_summary / tiles / players / logs / co_states / pending_claims / phase / local_player_id",
         "Dictionary/Array/String/int", "NetworkClient._on_state_snapshot 全替换", "game_state.gd:51-62"),
        ("GameState", "signal", "snapshot_received(snapshot)", "Dict", "每次 WS state.snapshot", "game_state.gd:20"),
        ("GameState", "signal", "state_updated(snapshot)", "Dict", "同上", "game_state.gd:21"),
        ("GameState", "signal", "tile_state_changed(x,y,new)", "int,int,Dict", "tile diff 派发", "game_state.gd:22"),
        ("GameState", "signal", "units_changed(units[])", "Array", "units flat 派发", "game_state.gd:23"),
        ("GameState", "signal", "unit_acted(id,has_acted,has_moved)", "int,bool,bool", "—", "game_state.gd:24"),
        ("GameState", "signal", "current_player_changed(pid)", "Variant", "—", "game_state.gd:25"),
        ("GameState", "signal", "phase_changed(phase)", "String", "is_local_turn setter 触发", "game_state.gd:26"),
        ("GameState", "signal", "connection_state_changed(connected)", "bool", "ws_connected setter 触发", "game_state.gd:27"),
        ("GameState", "signal", "log_received(action)", "Dict", "每个 event.delta", "game_state.gd:30"),
        ("GameState", "signal", "unit_moved(id,from_x,from_y,to_x,to_y,cost)",
         "int,int,int,int,int,int", "WS event.delta.move", "game_state.gd:31"),
        ("GameState", "signal", "unit_attacked(a,t,dmg,is_crit,is_kill)",
         "int,int,int,bool,bool", "WS event.delta.attack", "game_state.gd:32"),
        ("GameState", "signal", "unit_killed(id,killer)", "int,int", "WS event.delta.kill", "game_state.gd:33"),
        ("GameState", "signal", "unit_leveled_up(id,level)", "int,int", "—", "game_state.gd:34"),
        ("GameState", "signal", "unit_waited(id)", "int", "—", "game_state.gd:35"),
        ("GameState", "signal", "unit_used_skill(id,skill,target,hp)",
         "int,String,int,int", "—", "game_state.gd:36"),
        ("GameState", "signal", "unit_claimed(id,x,y,completed,owner)",
         "int,int,int,bool,int", "—", "game_state.gd:37"),
        ("GameState", "signal", "unit_recruited(id,type,x,y,cost)",
         "int,String,int,int,int", "—", "game_state.gd:38"),
        ("GameState", "signal", "turn_ended(next_pid,turn_n)", "Variant,int", "WS event.delta.turn_ended",
         "game_state.gd:39"),
        ("GameState", "signal", "round_started(turn_n)", "int", "—", "game_state.gd:40"),
        ("GameState", "signal", "match_started()", "—", "—", "game_state.gd:41"),
        ("GameState", "signal", "match_ended(winner,reason)", "Variant,String", "WS event.delta.match_ended",
         "game_state.gd:42"),
        ("GameState", "signal", "castle_captured(x,y,owner)", "int,int,int", "—", "game_state.gd:43"),
        ("GameState", "signal", "ai_thinking(thinking)", "bool", "AI 阶段入口/出口", "game_state.gd:44"),
        ("GameState", "signal", "low_hp_warning(id,hp,max)", "int,int,int", "—", "game_state.gd:45"),
        ("GameState", "signal", "comeback(pid)", "int", "—", "game_state.gd:46"),
        ("GameState", "signal", "victory_imminent(pid)", "int", "—", "game_state.gd:47"),
        # InputState
        ("InputState", "mode enum", "IDLE/UNIT_SELECTED/MOVE_MODE/ATTACK_MODE/CLAIM_MODE/RECRUIT_MODE/SKILL_MODE",
         "int", "—", "input_state.gd:16-24"),
        ("InputState", "field+signal", "mode + mode_changed(new)", "int", "Board.click handler 写入 (M2 计划)",
         "input_state.gd:26-31"),
        ("InputState", "field+signal", "selected_unit_id + selected_unit_changed",
         "Variant", "—", "input_state.gd:33-36"),
        ("InputState", "field+signal", "hover_tile + hover_tile_changed", "Vector2i", "—",
         "input_state.gd:38-41"),
        # NetworkClient
        ("NetworkClient", "signal", "api_response(method,path,body,code)", "4 元",
         "HTTP 2xx", "network_client.gd:26"),
        ("NetworkClient", "signal", "api_error(method,path,error,code)", "4 元",
         "HTTP 失败/4xx/5xx", "network_client.gd:27"),
        ("NetworkClient", "signal", "ws_connecting / ws_connected / ws_disconnected / ws_reconnecting",
         "—/—/String/(int,float)", "WS 状态机", "network_client.gd:29-32"),
        ("NetworkClient", "signal", "ws_message_received(message)", "Dict", "任意包解析前",
         "network_client.gd:35"),
        ("NetworkClient", "signal", "server_hello_received(seq,payload)", "int,Dict",
         "WS server.hello", "network_client.gd:38"),
        ("NetworkClient", "signal", "state_snapshot_received(game)", "Dict",
         "WS state.snapshot", "network_client.gd:39"),
        ("NetworkClient", "signal", "event_delta_received(event)", "Dict",
         "WS event.delta / turn.advance", "network_client.gd:40"),
        ("NetworkClient", "signal", "server_pong_received(echo_at_ms)", "int",
         "WS server.pong", "network_client.gd:41"),
        ("NetworkClient", "signal", "protocol_error_received(code,msg)", "String,String",
         "WS error frame", "network_client.gd:42"),
        # AudioManager
        ("AudioManager", "API", "apply_battle_bgm / crossfade_to / load_track / set_muted / toggle_muted / set_volume / is_muted",
         "—", "主控调(入战斗 / 静音 toggle / 音量)", "audio_manager.gd"),
        ("AudioManager", "trigger", "apply_battle_bgm(battle_config.audio.bgm)",
         "—", "main.gd:1253 进战斗 polling 触发", "audio_manager.gd:66-80"),
        ("AudioManager", "trigger", "set_muted / toggle_muted", "—",
         "main.gd:511 / 1799(后者无 connect — 死按钮)", "audio_manager.gd:138-159"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 18, 12, 50, 28, 28, 25])
    _freeze(ws, "B3")


# ============================================================
# Sheet 3: NetworkClient REST API
# ============================================================

def build_sheet_rest(wb):
    ws = wb.create_sheet("NetworkClient REST")
    _title(ws, "NetworkClient 全部 typed methods(HTTP path / body / callback / 调用位置 / 状态)")

    headers = ["#", "方法名", "HTTP", "路径", "Body 字段", "Callback 签名", "调用位置", "状态"]
    _row(ws, 2, headers, header=True)

    rows = [
        # 战斗动作
        ("action_move", "POST", "/games/{id}/move", "{player_id,unit_id,to_x,to_y}", "(body,code)",
         "main.gd:2255 _move_unit_to", "live"),
        ("action_attack", "POST", "/games/{id}/attack", "{player_id,attacker_id,target_id}",
         "(body,code)", "main.gd:7075 攻击确认 ConfirmBtn", "live"),
        ("forecast_attack", "GET", "/games/{id}/forecast-attack",
         "query:player_id,attacker_id,target_id", "(body,code)", "main.gd:6948 攻击目标点击",
         "live"),
        ("action_skill", "POST", "/games/{id}/skill", "{player_id,unit_id,skill,target_id?}",
         "(body,code)", "main.gd:7333 技能目标点击", "live"),
        ("action_wait", "POST", "/games/{id}/wait", "{player_id,unit_id}", "(body,code)",
         "main.gd:7342 WaitBtn", "live"),
        ("action_claim", "POST", "/games/{id}/claim", "{player_id,unit_id}", "(body,code)",
         "main.gd:7356 ClaimBtn", "live"),
        ("action_recruit", "POST", "/games/{id}/recruit",
         "{player_id,tile_x,tile_y,unit_type}", "(body,code)", "main.gd:7200 RecruitPanel 兵种按钮",
         "live"),
        ("action_end_turn", "POST", "/games/{id}/end-turn", "{player_id}", "(body,code)",
         "main.gd:2019 EndTurnButton / e2e_one_game:192", "live"),
        ("action_co_power", "POST", "/games/{id}/co-power", "{player_id}", "(body,code)",
         "main.gd:1747 CO Power 按钮", "live"),
        # 大厅 / 通用
        ("list_presets", "GET", "/games/presets", "—", "—",
         "main.gd:4566 Lobby 地图预设下拉", "live"),
        ("list_editor_maps", "GET", "/editor/maps", "—", "—",
         "main.gd:3122/3873/3887 进入/保存/删除后刷新", "live"),
        ("load_editor_map", "GET", "/editor/maps/{id}", "—", "—",
         "main.gd:3730 LoadBtn", "live"),
        ("save_editor_map", "POST", "/editor/maps", "CustomMapSave", "—",
         "main.gd:3757 SaveBtn", "live"),
        ("delete_editor_map", "DELETE", "/editor/maps/{id}", "—", "—",
         "main.gd:3740 DeleteBtn", "live"),
        ("list_games", "GET", "/games[?user_name]", "—", "—",
         "main.gd:941 主菜单恢复;5015 房间列表刷新", "live"),
        ("delete_game", "DELETE", "/games/{id}", "—", "—",
         "network_client.gd:464(未在 UI 触发)", "未触发"),
        ("create_game", "POST", "/games",
         "{name,map_preset,map_biome,win_condition,battle_config{...}}", "—",
         "main.gd:858 Dev-AI / 5104 Lobby 创建", "live"),
        ("get_game_state", "GET", "/games/{id}/state", "—", "—",
         "main.gd 10 处轮询;e2e_one_game:177", "live"),
        ("join_game", "POST", "/games/{id}/join", "{user_name,color,team,role,seat}", "—",
         "main.gd 6 处;e2e_one_game:91", "live"),
        ("start_game", "POST", "/games/{id}/start", "—", "—",
         "main.gd:838/894/4329/5444", "live"),
        ("add_ai_player", "POST", "/games/{id}/add-ai", "{difficulty,agent_kind,personality}", "—",
         "main.gd:890/4222/4268/5265", "live"),
        ("remove_player", "DELETE", "/games/{id}/players/{pid}", "—", "—",
         "main.gd:5284 移 AI / 5429 转观战", "live"),
        ("update_player_team", "PATCH", "/games/{id}/players/{pid}/team",
         "{caller_player_id,team}", "—",
         "main.gd:5299 玩家;5405 host;4311 多 AI 流", "live"),
        ("update_player_seat", "PATCH", "/games/{id}/players/{pid}/seat",
         "{caller_player_id,seat}", "—",
         "main.gd:4284/4972 Seat 拖拽 + 下拉", "live"),
        ("get_lobby", "GET", "/games/{id}/lobby", "—", "—",
         "network_client.gd:542(未在 UI 触发)", "未触发"),
        ("rejoin_game_by_player_id", "POST", "/games/{id}/rejoin", "{player_id}", "—",
         "main.gd:968 按 id 续局", "live"),
        ("rejoin_game_by_name", "POST", "/games/{id}/rejoin_by_name", "{user_name}", "—",
         "main.gd:971/1154 按 name 续局 + 主线存档续战", "live"),
        # 主线
        ("list_mainlines", "GET", "/mainlines[?user_name]", "—", "—",
         "main.gd:5596 进入 MainlineView", "live"),
        ("list_heroes", "GET", "/heroes", "—", "—",
         "main.gd:5594 / hero_speaker_map 空时拉", "live"),
        ("get_mainline_detail", "GET", "/mainlines/{id}", "—", "—",
         "main.gd:5777 章节详情", "live"),
        ("fetch_mainline_dialogue", "GET", "/mainlines/dialogue?path=", "—", "—",
         "main.gd:6540/6586 战前/战间对话", "live"),
        ("get_unlocked_commanders", "GET", "/players/me/commanders?user_name=", "—", "—",
         "main.gd:3902/5595", "live"),
        ("select_mainline_commander", "POST", "/mainlines/{id}/select-commander",
         "{user_name,commander_id}", "—",
         "main.gd:5555 章节指挥官选择", "live"),
        ("get_mainline_prepare", "GET", "/mainlines/{id}/prepare?user_name=", "—", "—",
         "main.gd:5791/5836/5849/6399/6409", "live"),
        ("promote_mainline_hero", "POST", "/mainlines/{id}/prepare/promote", "—", "—",
         "main.gd:6346 转职", "live"),
        ("equip_mainline_hero", "POST", "/mainlines/{id}/prepare/equipment", "—", "—",
         "main.gd:6356 装备", "live"),
        ("get_post_battle_shop", "GET", "/mainlines/{id}/shop?user_name=", "—", "—",
         "main.gd:5821/6410", "live"),
        ("purchase_post_battle_shop_item", "POST", "/mainlines/{id}/shop/purchase", "—", "—",
         "main.gd:6372", "live"),
        ("get_mercenary_config", "GET", "/mainlines/{id}/mercenary/config?user_name=", "—",
         "—",
         "main.gd:5825/6419", "live"),
        ("allocate_mercenary_points", "POST", "/mainlines/{id}/mercenary/allocate", "—", "—",
         "main.gd:6384", "live"),
        ("complete_mainline_prepare", "POST", "/mainlines/{id}/prepare/complete", "—",
         "—",
         "network_client.gd:624(未在 UI 触发)", "未触发"),
        ("start_mainline", "POST", "/mainlines/{id}/start",
         "{user_name,skip_intro,force,disabled_unit_indices}", "—",
         "main.gd:5839/6567 (含 force=true 重试)", "live"),
        ("advance_mainline", "POST", "/mainlines/{id}/advance", "{user_name,game_id}",
         "—", "main.gd:1964 战斗胜利推进章节", "live"),
        ("next_battle_mainline", "POST", "/mainlines/{id}/next-battle", "{user_name}", "—",
         "main.gd:6611 章节内下一战", "live"),
        ("abandon_mainline", "POST", "/mainlines/{id}/abandon", "{user_name}", "—",
         "main.gd:6511/6636 放弃章节", "live"),
        # 存档
        ("list_saves", "GET", "/saves?user_name=", "—", "—",
         "main.gd:1012/5604/5740/6130", "live"),
        ("save_manual", "POST", "/saves/save",
         "{user_name,slot_index,mainline_id,chapter_index,label}", "—",
         "network_client.gd:672(UI 未触发 — P0 缺口)", "未触发"),
        ("load_save", "POST", "/saves/load", "{user_name,kind,slot_index}", "—",
         "main.gd:1119/5683", "live"),
        ("load_suspend", "POST", "/saves/load_suspend", "{user_name}", "—",
         "main.gd:1115 启动快速续局", "live"),
        ("erase_save", "POST", "/saves/erase", "{user_name,kind,slot_index}", "—",
         "main.gd:1167/5729", "live"),
        ("capture_suspend", "POST", "/games/{id}/suspend", "{user_name}", "—",
         "network_client.gd:702(未在 UI 触发)", "未触发"),
        # 音频
        ("list_audio_tracks", "GET", "/audio/tracks", "—", "—",
         "main.gd:4496 Lobby BGM 下拉", "live"),
        # WS
        ("connect_to_game", "WS", "/ws/games/{id}?player_id=&since_seq=", "—", "—",
         "main.gd 9 处;e2e_one_game:138", "live"),
        ("ws_close", "WS", "/ws/games/{id}", "—", "—",
         "main.gd:2510 返回主菜单", "live"),
        ("ws_send", "WS", "/ws/games/{id}", "client.action.*", "—",
         "network_client.gd:367(预留方向,网关不消费)", "未触发"),
        ("ws_connect", "WS", "/ws/games/{id}", "raw URL", "—",
         "network_client.gd:198(escape hatch)", "未触发"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 28, 8, 35, 35, 14, 35, 10])
    _freeze(ws, "C3")


# ============================================================
# Sheet 4: WS 消息流
# ============================================================

def build_sheet_ws(wb):
    ws = wb.create_sheet("WS 消息流")
    _title(ws, "WebSocket 消息流 / 服务端 → 客户端 + 客户端 ping + 心跳 + 重连")

    headers = ["#", "方向", "type", "payload", "signal", "handler / 副作用", "锚点"]
    _row(ws, 2, headers, header=True)

    rows = [
        ("→", "server.hello", "{server_version,protocol_version,current_seq,heartbeat_sec,supports_replay,authed_player_id}",
         "server_hello_received", "GameState._on_server_hello,写 log + 记 seq", "network_client.gd:308"),
        ("→", "state.snapshot", "{game: GameStateOut}",
         "state_snapshot_received(game)", "GameState._on_state_snapshot(全替换缓存)",
         "network_client.gd:309-313"),
        ("→", "event.delta", "{event_type, ...}",
         "event_delta_received(event)", "GameState._on_event_delta → 18 个 typed signal 派发",
         "network_client.gd:314"),
        ("→", "server.pong", "{echo_at_ms}",
         "server_pong_received", "(无订阅,仅 log)", "network_client.gd:316"),
        ("→", "turn.advance", "{...}", "event_delta_received(payload.duplicate())",
         "(网关当前不发 — server-ws-events-gap)", "network_client.gd:319-322"),
        ("→", "error", "{code,message,...}", "protocol_error_received",
         "log + UI error", "network_client.gd:323-326"),
        ("→", "commentary.text", "{text}", "(no-op)",
         "预留 AI 旁白(Godot no-op 未接)", "network_client.gd:327"),
        ("→", "commentary.audio", "{...}", "(no-op)",
         "预留 AI 旁白(Godot no-op 未接)", "network_client.gd:328"),
        ("←", "client.ping", "{sent_at_ms}", "(无 ack)",
         "25s 自动发(_ws_send_ping)", "network_client.gd:335-347"),
        ("网络", "心跳", "server.pong 30s",
         "服务端 WS gateway", "NetworkClient 检测 STATE_CLOSED → 触发重连",
         "network_client.gd:255-287"),
        ("网络", "重连退避",
         "0.5s → 1.0 → 2.0 → 4.0 → 8.0 → 16.0 → 30.0 ... 30s 封顶",
         "(用户主动 ws_close 时停)", "connect → close → create_timer(delay) → _open_ws,带 since_seq",
         "network_client.gd:349-361"),
        ("网络", "since_seq 回放",
         "ws://...?since_seq={N}", "(N = 上次收到 seq)",
         "服务端环形缓冲补发漏 event.delta", "network_client.gd:65, 299-301"),
        ("网络", "轮询兜底", "GET /games/{id}/state",
         "(无单独 signal)", "main.gd:1728 _schedule_board_refresh (200ms debounce)",
         "main.gd:1714-1728"),
        ("外部约束", "服务端不发 WS",
         "end_turn / 回合结束 / 对局结束", "(走 REST GET /state 追踪)",
         "MEMORY.md server-ws-events-gap.md", "—"),
        ("外部约束", "网关不消费 client.action.*",
         "所有玩家动作走 REST", "—", "action_move / action_attack etc.",
         "network_client.gd:380-386"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 9, 18, 38, 28, 50, 25])
    _freeze(ws, "C3")


# ============================================================
# Sheet 5: 棋盘 + UnitNode
# ============================================================

def build_sheet_board(wb):
    ws = wb.create_sheet("棋盘+单位")
    _title(ws, "棋盘 / 渲染管线 / UnitNode 组件")

    headers = ["#", "节点 / 类", "类型", "职责", "关键代码 / 数据", "锚点"]
    _row(ws, 2, headers, header=True)

    rows = [
        # Board 节点
        ("Board", "Node2D root", "协调 layers / camera",
         "tile_set / metrics / map_size / tile_lookup", "board.gd"),
        ("GroundLayer", "TileMapLayer z=0", "地形基础",
         "plain / forest / river / mountain / ...", "board.gd:35-40"),
        ("StructureLayer", "TileMapLayer z=1", "地表",
         "castle / village / barracks / gate + 5 castle_subtype",
         "map_theme.gd:14-25"),
        ("DecorLayer", "TileMapLayer z=2", "装饰层(预留)",
         "LayerKind.DECOR 当前无 key", "map_theme.gd:5"),
        ("HighlightLayer", "Node2D z=3", "高亮层",
         "7 mode × sprite pool(MOVE/ATTACK/PATH/THREAT/SELECTED/HOVER)",
         "highlights.gd:24-33"),
        ("UnitLayer", "Node2D z=4", "单位渲染(增量 diff)",
         "Board._on_units_changed → seen_ids 集合", "board.gd:54-90"),
        ("EffectsLayer", "Node2D z=5", "浮动文字",
         "spawn_floating_text:上浮 60px + 0.8s fade", "board.gd:167-196"),
        ("BoardCamera", "Camera2D", "fit / 拖 / 缩",
         "_FIT_MARGIN=16 / _UI_LEFT_FRACTION=0.00 / _UI_RIGHT_FRACTION=0.45",
         "board_camera.gd:5-8"),
        # TileSet
        ("MapMetrics", "常量子 + helper",
         "TILE_SIZE=48 / 任意 15-45 / {w,h} 非方形",
         "board_size / cell_origin / cell_to_local / bounds_for",
         "map_metrics.gd:5-58"),
        ("MapTheme",
         "LayerKind 路由",
         "Ground/Structure/Decor 决策",
         "_GROUND_OVERLAY / _STRUCTURE_SOURCE_KEYS",
         "map_theme.gd:5-32"),
        ("TileSetBuilder",
         "atlas 构建",
         "legacy per-terrain vs FE8 master (预留)",
         "SOURCE_IDS / _build_fe8_atlas_source / 4×4 autotile 预留",
         "tile_set_builder.gd:32-210"),
        ("MapLoader",
         "字符 → 后端名字",
         "_CASTLE_SUBTYPE_CHARS 字典 + apply_to_board 三层写入",
         "tile_owners 不写(server 单独叠加)",
         "map_loader.gd:8-111"),
        ("MapLogic", "纯客户端 UI 镜像",
         "BFS reachable / Dijkstra pathfind / has_line_of_sight / attack_range_tiles",
         "server-authority — 不基于此拒绝动作",
         "map_logic.gd:1-15"),
        # UnitNode components
        ("UnitNode._marker", "阵营底块",
         "40×40 中心 28% α", "Config.player_color", "unit_node.gd:135"),
        ("UnitNode._sprite",
         "TextureRect",
         "48×48 res://assets/classic/{type}.png",
         "TextureLoader.load_resized 兜底", "unit_node.gd:142"),
        ("UnitNode._type_label",
         "Label 22px", "white + shadow",
         "sprite 缺失时显示", "unit_node.gd:157"),
        ("UnitNode._hp_bar_bg",
         "42×5 灰底", "—",
         "_COL_BG_BAR (0.05,0.05,0.05,0.85)",
         "unit_node.gd:174"),
        ("UnitNode._hp_bar",
         "40×3,绿/黄/红阈值",
         ">0.5 绿 / >0.25 黄 / ≤0.25 红",
         "三档颜色", "unit_node.gd:180"),
        ("UnitNode._mp_badge",
         "12×12 圆点(右下)",
         "max_mp > 0 显示",
         "_COL_MP_BLUE (0.31,0.71,0.95)",
         "unit_node.gd:188"),
        ("UnitNode._mp_badge_label",
         "百分比,100% 显 ★", "—",
         "黑底字", "unit_node.gd:195"),
        ("UnitNode._hero_crest",
         "18×18 右上",
         "hero_id != ''",
         "res://assets/heroes/crest_{id}.png",
         "unit_node.gd:210"),
        ("UnitNode._hero_badge",
         "14×14 金色方块 + H",
         "crest 缺失 fallback",
         "(0.95,0.72,0.24,0.95)",
         "unit_node.gd:218"),
        ("UnitNode._star_label",
         "士气 ⭐ 1-5",
         "morale × ⭐",
         "0 空字符串", "unit_node.gd:236"),
        ("UnitNode._acted_overlay",
         "40×40 半透黑", "has_acted=true",
         "(0,0,0,0.55)",
         "unit_node.gd:246"),
        # 移动 + 浮动
        ("FLIP 移动动画",
         "0.32s TRANS_CUBIC EASE_OUT",
         "起点 prev_pos → 终点 new_pos",
         "Tween.set_trans",
         "board.gd:72-79"),
        ("spawn_floating_text_at_cell",
         "Label 80×28 + Tween 上浮 60px + 0.8s fade",
         "💥/⚡/💀/💰/🚶",
         "shadow_offset (2,2)",
         "board.gd:167-196"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 28, 18, 28, 38, 22])
    _freeze(ws, "C3")


# ============================================================
# Sheet 6: 战斗动作链路
# ============================================================

def build_sheet_combat(wb):
    ws = wb.create_sheet("战斗动作链路")
    _title(ws, "7 战斗动作 + CO Power × 玩家触发 → 后端 REST 完整链路")

    headers = ["#", "动作", "玩家触发", "main.gd 入口 / 行号", "状态字段", "REST 调用", "网络"]
    _row(ws, 2, headers, header=True)

    rows = [
        ("移动", "选中己方 → 移动按钮 → 点可达格",
         "_move_unit_to(uid, tx, ty)",
         "_move_mode_unit_id, _move_reachable_set",
         "action_move(...)",
         "POST /games/{id}/move"),
        ("攻击(forecast)", "选中 → 攻击 → 点敌",
         "_show_attack_confirm",
         "_attack_mode_unit_id, _attack_targets",
         "forecast_attack(...)",
         "GET /games/{id}/forecast-attack"),
        ("攻击(执行)", "ConfirmBtn",
         "_on_attack_confirm_pressed → _attack_unit_to",
         "_pending_attack_*",
         "action_attack(...)", "POST /games/{id}/attack"),
        ("技能(heal)", "healer + heal 按钮 → 点友军",
         "_on_skill_pressed → _heal_targets (8-邻接 HP<max)",
         "_skill_mode_unit_id, _skill_targets",
         "action_skill(...)", "POST /games/{id}/skill"),
        ("技能(arcane)",
         "warlock + 奥术冲击 → 点敌",
         "_enter_arcane_mode → _arcane_targets (Manhattan 1-2)",
         "—", "action_skill(arcane_strike)",
         "POST /games/{id}/skill"),
        ("占领",
         "claim 按钮(village / barracks / castle_vault)",
         "_on_claim_pressed",
         "PendingClaim (2 回合)",
         "action_claim(...)",
         "POST /games/{id}/claim"),
        ("招募", "点空 barracks → RecruitPanel → 选兵种",
         "_show_recruit_at → _recruit_unit_to",
         "_recruit_pending_tile",
         "action_recruit(...)", "POST /games/{id}/recruit"),
        ("待命", "wait 按钮",
         "_on_wait_pressed",
         "has_acted=true",
         "action_wait(...)", "POST /games/{id}/wait"),
        ("结束回合", "HUD end_turn 按钮",
         "_on_end_turn_pressed (2017-2019)",
         "current_player_index++",
         "action_end_turn(...)", "POST /games/{id}/end-turn"),
        ("CO Power", "CO meter 发动按钮",
         "_on_co_power_pressed (~1747)",
         "CO meter → 全友军 atk/def 加成 N 回合",
         "action_co_power(...)", "POST /games/{id}/co-power"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 15, 30, 35, 25, 25, 30])
    _freeze(ws, "C3")


# ============================================================
# Sheet 7: 大厅 / 主线 / 存档 / 设置
# ============================================================

def build_sheet_lobby_mainline(wb):
    ws = wb.create_sheet("大厅+主线+存档")
    _title(ws, "大厅 + 主线 + 存档 + 暂停 / 教学 / 设置 — 状态机 + 关键函数 + 行号")

    headers = ["#", "模块", "功能 / 阶段", "关键函数", "行号锚点(main.gd)", "REST 调用"]
    _row(ws, 2, headers, header=True)

    rows = [
        # 大厅
        ("大厅", "视图入口", "_on_lobby_pressed",
         "3893-3907", "GET /games/presets / audio/tracks / players/me/commanders"),
        ("大厅", "4 视图切换 choose / create / join / in_room",
         "_show_lobby_choose / create / join / in_room",
         "3909-3986", "—"),
        ("大厅", "座位卡片 9 子控件",
         "_build_lobby_seat_card", "4728-4845", "—"),
        ("大厅", "自动轮询 2s",
         "_refresh_lobby_view → _on_lobby_state",
         "5142-5226",
         "GET /games/{id}/state"),
        ("大厅", "创建流水线 6 步",
         "create_game → join → 加 AI → 配 seat → 配 team → start",
         "5085-5114 + 4174-4330",
         "POST /games + join + add_ai + PATCH /seat + PATCH /team + start"),
        ("大厅", "加入流程",
         "_on_join_selected_pressed",
         "5117-5124",
         "POST /games/{id}/join(role/team)"),
        ("大厅", "观战转换",
         "_on_lobby_to_spec_pressed → remove + re-join(spectator)",
         "5422-5439",
         "DELETE + POST /join(role=spectator)"),
        ("大厅", "房主控件",
         "_render_lobby_host_controls / _on_lobby_host_apply_pressed",
         "5316-5419",
         "PATCH /team"),
        ("大厅", "win_condition 硬编码 rout",
         "_selected_lobby_win_condition", "4421-4426",
         "POST /games(battle_config.win_condition)"),
        ("大厅", "BGM 下拉",
         "_setup_lobby_bgm_options",
         "4463-4482",
         "GET /audio/tracks"),
        # 主线
        ("主线", "章节列表",
         "_on_mainline_pressed → _render_mainline_slots + chapter list",
         "5573-5771",
         "GET /mainlines + list_saves"),
        ("主线", "3 存档格",
         "_on_ml_slot_resume / _on_ml_slot_delete",
         "5678-5742",
         "POST /saves/load + DELETE"),
        ("主线", "章节详情",
         "_on_ml_card_pressed → _on_ml_detail_response",
         "5774-5791",
         "GET /mainlines/{id}"),
        ("主线", "对话分发(dialogue/narration/choice/battle_ref/wait)",
         "_play_dialogue_scenes + _advance_dialog",
         "2621-2763",
         "GET /mainlines/dialogue"),
        ("主线", "战前整备 6 tab",
         "_render_mainline_prepare + _on_prepare_tab_pressed",
         "5817-6489",
         "GET prepare + promote + equipment + shop + mercenary"),
        ("主线", "整备启动 + 409 重试",
         "start_mainline → 409 → abandon_mainline → start_mainline(retry=true)",
         "5839/6567",
         "POST /mainlines/{id}/start + abandon"),
        ("主线", "战斗胜利推进",
         "_on_match_ended → advance_mainline",
         "1911-1964 + 6574-6604",
         "POST /mainlines/{id}/advance"),
        ("主线", "下一战按钮(MainlineNextBtn)",
         "_on_mainline_next_battle_pressed",
         "6606-6611",
         "POST /mainlines/{id}/next-battle"),
        ("主线", "弃章",
         "_on_ml_abandon_pressed",
         "6628-6636",
         "POST /mainlines/{id}/abandon"),
        # 存档
        ("存档", "列表(3 手动 + 1 自动 + 1 suspend)",
         "_on_saves_response",
         "1015-1052",
         "GET /saves"),
        ("存档", "manual 写盘按钮(🔴 P0 缺口)",
         "—", "—",
         "POST /saves/save(未触发)"),
        ("存档", "加载存档",
         "_on_save_resume_pressed → load_save / load_suspend",
         "1107-1138",
         "POST /saves/load + /load_suspend"),
        ("存档", "rejoin_game_by_name(主线续局)",
         "_on_ml_slot_resume_response",
         "5704-5723",
         "POST /games/{id}/rejoin_by_name"),
        ("存档", "删除",
         "_on_save_delete_pressed",
         "1157-1182",
         "POST /saves/erase"),
        # 暂停 / 教学
        ("暂停", "Esc → PauseOverlay",
         "_toggle_pause (PROCESS_MODE_WHEN_PAUSED + tree.paused)",
         "2373-2387",
         "—"),
        ("暂停", "回到主菜单(重置 game_state)",
         "_reset_game_state_for_main_menu",
         "2507-2552",
         "WS close + 重置 cache"),
        ("教学", "首次触发 5 条",
         "_trigger_first_tutorial → _show_first_tutorial_deferred",
         "904-925",
         "—(本地硬编码)"),
        # 设置
        ("设置", "字号 3 档(生效)",
         "_apply_font_size → ThemeDB.default_font_size + re-apply HUD",
         "2430-2475",
         "—"),
        ("设置", "颜色 4 色(只写 pref)",
         "_apply_preferred_color → UserSettings.set_value",
         "2479-2481",
         "—"),
        ("设置", "主题 3 选(简化版只换 backdrop)",
         "_apply_theme",
         "1814-1824",
         "—"),
        ("设置", "静音 toggle(死按钮)",
         "_on_toggle_mute_pressed(无 connect)",
         "1797-1801",
         "AudioManager.toggle_muted()"),
        ("设置", "玩家名 Apply",
         "_on_settings_apply_pressed",
         "2419-2426",
         "UserSettings.set_value"),
        ("设置", "Help 面板(死函数)", "show_help()", "1831-1888", "—"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 12, 30, 40, 18, 50])
    _freeze(ws, "C3")


# ============================================================
# Sheet 8: 编辑器
# ============================================================

def build_sheet_editor(wb):
    ws = wb.create_sheet("编辑器")
    _title(ws, "地图编辑器 — 三部署模式 / 撤销重做 / 历史栈 / 行号锚点")

    headers = ["#", "项", "模式/类型", "内容/字符", "中文 UI", "后端契约", "锚点(main.gd / main.tscn / 后端)"]
    _row(ws, 2, headers, header=True)

    rows = [
        # 部署模式
        ("部署模式", "Terrain", "地形",
         "P / F / M / R / r / S",
         "平原/森林/山地/河流/道路/雪峰",
         "TERRAIN_CHAR_TO_NAME[char]",
         "main.gd:250-258 / editor.py:40 / config.gd:200"),
        ("部署模式", "Surface", "地表",
         "C / v / b / g",
         "城堡/村庄/兵营/城门",
         "castle / village / barracks / gate",
         "main.gd:251-258"),
        ("部署模式", "Surface subtype", "城堡细分类",
         "f/F / w/W / t/T / d/D / s/S / V/v",
         "castle_floor/wall/throne/door/stairs/vault",
         "_CASTLE_SUBTYPE_CHARS(map_loader.gd:8-13)",
         "map_loader.gd:8-13"),
        ("部署模式", "Unit", "5 类 + 4 色 + 等级 1-10",
         "swordsman/archer/knight/healer/warlock + red/blue/green/yellow + 1-10",
         "剑士/弓手/骑士/治疗师/术士",
         "InitialUnit schema",
         "editor.py:54-130"),
        ("部署模式", "owner", "无主 + 4 色",
         "['', red, blue, green, yellow]",
         "(无主/红/蓝/绿/黄)",
         "color ∈ _VALID_COLORS",
         "editor.py:_VALID_COLORS"),
        # tile_owners
        ("tile_owners", "custom 字段",
         "List[TileOwner{x,y,color}]",
         "服务端 schema + client 写入",
         "color 解析 → player_id",
         "editor.py:54-130 / game.py:650-651"),
        # 历史栈
        ("历史栈", "_editor_undo_stack",
         "50 步 FIFO", "Array[Dictionary]", "—",
         "_EDITOR_HISTORY_LIMIT=50",
         "main.gd:256-258"),
        ("历史栈", "_editor_redo_stack",
         "50 步 FIFO", "Array[Dictionary]", "—", "—",
         "main.gd:256-258"),
        ("历史栈", "push 操作(7 个)",
         "地形绘制 / 地表绘制 / 单位放置 / 单位擦除 / 新建 / 调整尺寸 / 套用生态",
         "—", "—",
         "_push_editor_history",
         "main.gd:3536/3581/3619/3649/3660/3675/3713"),
        ("历史栈", "清栈",
         "加载 / 保存 后端响应 / push 操作末尾(redo 清)",
         "—", "—",
         "_reset_editor_history",
         "main.gd:_reset_editor_history"),
        ("历史栈", "按钮可用性",
         "undo_btn.disabled = stack.is_empty()",
         "—", "—",
         "_update_editor_history_buttons",
         "main.gd:3468-3472"),
        ("历史栈", "快捷键 Ctrl+Z / Ctrl+Y",
         "仅 editor_view.visible 时生效", "—", "—",
         "_unhandled_input KEY_Z/KEY_Y",
         "main.gd:2040-2050"),
        # 网络调用
        ("网络", "list_editor_maps",
         "GET /editor/maps", "—",
         "—", "—",
         "network_client.gd:441"),
        ("网络", "load_editor_map",
         "GET /editor/maps/{id}", "—", "—",
         "—",
         "network_client.gd:445"),
        ("网络", "save_editor_map",
         "POST /editor/maps", "CustomMapSave",
         "—", "—",
         "network_client.gd:449"),
        ("网络", "delete_editor_map",
         "DELETE /editor/maps/{id}", "—",
         "—", "—",
         "network_client.gd:453"),
        # CustomMapIn
        ("Schema", "id", "Optional[str]",
         "None=新建 / 给定=更新", "—", "—",
         "editor.py:54"),
        ("Schema", "name", "str",
         "1-64 字符", "—", "—",
         "editor.py:55"),
        ("Schema", "size", "MapSize{width, height}",
         "15 ≤ w/h ≤ 45", "—", "—",
         "editor.py:56"),
        ("Schema", "biome", "str",
         "∈ {grass, snow, desert}",
         "—", "—",
         "editor.py:57"),
        ("Schema", "layout", "List[str]",
         "每行 width 字符",
         "—", "—", "editor.py:_validate_layout"),
        ("Schema", "initial_units", "List[InitialUnit]",
         "{x, y, type, color, level}", "—", "—",
         "editor.py"),
        ("Schema", "tile_owners", "List[TileOwner]",
         "{x, y, color}", "—", "—",
         "editor.py"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 16, 14, 28, 22, 22, 35])
    _freeze(ws, "C3")


# ============================================================
# Sheet 9: 工具链
# ============================================================

def build_sheet_tools(wb):
    ws = wb.create_sheet("工具链")
    _title(ws, "tools/ 26 个脚本 × 用途 / 触发 / NetworkClient / 输出")

    headers = ["#", "类别", "脚本", "大小", "入口", "NetworkClient 调用", "跑法 / 输出"]
    _row(ws, 2, headers, header=True)

    rows = [
        # 冒烟
        ("冒烟", "smoke_test", "73KB", ".tscn 包装",
         "仅 has_method() 静态校验", "`godot --headless --path godot-client res://tools/smoke_test.tscn`"),
        ("e2e", "e2e_one_game", "13KB", ".tscn",
         "create/join/add-ai/start/WS/action_end_turn/get_state", "`godot --headless ... res://tools/e2e_one_game.tscn` → 600s 上限"),
        ("e2e", "entry_flow_e2e", "3.6KB", ".tscn",
         "走 main 内部回调", "`godot --headless ... res://tools/entry_flow_e2e.tscn`"),
        ("e2e", "chapter_06_ai_takeover", "18KB", ".tscn",
         "不调 NetworkClient,操作 GameState",
         "`godot --headless ... res://tools/chapter_06_ai_takeover.tscn`"),
        ("e2e", "chapter_06_verify_events", "29KB", ".tscn",
         "不调 NetworkClient", "25 字段验证 → 6 阶段 + 截图"),
        ("e2e", "chapter_06_trigger_test", "13KB", ".tscn",
         "不调 NetworkClient", "5 张 snapshot 截图"),
        ("e2e", "ws_e2e.py", "11KB", "Python",
         "Python websocket-client,5 阶段",
         "`python tools/ws_e2e.py [--host] [--port]`"),
        # 截图
        ("截图", "menu_screenshot", "691B", ".tscn",
         "—", "5 帧后 user://menu_screenshot.png"),
        ("截图", "settings_screenshot", "1.7KB", ".tscn",
         "—", "SettingsPanel → user://settings_screenshot.png"),
        ("截图", "story_screenshot", "2.3KB", ".tscn",
         "—", "DialogPanel + TutorialBubble + BattleResultPanel 同框"),
        ("截图", "game_screenshot", "6KB", ".tscn",
         "—", "HUD 4 角 pill + InfoPanel + ActionBubble + WarReportPanel 全开"),
        ("截图", "game_overview", "5.5KB", ".tscn",
         "—", "游戏 + PausePanel 同框"),
        ("截图", "views_screenshot", "1.1KB", ".tscn",
         "—", "BB_SCREENSHOT_VIEWS 批量(只截 menu)"),
        ("截图", "screenshot", "2.8KB", ".tscn",
         "—", "48px tile 层渲染验证"),
        ("截图", "move_screenshot", "7KB", ".tscn",
         "走 main.action_move",
         "选中→移动→POST /move→unit_moved 后截图"),
        ("截图", "attack_screenshot", "6KB", ".tscn",
         "走 main.action_attack",
         "选中→attack→POST /attack→unit_attacked 后截图"),
        ("截图", "attack_forecast_screenshot", "7.5KB", ".tscn",
         "直接 NetworkClient.request(GET /forecast-attack)",
         "创建临时 map codex_forecast_screenshot + 跑完删除"),
        ("截图", "lobby_subview_screenshot", "2.7KB", ".tscn",
         "走 main 内部", "4 张:choose / create / join / in-room"),
        ("截图", "lobby_create_preview_screenshot", "2.3KB", ".tscn",
         "走 main + 假响应",
         "res://screenshots/lobby_*.png(commit)"),
        ("截图", "large_board_screenshot", "2KB", ".tscn",
         "—", "balanced_4p_20 + Camera 验证"),
        ("截图", "flow_screenshot", "8KB", ".tscn",
         "走 main + BB_ATTACK_FORCE_RANGE=10",
         "v0.3 端到端 8 帧 demo"),
        ("截图", "full_game_screenshot", "4.1KB", ".tscn",
         "走 main + 轮询 end_turn",
         "完整 1 局 vs AI 直到 match_ended,3 张图"),
        ("截图", "live_screenshot", "2.3KB", ".tscn",
         "走 main + _start_dev_ai_game",
         "WS snapshot 后立即截"),
        # 辅助
        ("辅助", "sync_assets.py", "2.3KB", "Python",
         "—",
         "把 `game/app/web/assets/tiles/*.png` 70 张同步到 `godot-client/assets/tiles/`,`--check` byte-diff 退出码 1"),
        ("辅助", "check_chinese_ui.py", "3.6KB", "Python",
         "—",
         "扫 scenes/ + scripts/ 的 `.gd` + `.tscn` UI 文案,白名单空,exit 0/1"),
        # 启动
        ("启动", "play.bat", "354B", "Windows 批处理",
         "—", "`Godot_v4.7-stable_win64_console.exe --rendering-driver opengl3 --path godot-client res://scenes/main.tscn`"),
        ("启动", "run_debug.sh", "2.6KB", "bash 脚本",
         "—", "自动 kill 旧 godot → 启动 console → 写 `logs/run_*.log` → 总结"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 9, 32, 12, 25, 35, 50])
    _freeze(ws, "C3")


# ============================================================
# Sheet 10: 缺口 / 死代码 / Bug
# ============================================================

def build_sheet_dead(wb):
    ws = wb.create_sheet("缺口+死代码")
    _title(ws, "P0/P1/P2 缺口 + 死代码 + Bug 修复清单(按优先级排序)")

    headers = ["#", "优先级", "类型", "项", "位置锚点", "建议修复", "状态"]
    _row(ws, 2, headers, header=True)

    rows = [
        ("P0", "缺口", "Manual save 写盘按钮完全缺失",
         "main.tscn / main.gd(Saves 视图 / Prepare Saves tab)",
         "新增 save_new_btn 调 `NetworkClient.save_manual(...)`",
         "dead"),
        ("P1", "缺口", "JoinByCodeButton 死按钮",
         "main.tscn:143-146,disabled=true",
         "接 `_on_join_by_code_pressed` → 输 code → 过滤 list_games → join_game",
         "dead"),
        ("P1", "缺口", "主菜单 SettingsButton 死按钮",
         "main.tscn:173-175 + main.gd:463, 6657-6658",
         "接 `_on_settings_open_pressed`(已有 main.gd:2410)",
         "dead"),
        ("P1", "缺口", "Help 面板无触发按钮",
         "main.gd:1831 show_help 实现但无任何 tscn 节点触发",
         "加 ❓ / 玩法说明 按钮 → connect show_help",
         "dead"),
        ("P1", "缺口", "静音 toggle 死按钮",
         "main.gd:1797 `_on_toggle_mute_pressed` 无 connect",
         "加 mute_btn 节点 connect",
         "dead"),
        ("P1", "缺口", "MainlineNextBtn 默认 visible=false",
         "main.tscn:1990-1993",
         "已 wired 但需真实 advance 流程验证",
         "partial"),
        ("P1", "缺口", "Editor 高级工具缺失(fill/line/select/move/recolor)",
         "main.gd(仅 3 部署模式 + undo/redo 50 步)",
         "补 fill / line / select / move / recolor",
         "missing"),
        ("P1", "Bug", "`gs.set(\"is_connected\")` 字段名错",
         "network_client.gd:95-96",
         "改为 `gs.set(\"ws_connected\", true)`",
         "bug"),
        ("P2", "缺口", "主题切换 stub(只换 backdrop 色)",
         "main.gd:1814-1824",
         "M5.5 写完整 .tres 主题",
         "stub"),
        ("P2", "缺口", "`_on_lobby_seat_commander_step` 只本地 UI",
         "main.gd:4951-4957",
         "若要持久化需补 API",
         "partial"),
        ("P2", "缺口", "commentary.text/audio WS 类型 no-op",
         "network_client.gd:327-329",
         "接战报 / 聊天面板",
         "no-op"),
        ("P2", "缺口", "战斗中观战模式 \"结束回合 → ✅ 确认(继续)\" 未实现",
         "main.gd(end_turn_button 始终 \"结束回合\")",
         "在 spec 模式动态改文本",
         "missing"),
        ("P2", "缺口", "主题 dropdown label 与 tscn 占位符不一致",
         "main.tscn:1752 \"像素战棋风\" vs dropdown \"深绿像素\"",
         "统一文本",
         "typo"),
        ("P2", "缺口", "`_apply_preferred_color` 只写 pref 不生效",
         "main.gd:2479-2481",
         "加 hot-effect(改下一房间即时生效)",
         "stub"),
        ("P2", "缺口", "board THREAT / SELECTED / HOVER mode 预留未触发",
         "highlights.gd:35-39",
         "引入攻击威胁范围",
         "no-op"),
        ("P2", "缺口", "`capture_suspend` 已实现未触发",
         "network_client.gd:702",
         "接主动挂起 UI",
         "dead"),
        ("P2", "缺口", "`complete_mainline_prepare` 已实现未触发",
         "network_client.gd:624",
         "接主线 \"准备好了\" 按钮",
         "dead"),
        ("P2", "缺口", "`get_lobby` 包好未触发",
         "network_client.gd:542",
         "WebUI 改用 /state,Godot 可继续 /state",
         "dead"),
        ("P2", "缺口", "`delete_game` 包好未触发",
         "network_client.gd:464",
         "WebUI 旧存档删除按钮有,Godot 加同样按钮",
         "dead"),
        ("P2", "死节点", "主菜单 JoinByCodeButton",
         "main.tscn:143-146", "接通或删除", "dead"),
        ("P2", "死节点", "EditorSurfaceOption 重复声明",
         "main.tscn 行 323 + 374", "去重前者", "dead"),
        ("P2", "死代码", "InputState signals 未连",
         "input_state.gd:11-13 + main.gd 0 connect", "M2 接通 Board click handler",
         "no-op"),
        ("P2", "死代码", "AudioManager 仅 main.gd 3 处触发(511/1253/1799)",
         "main.gd", "进大厅 / 进主线 / 进结算各调一次", "partial"),
        ("P2", "死代码", "commentary 队列与面板",
         "main.gd", "接 WS commentary frame → 战报 / 聊天面板",
         "missing"),
        ("P2", "todo", "M5.5 完整主题 .tres",
         "main.gd:1814", "写 deep_gba / metal_silver / minimal_light .tres",
         "todo"),
        ("P2", "todo", "M4 移动端 export",
         "—", "Android + iOS 输入重映射 + 手势相机",
         "todo"),
        ("P2", "todo", "M5 HTML5 export + WSS 部署",
         "—", "WSS 公网 host + HTML5", "todo"),
    ]

    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=str(i - 2)).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT
        for j, v in enumerate(r, start=2):
            c = ws.cell(row=i, column=j, value=v)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

    _autosize(ws, [5, 8, 10, 35, 35, 40, 12])
    _freeze(ws, "C3")


# ============================================================
# Main
# ============================================================

def main():
    wb = Workbook()
    wb.remove(wb.active)

    build_sheet_overview(wb)
    build_sheet_autoloads(wb)
    build_sheet_rest(wb)
    build_sheet_ws(wb)
    build_sheet_board(wb)
    build_sheet_combat(wb)
    build_sheet_lobby_mainline(wb)
    build_sheet_editor(wb)
    build_sheet_tools(wb)
    build_sheet_dead(wb)

    out = Path(__file__).parent / "Godot客户端功能调查报告.xlsx"
    wb.save(str(out))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
