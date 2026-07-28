#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 smoke_test.gd:editor 逻辑已搬到 EditorView 组件,
把测试里对 main_check 的 editor 方法/成员调用改指向 editor_view(=组件)。
_on_editor_pressed 是保留在 main 的入口,不动。"""
import pathlib, sys

F = pathlib.Path(__file__).resolve().parent.parent / "godot-client" / "tools" / "smoke_test.gd"
raw = F.read_text(encoding="utf-8")
nl = "\r\n" if "\r\n" in raw else "\n"
text = raw

# 组件方法(搬走的),把 main_check.call("<m>" → editor_view.call("<m>"
METHODS = [
    "_on_editor_maps_response", "_on_editor_map_selected",
    "_on_editor_load_response", "_on_editor_delete_response",
    "_on_editor_tile_clicked", "_on_editor_resize_pressed",
    "_on_editor_save_response", "_on_editor_undo_pressed",
    "_on_editor_redo_pressed",
]
# 组件成员,把 main_check.get("<v>") → editor_view.get("<v>")
MEMBERS = ["_editor_map", "_selected_editor_map_id"]

changes = 0
for m in METHODS:
    old = f'main_check.call("{m}"'
    new = f'editor_view.call("{m}"'
    c = text.count(old)
    text = text.replace(old, new)
    changes += c
    print(f"  {m}: {c} 处")
for v in MEMBERS:
    old = f'main_check.get("{v}")'
    new = f'editor_view.get("{v}")'
    c = text.count(old)
    text = text.replace(old, new)
    changes += c
    print(f"  {v}: {c} 处")

# 安全检查:确保没有把入口 _on_editor_pressed 误改
assert 'main_check.call("_on_editor_pressed")' in text, "入口 _on_editor_pressed 应保留在 main_check!"
# 确保 editor_view 变量声明存在
assert 'var editor_view: Control = main_check.get_node("EditorView")' in text, "editor_view 变量声明缺失"

F.write_text(text.replace("\n", nl), encoding="utf-8")
print(f"OK: 共 {changes} 处改指向 editor_view;入口 _on_editor_pressed 保留 main。")
