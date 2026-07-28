"""strip_mainline_batch_b.py — 机械把 main.gd 中 batch B 函数搬到 mainline_controller.gd。

策略:
  1. Read main.gd,识别 batch B 函数边界(从 ^func <name> 到下一个 ^func/#/^class)
  2. 对每个函数体做跨域替换(词边界 regex)— 引用 _user_name 等都改 _main._<x>
  3. 拼接所有搬入函数到 mainline_controller.gd 末尾
  4. 在 main.gd 删除对应函数
  5. _ready 接 batch B 的 ml_prep_* 信号
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path("godot-client/scripts")
MAIN_GD = ROOT / "main.gd"
CONTROLLER_GD = ROOT / "mainline" / "mainline_controller.gd"

# ── Batch B 函数清单(搬入组件)──
BATCH_B_FUNCS = [
    "_on_mainline_prepare_response",
    "_on_prepare_tab_pressed",
    "_on_prepare_start_pressed",
    "_on_prepare_complete_pressed",
    "_on_prepare_complete_response",
    "_on_prepare_refresh_pressed",
    "_render_mainline_prepare",
    "_on_prepare_hero_selected",
    "_on_prepare_equipment_selected",
    "_on_prepare_shop_item_selected",
    "_on_prepare_merc_unit_selected",
    "_on_prepare_merc_stat_selected",
    "_update_prepare_action_buttons",
    "_on_prepare_primary_action_pressed",
    "_on_prepare_secondary_action_pressed",
    "_build_prepare_heroes_text",
    "_build_prepare_roster_text",
    "_build_prepare_equipment_text",
    "_build_prepare_saves_text",
    "_build_prepare_shop_text",
    "_build_prepare_mercenary_text",
    "_on_prepare_shop_response",
    "_on_prepare_mercenary_response",
    "_promote_focused_prepare_hero",
    "_equip_focused_prepare_hero",
    "_purchase_first_shop_item",
    "_allocate_first_mercenary_point",
    "_on_prepare_mutation_response",
    "_on_prepare_shop_purchase_response",
    "_on_prepare_mercenary_allocate_response",
    "_focused_prepare_hero_can_promote",
    "_find_first_equippable_item",
    "_first_mercenary_allocation_choice",
    "_focused_prepare_hero",
    "_selected_equippable_item",
    "_selected_shop_item",
    "_bb_escape",
    "_on_mainline_start_response",
    "_on_mainline_auto_abandon_response",
    "_on_mainline_dialogue_response",
    "_on_mainline_advance_response",
    "_on_mainline_next_battle_pressed",
    "_on_mainline_next_battle_response",
    "_on_ml_back_pressed",
    "_on_ml_abandon_pressed",
    "_on_mainline_abandon_response",
]


# ── 跨域替换(词边界 regex)──
def _cross_domain_replace(text: str) -> str:
    """把所有 mainline 域引用的 main.gd 字段/函数改成 _main._<x>"""
    # 成员字段
    fields = [
        "_user_name", "_selected_mainline_id", "_active_mainline_id",
        "_game_id", "_player_id", "_mainline_battle_game_id",
        "_ml_slot_records", "_mainline_page",
        "_mainline_prepare_payload", "_mainline_prepare_tab",
        "_mainline_shop_payload", "_mainline_mercenary_payload",
        "_mainline_auto_retry_pending",
        "_selected_prepare_hero_id", "_selected_prepare_equipment_id",
        "_selected_prepare_shop_item_id", "_selected_prepare_merc_unit_type",
        "_selected_prepare_merc_stat",
    ]
    for f in fields:
        text = re.sub(rf"\b{f}\b", f"_main.{f}", text)

    # 函数调用
    funcs = [
        ("_show_view", "_main._show_view"),
        ("_update_status", "_main._update_status"),
        ("_is_mainline_already_active_response", "_main._is_mainline_already_active_response"),
        ("_set_prepare_content", "_main._set_prepare_content"),
        ("_play_dialogue_scenes", "_main._play_dialogue_scenes"),
        ("_show_auto_save_toast", "_main._show_auto_save_toast"),
        ("_unit_type_cn", "_main._unit_type_cn"),
    ]
    for src, dst in funcs:
        text = re.sub(rf"\b{src}\b(?=\()", dst, text)

    # saves_view.<helper>(...) — saves 组件 helper 调 mainline 域(改走 _main.saves_view)
    save_helpers = ["_save_records_from_response", "_format_save_name", "_save_option_label"]
    for h in save_helpers:
        text = re.sub(rf"\bsaves_view\.{h}\b", f"_main.saves_view.{h}", text)

    # on_ml_slots_response / on_ml_card_pressed 等组件 self 调 — 保持 Callable(self, "...")
    # (这些都在 batch B 函数内引用 batch A 函数,已搬入组件 self)
    # 实际上 batch B 函数中调用 _on_ml_slots_response 的位置:
    # _on_prepare_primary_action_pressed() 的 "saves" 分支 → 保持 Callable(self, ...) ✓
    # 其它 self call 也保留 self

    return text


def extract_func_block(text: str, func_name: str) -> tuple[str | None, int, int]:
    """Extract function block from main.gd.
    Returns (body_text, start_idx, end_idx) or (None, -1, -1)."""
    # 锚定 ^func <name>(
    pattern = re.compile(rf"^func {func_name}\(", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None, -1, -1
    start = m.start()
    # 找下一个 ^func | ^# comment | ^class | ^var [A-Z] | ^@onready | EOF
    rest = text[m.end():]
    end_match = re.search(r"^(?=func |# |class |var [A-Z]|@onready)", rest, re.MULTILINE)
    end = m.end() + end_match.start() if end_match else len(text)
    return text[start:end], start, end


def main() -> None:
    main_text = MAIN_GD.read_text(encoding="utf-8")
    orig_len = len(main_text)

    # 1) 抽取所有 batch B 函数 + 跨域替换
    extracted: list[tuple[str, str]] = []  # (name, body)
    for fn in BATCH_B_FUNCS:
        body, s, e = extract_func_block(main_text, fn)
        if body is None:
            print(f"[warn] not found: {fn}")
            continue
        transformed = _cross_domain_replace(body)
        extracted.append((fn, transformed))
        print(f"[ok] extract {fn} ({len(body)} chars)")

    # 2) 倒序从 main.gd 删除
    # 必须从后往前删,避免 index 漂移
    to_delete_ranges: list[tuple[int, int]] = []
    for fn in BATCH_B_FUNCS:
        _, s, e = extract_func_block(main_text, fn)
        if s >= 0:
            to_delete_ranges.append((s, e))
    to_delete_ranges.sort(reverse=True)
    for s, e in to_delete_ranges:
        main_text = main_text[:s] + main_text[e:]
    print(f"\n[main.gd] removed {orig_len - len(main_text)} chars")

    # 3) 追加到 mainline_controller.gd
    controller_text = CONTROLLER_GD.read_text(encoding="utf-8")
    # 移除旧的 stub _render_mainline_prepare()
    controller_text = re.sub(
        r"# ── Stubs for Batch B \(kept for compile \+ batch B to fill in\) ──\n\n"
        r"func _render_mainline_prepare\(\) -> void:\n"
        r"\tpass\n",
        "",
        controller_text,
    )

    # 追加 batch B 函数
    additions = []
    for fn, body in extracted:
        # 重新加注释 — 每个函数前加 banner
        additions.append(f"\n# ── {fn} ────────────────────────────────────────\n")
        additions.append(body)
        if not body.endswith("\n"):
            additions.append("\n")

    controller_text += "\n".join(additions)
    CONTROLLER_GD.write_text(controller_text, encoding="utf-8")
    print(f"[controller] appended {sum(len(b) for _, b in extracted)} chars")

    # 4) 写回 main.gd
    MAIN_GD.write_text(main_text, encoding="utf-8")
    print(f"\n[done] saved.")


if __name__ == "__main__":
    main()