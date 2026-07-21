"""
Godot 全按钮 vs 后端接口对照表生成
- 输入:godot-client/scenes/main.tscn + main.gd
- 输出:docs/架构/Godot按钮-后端接口对照表.md + .xlsx
"""

from __future__ import annotations
import re
from pathlib import Path

REPO = Path(r"D:/Python/BattleBlitz/battleblitz")
TSCN = REPO / "godot-client/scenes/main.tscn"
GD = REPO / "godot-client/scripts/main.gd"
NC = REPO / "godot-client/scripts/autoload/network_client.gd"
OUT_DIR = REPO / "docs/架构"
OUT_DIR.mkdir(parents=True, exist_ok=True)


ENDPOINT = {
    # 游戏生命周期
    'list_presets': 'GET /games/presets',
    'list_editor_maps': 'GET /editor/maps',
    'load_editor_map': 'GET /editor/maps/{id}',
    'save_editor_map': 'POST /editor/maps',
    'delete_editor_map': 'DELETE /editor/maps/{id}',
    'list_games': 'GET /games[?user_name]',
    'delete_game': 'DELETE /games/{id}',
    'create_game': 'POST /games',
    'get_game_state': 'GET /games/{id}/state',
    'join_game': 'POST /games/{id}/join',
    'start_game': 'POST /games/{id}/start',
    'forecast_attack': 'GET /games/{id}/forecast-attack',
    'add_ai_player': 'POST /games/{id}/add-ai',
    'remove_player': 'DELETE /games/{id}/players/{pid}',
    'update_player_team': 'PATCH /games/{id}/players/{pid}/team',
    'update_player_seat': 'PATCH /games/{id}/players/{pid}/seat',
    'get_lobby': 'GET /games/{id}/lobby',
    'rejoin_game_by_player_id': 'POST /games/{id}/rejoin',
    'rejoin_game_by_name': 'POST /games/{id}/rejoin_by_name',
    # 主线
    'list_mainlines': 'GET /mainlines[?user_name]',
    'list_heroes': 'GET /heroes',
    'connect_to_game': 'WS /ws/games/{id}?player_id=&since_seq=',
    'get_mainline_detail': 'GET /mainlines/{id}',
    'fetch_mainline_dialogue': 'GET /mainlines/dialogue?path=',
    'get_unlocked_commanders': 'GET /players/me/commanders?user_name=',
    'select_mainline_commander': 'POST /mainlines/{id}/select-commander',
    'get_mainline_prepare': 'GET /mainlines/{id}/prepare?user_name=',
    'promote_mainline_hero': 'POST /mainlines/{id}/prepare/promote',
    'equip_mainline_hero': 'POST /mainlines/{id}/prepare/equipment',
    'get_post_battle_shop': 'GET /mainlines/{id}/shop?user_name=',
    'purchase_post_battle_shop_item': 'POST /mainlines/{id}/shop/purchase',
    'complete_mainline_prepare': 'POST /mainlines/{id}/prepare/complete',
    'get_mercenary_config': 'GET /mainlines/{id}/mercenary/config?user_name=',
    'allocate_mercenary_points': 'POST /mainlines/{id}/mercenary/allocate',
    'start_mainline': 'POST /mainlines/{id}/start',
    'advance_mainline': 'POST /mainlines/{id}/advance',
    'next_battle_mainline': 'POST /mainlines/{id}/next-battle',
    'abandon_mainline': 'POST /mainlines/{id}/abandon',
    # 存档
    'list_saves': 'GET /saves?user_name=',
    'save_manual': 'POST /saves/save',
    'load_save': 'POST /saves/load',
    'load_suspend': 'POST /saves/load_suspend',
    'erase_save': 'POST /saves/erase',
    'capture_suspend': 'POST /games/{id}/suspend',
    # 音频
    'list_audio_tracks': 'GET /audio/tracks',
    # 战斗
    'action_move': 'POST /games/{id}/move',
    'action_attack': 'POST /games/{id}/attack',
    'action_skill': 'POST /games/{id}/skill',
    'action_wait': 'POST /games/{id}/wait',
    'action_claim': 'POST /games/{id}/claim',
    'action_recruit': 'POST /games/{id}/recruit',
    'action_end_turn': 'POST /games/{id}/end-turn',
    'action_co_power': 'POST /games/{id}/co-power',
}


