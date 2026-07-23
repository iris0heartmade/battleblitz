"""fix_batch_b_round2.py — 第二轮修 batch B:
  1. 把 _update_prepare_tab_buttons / _sync_prepare_selectors / 4 个 _sync_prepare_*_select 搬入 mainline_controller
  2. 修类型推断(`var has_prepare :=` → `: bool` 等)
  3. main.gd:6073 `_main.mainline_view._bb_escape` → 改用 mainline_view._bb_escape(组件)
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path("godot-client/scripts")
MAIN_GD = ROOT / "main.gd"
CONTROLLER = ROOT / "mainline" / "mainline_controller.gd"

# Round 2 helper to move
ROUND2_FUNCS = [
    "_update_prepare_tab_buttons",
    "_sync_prepare_selectors",
    "_sync_prepare_hero_select",
    "_sync_prepare_equipment_select",
    "_sync_prepare_shop_select",
    "_sync_prepare_mercenary_selects",
]


def _cross_replace(text: str) -> str:
    """Round 2 helper cross-domain: 引用 ml_prep_* 节点和 mainline 字段"""
    fields = [
        "_mainline_prepare_payload", "_mainline_prepare_tab",
        "_selected_prepare_hero_id", "_selected_prepare_equipment_id",
        "_selected_prepare_shop_item_id", "_selected_prepare_merc_unit_type",
        "_selected_prepare_merc_stat", "_mainline_shop_payload",
        "_mainline_mercenary_payload",
    ]
    for f in fields:
        text = re.sub(rf"\b{f}\b", f"_main.{f}", text)
    # ml_prep_* 节点:组件内 self,不变
    return text


def extract_func(text: str, name: str) -> tuple[str | None, int, int]:
    p = re.compile(rf"^func {name}\(", re.MULTILINE)
    m = p.search(text)
    if not m:
        return None, -1, -1
    rest = text[m.end():]
    end_m = re.search(r"^(?=func |# |class |var [A-Z]|@onready)", rest, re.MULTILINE)
    end = m.end() + end_m.start() if end_m else len(text)
    return text[m.start():end], m.start(), end


def main() -> None:
    # 1. 读 main.gd,抽取 round 2 helper,跨域替换
    main_text = MAIN_GD.read_text(encoding="utf-8")
    extracted = []
    for fn in ROUND2_FUNCS:
        body, _, _ = extract_func(main_text, fn)
        if body is None:
            print(f"[warn] {fn} not found")
            continue
        extracted.append((fn, _cross_replace(body)))
        print(f"[ok] extract {fn}")

    # 2. 倒序删
    ranges = []
    for fn in ROUND2_FUNCS:
        _, s, e = extract_func(main_text, fn)
        if s >= 0:
            ranges.append((s, e))
    ranges.sort(reverse=True)
    for s, e in ranges:
        main_text = main_text[:s] + main_text[e:]
    MAIN_GD.write_text(main_text, encoding="utf-8")
    print(f"[main.gd] removed {sum(e - s for s, e in ranges)} chars")

    # 3. 追加到 controller
    controller = CONTROLLER.read_text(encoding="utf-8")
    append = "\n\n# ── Round 2 helpers(prepare UI 同步)— Batch B 补 ──────\n"
    for fn, body in extracted:
        append += f"\n# ── {fn} ──\n{body}"
        if not body.endswith("\n"):
            append += "\n"
    controller += append
    print(f"[controller] appended {len(append)} chars")

    # 4. 修类型推断
    type_fixes = [
        (r"var has_prepare := not _main\._mainline_prepare_payload\.is_empty\(\)",
         "var has_prepare: bool = not _main._mainline_prepare_payload.is_empty()"),
        (r"var retry_id := _main\._selected_mainline_id",
         "var retry_id: String = _main._selected_mainline_id"),
    ]
    for pat, rep in type_fixes:
        n = len(re.findall(pat, controller))
        controller = re.sub(pat, rep, controller)
        print(f"[type fix] {pat[:50]} → {n} matches")

    # 修更多可能的类型推断:`var unit_type := ` `var stat := ` 在 _first_mercenary_allocation_choice
    # 看上下文(line 1057-1058 是 _first_mercenary_allocation_choice)
    extra_fixes = [
        (r"var unit_type := _main\._selected_prepare_merc_unit_type",
         "var unit_type: String = _main._selected_prepare_merc_unit_type"),
        (r"var stat := _main\._selected_prepare_merc_stat",
         "var stat: String = _main._selected_prepare_merc_stat"),
    ]
    for pat, rep in extra_fixes:
        if re.search(pat, controller):
            controller = re.sub(pat, rep, controller)
            print(f"[type fix] {pat[:50]}")

    CONTROLLER.write_text(controller, encoding="utf-8")


if __name__ == "__main__":
    main()