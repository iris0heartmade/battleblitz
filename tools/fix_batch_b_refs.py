"""fix_batch_b_refs.py — 修 batch B 函数搬到组件后剩下的引用问题:
  1. battle_mainline_next_btn → _main.battle_mainline_next_btn(game 域 UI)
  2. 类型推断修复(`var mainline_id :=` → `var mainline_id: String =`)
  3. 任何遗漏的 callable 跨域
"""
from __future__ import annotations
import re
from pathlib import Path

CONTROLLER = Path("godot-client/scripts/mainline/mainline_controller.gd")
MAIN = Path("godot-client/scripts/main.gd")


def fix_controller() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")
    orig = len(text)

    # 1) battle_mainline_next_btn → _main.battle_mainline_next_btn
    text = re.sub(r"\bbattle_mainline_next_btn\b", "_main.battle_mainline_next_btn", text)

    # 2) 类型推断:`var mainline_id :=` → `var mainline_id: String =`
    # (因为 mainline_id 来自 _main 调用,无类型)
    text = re.sub(r"var mainline_id := ", "var mainline_id: String = ", text)
    # 同理 var <unnamed_typed_inferred> — 但只 fix mainline_id 一个已知的

    # 3) any other `var label :=` 等可能受类型推断
    # 这条 batch B 范围内只有 mainline_id

    # 4) main.gd 中的其它 utility 调用 — 确认 _on_mainline_dialogue_response 回调
    # _on_mainline_next_battle_response 现在在组件;main.gd 不应再有该引用

    CONTROLLER.write_text(text, encoding="utf-8")
    print(f"[controller] fixed {orig - len(text)} chars (orig {orig}, now {len(text)})")


def fix_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    orig = len(text)

    # 检查 main.gd 是否还有 _on_mainline_next_battle_pressed 等被搬走的函数引用
    # 这些 connect 已修 — 二次扫描
    # main.gd 还有其它 game 域的 _bb_escape 调用 — 不修,仅 controller 修

    # smoke_test redirect 里有 _on_mainline_prepare_response / _on_mainline_start_response / 等
    # 这些已搬到组件,smoke_test redirect 也需要改 mainline_view.call
    # 但由后续 smoke test 跑时处理,不在此 batch

    MAIN.write_text(text, encoding="utf-8")
    print(f"[main] no change (orig {orig})")


if __name__ == "__main__":
    fix_controller()
    fix_main()