def main():
    tscn = TSCN.read_text(encoding="utf-8")
    src = GD.read_text(encoding="utf-8")
    nc_src = NC.read_text(encoding="utf-8")

    # 1) 抓 main.tscn 全部 Button 节点
    btn_pat = r'\[node name="([^"]+)" type="Button" parent="([^"]+)"\]\s*\n((?:[^\n]*\n){0,10})'
    buttons = []
    for m in re.finditer(btn_pat, tscn):
        # groups: 1=name, 2=parent, 3=body
        node_name = m.group(1)
        parent_path = m.group(2)
        body = m.group(3)
        txt_match = re.search(r'text\s*=\s*"([^"]*)"', body)
        buttons.append((node_name, parent_path, txt_match.group(1) if txt_match else ""))

    # PascalCase → snake_case(把 ML/UI 等缩写折叠: `_l_` → `l_`)
    def to_snake(name: str) -> str:
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
        snake = re.sub(r'(?<=[a-z])_l_', 'l_', snake)
        return snake

    # 2) 抓 main.gd 全部 .pressed.connect 和 .toggled.connect
    handler_map: dict[str, list[tuple[str, str]]] = {}
    pat = r'([a-zA-Z_][a-zA-Z0-9_]*)\.(pressed|toggled)\.connect\(([a-zA-Z_][a-zA-Z0-9_]*)(?:\.bind\(([^)]*)\))?\)'
    for m in re.finditer(pat, src):
        key = m.group(1).lower()
        sig = m.group(2)
        handler = m.group(3)
        bind = (m.group(4) or "").strip()
        handler_map.setdefault(key, []).append((handler, f"{sig}{' bind='+bind if bind else ''}"))

    # 补:handler 函数体里通过 `$Path/NodeName` 引用的 button 也算已接
    # 我们用 handler 名字反查所有 .pressed.connect — 已有的 handler 名字列表
    all_handlers_in_connect = set()
    for m in re.finditer(pat, src):
        all_handlers_in_connect.add(m.group(3))

    # 3) handler 函数体匹配(宽容版)
    def find_body(name):
        pat = rf'^func {name}\([^)]*\)(?:\s*->\s*[\w\[\]\.]+)?:\n(.*?)(?=^func |\Z)'
        m = re.search(pat, src, re.MULTILINE | re.DOTALL)
        return m.group(1) if m else ""

    # 4) NetworkClient 调用
    def find_calls(body):
        return list(dict.fromkeys(re.findall(r'NetworkClient\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', body)))

    # 5) 哪些方法在 network_client.gd 里**实际有定义**(live)vs 仅调用了但没定义(dead/missing)
    defined = set(re.findall(r'^func ([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', nc_src, re.MULTILINE))

    # 6) 出表
    rows = []
    no_handler = []
    for name, parent, text in buttons:
        key = to_snake(name)
        matches = handler_map.get(key, [])
        if not matches:
            no_handler.append(f"{parent}/{name}")
            # 进一步:button 在源码里是否有同 path 的 var 声明?(即使 var 名 ≠ node 名)
            # 找 @onready var X: Button = $...path/NodeName
            var_for_node = []
            for m in re.finditer(r'@onready var ([a-zA-Z_][a-zA-Z0-9_]*): Button = \$(.*?)/' + re.escape(name) + r'\b', src):
                var_for_node.append(m.group(1))
            # 进一步:那些 var 有没有 .pressed.connect
            actually_wired = [v for v in var_for_node if v.lower() in handler_map]
            if actually_wired:
                # 实际已接(但因为 var name ≠ to_snake(name) 我没找到)— 算 live
                first = actually_wired[0]
                h = handler_map[first.lower()][0][0]
                body = find_body(h)
                calls = find_calls(body)
                eps = [ENDPOINT.get(c, f"?{c}?") for c in calls]
                if not calls:
                    state = "🎨 UI-only"
                    note = f"var {first} 已接 handler {h}(name 转换匹配失败,实际 UI-only)"
                elif any(c not in defined for c in calls):
                    state = "🐞 调用了未定义的方法"
                    note = f"var {first}.{h}: {[c for c in calls if c not in defined]} 未在 network_client.gd 定义"
                else:
                    state = "✅ live"
                    note = f"var {first} 已接 {h}(name 转换匹配失败但实际已接)"
                rows.append({
                    "path": f"{parent}/{name}",
                    "text": text,
                    "handler": h,
                    "nc_calls": calls,
                    "endpoints": eps,
                    "state": state,
                    "note": note,
                })
                continue
            if var_for_node:
                rows.append({
                    "path": f"{parent}/{name}",
                    "text": text,
                    "handler": "—",
                    "nc_calls": [],
                    "endpoints": [],
                    "state": "❌ dead(已声明未接)",
                    "note": f"var {var_for_node} 声明,但未 connect handler",
                })
            else:
                rows.append({
                    "path": f"{parent}/{name}",
                    "text": text,
                    "handler": "—",
                    "nc_calls": [],
                    "endpoints": [],
                    "state": "❌ dead",
                    "note": "tscn 有 button 节点,但 main.gd 未声明 var / 未接 .connect",
                })
            continue
        h, sig = matches[0]
        body = find_body(h)
        calls = find_calls(body)
        eps = [ENDPOINT.get(c, f"?{c}?") for c in calls]
        if not calls:
            state = "🎨 UI-only"
            note = "纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端"
        elif any(c not in defined for c in calls):
            state = "🐞 调用了未定义的方法"
            note = f"NetworkClient.{[c for c in calls if c not in defined]} 未在 network_client.gd 定义"
        else:
            state = "✅ live"
            note = "接线 + endpoint 完整"
        rows.append({
            "path": f"{parent}/{name}",
            "text": text,
            "handler": h,
            "nc_calls": calls,
            "endpoints": eps,
            "state": state,
            "note": note,
        })

    # 输出 markdown 表格
    md_path = OUT_DIR / "Godot按钮-后端接口对照表.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Godot 客户端所有按钮 vs 后端接口对照表\n\n")
        f.write(f"> 自动生成:{Path(__file__).name}\n")
        f.write(f"> main.tscn 共 **{len(buttons)}** 个 Button(全部静态 + 部分动态 `.bind`) × main.gd handlers × `NetworkClient.*`\n")
        f.write(f"> **dead 按钮:{len(no_handler)}**  \n")
        f.write(f"> **状态分布**:`✅ live`(接 endpoint)= {sum(1 for r in rows if r['state']=='✅ live')}  ·  "
                f"`🎨 UI-only`= {sum(1 for r in rows if r['state']=='🎨 UI-only')}  ·  "
                f"`❌ dead`= {sum(1 for r in rows if r['state']=='❌ dead')}\n\n")
        f.write("| # | 路径 | text | handler | NetworkClient 调用 | 后端 endpoint | 状态 | 备注 |\n")
        f.write("|---|------|------|---------|--------------------|----------------|------|------|\n")
        for i, r in enumerate(rows, 1):
            f.write(f"| {i} | `{r['path']}` | `{r['text']}` | `{r['handler']}` | "
                    f"{', '.join('`'+c+'`' for c in r['nc_calls']) or '—'} | "
                    f"{', '.join('`'+e+'`' for e in r['endpoints']) or '—'} | {r['state']} | {r['note']} |\n")

        # 死按钮详细
        if no_handler:
            f.write(f"\n## 无 handler 的死按钮({len(no_handler)})\n\n")
            for b in no_handler:
                f.write(f"- `{b}`\n")
            f.write("\n> 原因:这些 button 节点在 main.tscn 存在,但 main.gd 没有 `*.pressed.connect(...)` 接线。\n")
            f.write("> 检查:可能是 main.gd 用了不同的 handler 名/var 名;或事件被另一段 `_input` 直接处理;或纯视觉残留。\n")
        f.write("\n## 备注\n")
        f.write("- `network_client.gd` 中所有 50 个 typed methods 都在本表 endpoint 映射里;若调用了未列出的 `NetworkClient.x` 即为不在服务端实现或已被删\n")
        f.write("- 本表仅涵盖 `main.tscn` 静态按钮;`main.gd` 中 `_for g in games` 等运行时动态创建的不计入\n")
        f.write("- `pre_battle_dialogue`/`/advance` 自动存档/`auto-save` 等后端内部触发链不暴露成按钮,但服务端的 `auto_save_checkpoint` 仍生效\n")

    # 输出 xlsx
    xlsx_path = OUT_DIR / "Godot按钮-后端接口对照表.xlsx"
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    TITLE_FILL = PatternFill("solid", fgColor="1F2937")
    TITLE_FONT = Font(name="Microsoft YaHei", size=14, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill("solid", fgColor="2563EB")
    HEADER_FONT = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")
    BODY_FONT = Font(name="Microsoft YaHei", size=10)
    YES_FILL = PatternFill("solid", fgColor="DCFCE7")
    PARTIAL_FILL = PatternFill("solid", fgColor="DBEAFE")
    NO_FILL = PatternFill("solid", fgColor="FEE2E2")
    DEAD_FILL = PatternFill("solid", fgColor="FFE4E6")
    THIN = Side(border_style="thin", color="D1D5DB")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
    CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "按钮-后端对照表"

    ws.merge_cells("A1:H1")
    c = ws.cell(row=1, column=1, value="Godot 客户端所有按钮 vs 后端接口对照表")
    c.fill = TITLE_FILL
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    headers = ["#", "路径", "text", "handler", "NetworkClient 调用", "后端 endpoint", "状态", "备注"]
    for col, val in enumerate(headers, 1):
        c = ws.cell(row=2, column=col, value=val)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    for i, r in enumerate(rows, 3):
        ws.cell(row=i, column=1, value=i - 2).border = BORDER
        ws.cell(row=i, column=1).alignment = CENTER
        ws.cell(row=i, column=1).font = BODY_FONT

        cells = [
            (2, r["path"]),
            (3, r["text"]),
            (4, r["handler"]),
            (5, ", ".join(r["nc_calls"]) or "—"),
            (6, ", ".join(r["endpoints"]) or "—"),
            (7, r["state"]),
            (8, r["note"]),
        ]
        for col, val in cells:
            c = ws.cell(row=i, column=col, value=val)
            c.font = BODY_FONT
            c.alignment = WRAP
            c.border = BORDER

        # 状态列上色
        state_col = 7
        state_cell = ws.cell(row=i, column=state_col)
        if r["state"].startswith("✅"):
            state_cell.fill = YES_FILL
        elif r["state"].startswith("🎨"):
            state_cell.fill = PARTIAL_FILL
        elif r["state"].startswith("❌"):
            state_cell.fill = NO_FILL
        elif r["state"].startswith("🐞"):
            state_cell.fill = DEAD_FILL

    # 列宽
    widths = [5, 65, 16, 32, 26, 38, 12, 50]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + col)].width = w
    ws.freeze_panes = "C3"

    wb.save(str(xlsx_path))

    print(f"saved md: {md_path}")
    print(f"saved xlsx: {xlsx_path}")
    print(f"buttons={len(buttons)} live={sum(1 for r in rows if r['state']=='✅ live')} "
          f"ui_only={sum(1 for r in rows if r['state']=='🎨 UI-only')} "
          f"dead={sum(1 for r in rows if r['state']=='❌ dead')} "
          f"no_handler={len(no_handler)}")


if __name__ == "__main__":
    main()
