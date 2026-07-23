"""redirect_smoke_test_batch_b.py — smoke_test.gd 批量 redirect batch B 函数到 mainline_view.call"""
from __future__ import annotations
import re
from pathlib import Path

SMOKE = Path("godot-client/tools/smoke_test.gd")

# batch B 函数清单(都已搬到 mainline_controller.gd)
BATCH_B_FUNCS = [
    "_on_mainline_prepare_response",
    "_on_prepare_hero_selected",
    "_on_prepare_shop_response",
    "_on_prepare_tab_pressed",
    "_on_prepare_mercenary_response",
    "_on_mainline_start_response",
    "_on_mainline_advance_response",
    "_on_mainline_next_battle_response",
    "_on_mainline_abandon_response",
    "_on_mainline_auto_abandon_response",
    "_on_mainline_dialogue_response",
]


def main() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    orig = len(text)

    # 第一次 redirect 时(行 706-712 区域)已加入 var mainline_view: Node = main_check.get_node("MainlineView")
    # 现在 batch B 范围只需把 main_check.call → mainline_view.call
    for fn in BATCH_B_FUNCS:
        pattern = re.compile(rf"main_check\.call\(\"{fn}\"")
        n_before = len(pattern.findall(text))
        text = pattern.sub(f'mainline_view.call("{fn}"', text)
        print(f"[redirect] {fn}: {n_before}")

    SMOKE.write_text(text, encoding="utf-8")
    print(f"\n[done] {orig - len(text)} chars diff")


if __name__ == "__main__":
    main()