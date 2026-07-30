#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 重构:把地图编辑器逻辑从 main.gd 抽离到 scripts/ui/editor_controller.gd。

策略:
  - 按 top-level `func NAME` 边界,把 MOVE_FUNCS 集合的函数体搬进新组件文件,
    并在函数体上做 3 处跨域调用替换。
  - 共享 helper(_unit_type_cn 等)与 lobby 域的 _upsert_editor_map_as_lobby_preset
    以及入口 _on_editor_pressed 保留在 main。
  - 再对精简后的 main 做若干精确字符串替换(删声明/成员/connect、改入口、改快捷键)。
仅做机械搬迁,不改变任何运行逻辑。
"""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = ROOT / "godot-client" / "scripts" / "main.gd"
COMPONENT = ROOT / "godot-client" / "scripts" / "ui" / "editor_controller.gd"

# 搬入组件的函数(全部 editor func + 2 个 editor 专用 color label)。
# 排除:_on_editor_pressed(入口,改写保留)、_upsert_editor_map_as_lobby_preset(lobby 域,保留)。
MOVE_FUNCS = {
    "_setup_editor_options", "_editor_terrain_label", "_editor_biome_label",
    "_team_color_label", "_owner_color_label",
    "_selected_editor_biome", "_selected_editor_terrain_char",
    "_selected_editor_surface_char", "_selected_editor_surface_owner_color",
    "_selected_editor_mode", "_on_editor_mode_selected",
    "_update_editor_mode_controls", "_is_editor_unit_mode",
    "_is_editor_surface_mode", "_selected_editor_unit_type",
    "_selected_editor_unit_color", "_selected_editor_unit_level",
    "_selected_editor_size", "_select_editor_size_option",
    "_is_editor_unit_erase_mode", "_build_blank_editor_map",
    "_render_editor_map", "_snapshot_editor_map", "_push_editor_history",
    "_reset_editor_history", "_update_editor_history_buttons",
    "_restore_editor_snapshot", "_on_editor_undo_pressed",
    "_on_editor_redo_pressed", "_paint_editor_tile", "_set_editor_tile_owner",
    "_paint_editor_surface", "_on_editor_tile_clicked", "_erase_editor_unit",
    "_place_editor_unit", "_on_editor_new_pressed",
    "_on_editor_apply_biome_pressed", "_on_editor_resize_pressed",
    "_on_editor_load_pressed", "_on_editor_delete_pressed",
    "_on_editor_save_pressed", "_on_editor_back_pressed",
    "_on_editor_maps_response", "_on_editor_map_selected",
    "_on_editor_load_response", "_on_editor_delete_response",
    "_on_editor_save_response",
}

FUNC_RE = re.compile(r"^func\s+([A-Za-z0-9_]+)\s*\(")


def parse_funcs(lines):
    """返回 [(name, start_idx, end_idx)],end 为下一 top-level func 起始(或 EOF)。"""
    starts = []
    for i, ln in enumerate(lines):
        m = FUNC_RE.match(ln)
        if m:
            starts.append((i, m.group(1)))
    spans = []
    for k, (idx, name) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        spans.append((name, idx, end))
    return spans


def apply_body_rewrites(text):
    """组件内 3 处跨域调用替换。"""
    text = text.replace("_unit_type_cn(", "unit_label_fn.call(")
    text = text.replace('_show_view("menu")', "back_requested.emit()")
    text = text.replace(
        "_upsert_editor_map_as_lobby_preset(body)", "map_saved.emit(body)"
    )
    return text


COMPONENT_HEADER = '''extends Control
## editor_controller.gd — 地图编辑器视图控制器(P2 从 main.gd 抽离)。
## 挂在场景 EditorView 节点上,自管面板内部逻辑;view 可见性仍由 main._show_view 控制。
## 对外接口:
##   open()                  — main 切到 editor view 后调用:初始化选项 + 拉取地图列表
##   request_undo/redo()     — 供 main 的 Ctrl+Z/Y 快捷键转发
##   signal back_requested   — 用户点返回 → main 切回 menu
##   signal map_saved(map)   — 保存成功 → main upsert lobby 自定义地图预设
##   unit_label_fn: Callable — 注入 main._unit_type_cn(单位名中文化,多域共享)

signal back_requested
signal map_saved(map_data)

var unit_label_fn: Callable = Callable()

const _EDITOR_HISTORY_LIMIT := 50

@onready var editor_board = $EditorBoard
@onready var editor_map_name_input: LineEdit = $EditorPanel/EditorMapNameInput
@onready var editor_biome_option: OptionButton = $EditorPanel/EditorBiomeOption
@onready var editor_apply_biome_btn: Button = $EditorPanel/EditorApplyBiomeBtn
@onready var editor_terrain_option: OptionButton = $EditorPanel/EditorTerrainOption
@onready var editor_surface_option: OptionButton = $EditorPanel/EditorSurfaceOption
@onready var editor_map_select_option: OptionButton = $EditorPanel/EditorMapSelectOption
@onready var editor_load_btn: Button = $EditorPanel/EditorLoadBtn
@onready var editor_mode_option: OptionButton = $EditorPanel/EditorModeOption
@onready var editor_unit_tool_option: OptionButton = $EditorPanel/EditorUnitToolOption
@onready var editor_unit_option: OptionButton = $EditorPanel/EditorUnitOption
@onready var editor_unit_color_option: OptionButton = $EditorPanel/EditorUnitColorOption
@onready var editor_surface_owner_option: OptionButton = $EditorPanel/EditorSurfaceOwnerOption
@onready var editor_unit_level_option: OptionButton = $EditorPanel/EditorUnitLevelOption
@onready var editor_width_option: OptionButton = $EditorPanel/EditorWidthOption
@onready var editor_height_option: OptionButton = $EditorPanel/EditorHeightOption
@onready var editor_resize_btn: Button = $EditorPanel/EditorResizeBtn
@onready var editor_undo_btn: Button = $EditorPanel/EditorUndoBtn
@onready var editor_redo_btn: Button = $EditorPanel/EditorRedoBtn
@onready var editor_status: Label = $EditorPanel/EditorStatus
@onready var editor_new_btn: Button = $EditorPanel/EditorNewBtn
@onready var editor_save_btn: Button = $EditorPanel/EditorSaveBtn
@onready var editor_delete_btn: Button = $EditorPanel/EditorDeleteBtn
@onready var editor_back_btn: Button = $EditorPanel/EditorBackBtn

var _editor_map: Dictionary = {}
var _editor_map_ids: Array[String] = []
var _selected_editor_map_id: String = ""
var _editor_terrain_chars: Array[String] = ["P", "F", "M", "R", "r", "S"]
var _editor_surface_chars: Array[String] = ["C", "v", "b", "g"]
var _editor_unit_types: Array[String] = [
\t"swordsman", "archer", "knight", "healer", "warlock",
\t"lancer", "warrior", "berserker", "dragon_rider", "falcon_knight",
\t"blade_master", "paladin", "sniper", "sage", "saint",
]
var _editor_unit_colors: Array[String] = ["red", "blue", "green", "yellow"]
var _editor_owner_colors: Array[String] = ["", "red", "blue", "green", "yellow"]
var _editor_size_choices: Array[int] = [15, 20, 25, 30, 35, 40, 45]
var _editor_undo_stack: Array[Dictionary] = []
var _editor_redo_stack: Array[Dictionary] = []


func _ready() -> void:
\teditor_new_btn.pressed.connect(_on_editor_new_pressed)
\teditor_save_btn.pressed.connect(_on_editor_save_pressed)
\teditor_load_btn.pressed.connect(_on_editor_load_pressed)
\teditor_delete_btn.pressed.connect(_on_editor_delete_pressed)
\teditor_apply_biome_btn.pressed.connect(_on_editor_apply_biome_pressed)
\teditor_resize_btn.pressed.connect(_on_editor_resize_pressed)
\teditor_undo_btn.pressed.connect(_on_editor_undo_pressed)
\teditor_redo_btn.pressed.connect(_on_editor_redo_pressed)
\teditor_map_select_option.item_selected.connect(_on_editor_map_selected)
\teditor_mode_option.item_selected.connect(_on_editor_mode_selected)
\teditor_back_btn.pressed.connect(_on_editor_back_pressed)
\tif not editor_board.tile_clicked.is_connected(_on_editor_tile_clicked):
\t\teditor_board.tile_clicked.connect(_on_editor_tile_clicked)


func open() -> void:
\t_setup_editor_options()
\tif _editor_map.is_empty():
\t\t_editor_map = _build_blank_editor_map()
\t\t_reset_editor_history()
\t_render_editor_map()
\tif editor_status != null and is_instance_valid(editor_status):
\t\teditor_status.text = "地图编辑器已就绪。"
\tNetworkClient.list_editor_maps(Callable(self, "_on_editor_maps_response"))


func request_undo() -> void:
\t_on_editor_undo_pressed()


func request_redo() -> void:
\t_on_editor_redo_pressed()


'''


def main():
    raw = MAIN.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split("\n")
    # 去掉每行可能残留的 \r,统一用 nl 重组
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in lines]

    spans = parse_funcs(lines)
    found = {name for name, _, _ in spans}
    missing = MOVE_FUNCS - found
    if missing:
        print("ERROR: 这些函数在 main.gd 未找到:", missing)
        sys.exit(1)

    # 收集组件函数体(按 main 出现顺序),并标记 main 中待删行。
    del_idx = set()
    body_chunks = []
    for name, start, end in spans:
        if name in MOVE_FUNCS:
            chunk = "\n".join(lines[start:end])
            body_chunks.append(chunk.rstrip("\n"))
            for i in range(start, end):
                del_idx.add(i)

    component_body = ("\n\n\n").join(body_chunks)
    component_text = COMPONENT_HEADER.replace("\t", "\t") + apply_body_rewrites(
        component_body
    ) + "\n"
    # 组件里 tab:COMPONENT_HEADER 用 \t 字面量已是 tab。函数体来自 main(tab)。
    component_text = component_text.replace("\t", "\t")

    # 生成精简 main(删 MOVE 函数行)。
    kept = [ln for i, ln in enumerate(lines) if i not in del_idx]
    main_text = "\n".join(kept)

    # ---- 精确字符串替换(每处必须唯一存在) ----
    def sub(text, old, new, label):
        cnt = text.count(old)
        if cnt != 1:
            print(f"ERROR: 替换[{label}]期望命中1处,实际{cnt}处")
            sys.exit(1)
        return text.replace(old, new)

    # R1: editor_view 声明去类型标注(以便调用组件方法)
    main_text = sub(
        main_text,
        "@onready var editor_view: Control = $EditorView",
        "@onready var editor_view = $EditorView  # -> editor_controller.gd (P2)",
        "R1 editor_view 声明",
    )

    # R2: 删 editor @onready 节点块(editor_board..editor_back_btn)
    blk_onready = "\n".join([
        "@onready var editor_board: Board = $EditorView/EditorBoard",
        "@onready var editor_map_name_input: LineEdit = $EditorView/EditorPanel/EditorMapNameInput",
        "@onready var editor_biome_option: OptionButton = $EditorView/EditorPanel/EditorBiomeOption",
        "@onready var editor_apply_biome_btn: Button = $EditorView/EditorPanel/EditorApplyBiomeBtn",
        "@onready var editor_terrain_option: OptionButton = $EditorView/EditorPanel/EditorTerrainOption",
        "@onready var editor_surface_option: OptionButton = $EditorView/EditorPanel/EditorSurfaceOption",
        "@onready var editor_map_select_option: OptionButton = $EditorView/EditorPanel/EditorMapSelectOption",
        "@onready var editor_load_btn: Button = $EditorView/EditorPanel/EditorLoadBtn",
        "@onready var editor_mode_option: OptionButton = $EditorView/EditorPanel/EditorModeOption",
        "@onready var editor_unit_tool_option: OptionButton = $EditorView/EditorPanel/EditorUnitToolOption",
        "@onready var editor_unit_option: OptionButton = $EditorView/EditorPanel/EditorUnitOption",
        "@onready var editor_unit_color_option: OptionButton = $EditorView/EditorPanel/EditorUnitColorOption",
        "@onready var editor_surface_owner_option: OptionButton = $EditorView/EditorPanel/EditorSurfaceOwnerOption",
        "@onready var editor_unit_level_option: OptionButton = $EditorView/EditorPanel/EditorUnitLevelOption",
        "@onready var editor_width_option: OptionButton = $EditorView/EditorPanel/EditorWidthOption",
        "@onready var editor_height_option: OptionButton = $EditorView/EditorPanel/EditorHeightOption",
        "@onready var editor_resize_btn: Button = $EditorView/EditorPanel/EditorResizeBtn",
        "@onready var editor_undo_btn: Button = $EditorView/EditorPanel/EditorUndoBtn",
        "@onready var editor_redo_btn: Button = $EditorView/EditorPanel/EditorRedoBtn",
        "@onready var editor_status: Label = $EditorView/EditorPanel/EditorStatus",
        "@onready var editor_new_btn: Button = $EditorView/EditorPanel/EditorNewBtn",
        "@onready var editor_save_btn: Button = $EditorView/EditorPanel/EditorSaveBtn",
        "@onready var editor_delete_btn: Button = $EditorView/EditorPanel/EditorDeleteBtn",
        "@onready var editor_back_btn: Button = $EditorView/EditorPanel/EditorBackBtn",
    ])
    main_text = sub(main_text, blk_onready + "\n", "", "R2 @onready 节点块")

    # R3: 删 editor 成员变量块
    blk_vars = "\n".join([
        "var _editor_map: Dictionary = {}",
        "var _editor_map_ids: Array[String] = []",
        'var _selected_editor_map_id: String = ""',
        'var _editor_terrain_chars: Array[String] = ["P", "F", "M", "R", "r", "S"]',
        'var _editor_surface_chars: Array[String] = ["C", "v", "b", "g"]',
        "var _editor_unit_types: Array[String] = [",
        '\t"swordsman", "archer", "knight", "healer", "warlock",',
        '\t"lancer", "warrior", "berserker", "dragon_rider", "falcon_knight",',
        '\t"blade_master", "paladin", "sniper", "sage", "saint",',
        "]",
        'var _editor_unit_colors: Array[String] = ["red", "blue", "green", "yellow"]',
        'var _editor_owner_colors: Array[String] = ["", "red", "blue", "green", "yellow"]',
        "var _editor_size_choices: Array[int] = [15, 20, 25, 30, 35, 40, 45]",
        "var _editor_undo_stack: Array[Dictionary] = []",
        "var _editor_redo_stack: Array[Dictionary] = []",
        "const _EDITOR_HISTORY_LIMIT := 50",
    ])
    main_text = sub(main_text, blk_vars + "\n", "", "R3 成员变量块")

    # R4: 删 editor connect 块
    blk_connect = "\n".join([
        "\tif editor_new_btn != null and is_instance_valid(editor_new_btn):",
        "\t\teditor_new_btn.pressed.connect(_on_editor_new_pressed)",
        "\tif editor_save_btn != null and is_instance_valid(editor_save_btn):",
        "\t\teditor_save_btn.pressed.connect(_on_editor_save_pressed)",
        "\tif editor_load_btn != null and is_instance_valid(editor_load_btn):",
        "\t\teditor_load_btn.pressed.connect(_on_editor_load_pressed)",
        "\tif editor_delete_btn != null and is_instance_valid(editor_delete_btn):",
        "\t\teditor_delete_btn.pressed.connect(_on_editor_delete_pressed)",
        "\tif editor_apply_biome_btn != null and is_instance_valid(editor_apply_biome_btn):",
        "\t\teditor_apply_biome_btn.pressed.connect(_on_editor_apply_biome_pressed)",
        "\tif editor_resize_btn != null and is_instance_valid(editor_resize_btn):",
        "\t\teditor_resize_btn.pressed.connect(_on_editor_resize_pressed)",
        "\tif editor_undo_btn != null and is_instance_valid(editor_undo_btn):",
        "\t\teditor_undo_btn.pressed.connect(_on_editor_undo_pressed)",
        "\tif editor_redo_btn != null and is_instance_valid(editor_redo_btn):",
        "\t\teditor_redo_btn.pressed.connect(_on_editor_redo_pressed)",
        "\tif editor_map_select_option != null and is_instance_valid(editor_map_select_option):",
        "\t\teditor_map_select_option.item_selected.connect(_on_editor_map_selected)",
        "\tif editor_mode_option != null and is_instance_valid(editor_mode_option):",
        "\t\teditor_mode_option.item_selected.connect(_on_editor_mode_selected)",
        "\tif editor_back_btn != null and is_instance_valid(editor_back_btn):",
        "\t\teditor_back_btn.pressed.connect(_on_editor_back_pressed)",
        "\tif editor_board != null and is_instance_valid(editor_board):",
        "\t\tif not editor_board.tile_clicked.is_connected(_on_editor_tile_clicked):",
        "\t\t\teditor_board.tile_clicked.connect(_on_editor_tile_clicked)",
    ])
    main_text = sub(main_text, blk_connect + "\n", "", "R4 connect 块")

    # R5: _on_editor_pressed 改写为 3 行入口
    old_pressed = "\n".join([
        "func _on_editor_pressed() -> void:",
        '\t_entry_flow = "editor"',
        '\t_show_view("editor")',
        "\t_setup_editor_options()",
        "\tif _editor_map.is_empty():",
        "\t\t_editor_map = _build_blank_editor_map()",
        "\t\t_reset_editor_history()",
        "\t_render_editor_map()",
        "\tif editor_status != null and is_instance_valid(editor_status):",
        '\t\teditor_status.text = "地图编辑器已就绪。"',
        '\tNetworkClient.list_editor_maps(Callable(self, "_on_editor_maps_response"))',
    ])
    new_pressed = "\n".join([
        "func _on_editor_pressed() -> void:",
        '\t_entry_flow = "editor"',
        '\t_show_view("editor")',
        "\teditor_view.open()",
    ])
    main_text = sub(main_text, old_pressed, new_pressed, "R5 入口改写")

    # R6: Ctrl+Z/Y 快捷键转发到组件
    main_text = sub(
        main_text,
        "\t\t\t\t_on_editor_undo_pressed()",
        "\t\t\t\teditor_view.request_undo()",
        "R6 undo 快捷键",
    )
    main_text = sub(
        main_text,
        "\t\t\t\t_on_editor_redo_pressed()",
        "\t\t\t\teditor_view.request_redo()",
        "R6 redo 快捷键",
    )

    # R7: _ready 里注入组件依赖 + 接线(插在 _check_resume_session 调用前)。
    anchor = "\t# T:5 主菜单 load 时尝试匹配存档\n\t_check_resume_session()"
    wire = "\n".join([
        "\t# P2: editor_controller.gd 组件接线(注入共享 helper + 跨域信号)",
        "\tif editor_view != null and is_instance_valid(editor_view):",
        "\t\teditor_view.unit_label_fn = Callable(self, \"_unit_type_cn\")",
        "\t\tif not editor_view.back_requested.is_connected(_on_editor_back_requested):",
        "\t\t\teditor_view.back_requested.connect(_on_editor_back_requested)",
        "\t\tif not editor_view.map_saved.is_connected(_upsert_editor_map_as_lobby_preset):",
        "\t\t\teditor_view.map_saved.connect(_upsert_editor_map_as_lobby_preset)",
        anchor,
    ])
    main_text = sub(main_text, anchor, wire, "R7 组件接线")

    # R8: 新增 _on_editor_back_requested 回调(紧接改写后的入口函数)。
    main_text = sub(
        main_text,
        new_pressed,
        new_pressed + "\n\n\nfunc _on_editor_back_requested() -> void:\n\t_show_view(\"menu\")",
        "R8 back 回调",
    )

    # 写盘(备份原 main)。
    backup = MAIN.with_suffix(".gd.p2bak")
    backup.write_text(raw, encoding="utf-8")
    COMPONENT.write_text(component_text.replace("\n", nl), encoding="utf-8")
    MAIN.write_text(main_text.replace("\n", nl), encoding="utf-8")

    print("OK")
    print(f"  组件: {COMPONENT}  ({component_text.count(chr(10))+1} 行)")
    print(f"  main: {MAIN}  ({main_text.count(chr(10))+1} 行, 原 {raw.count(chr(10))+1} 行)")
    print(f"  备份: {backup}")
    print(f"  搬迁函数数: {len(body_chunks)}")


if __name__ == "__main__":
    main()
