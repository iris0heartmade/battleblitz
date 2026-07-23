"""strip_mainline_batch_a.py — 机械删除 main.gd 中 batch A 已搬到
mainline_controller.gd 的内容(纯函数 + 成员 + 节点 + _ready connects)。

模式:用 regex 锚定函数签名 + 标记结束(下一个 ^func 或 ^# 注释或 EOF)。
鲁棒性:每次 strip 后立即写回,如某段匹配失败,raise 让用户看到。
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

MAIN_GD = Path("godot-client/scripts/main.gd")

# ── 1) onready 节点段:$MainlineView/MLFrame/<X> 全删,只留 mainline_view ──
ONREADY_BLOCK_OLD = re.compile(
    r"# T:96 MainlineView — 节点全搬入 mainline_controller\.gd \(P2, Batch A\),仅保留视图引用\n"
    r"@onready var mainline_view = \$MainlineView\n",
    re.MULTILINE,
)

# ── 2) mainline 成员删除(全部 13 个) ──
MEMBERS_BLOCK_OLD = re.compile(
    r"var _mainline_session: MainlineSession = null\n"
    r"# Batch A 搬走:mainline 页/commander/prepare/shop/merc 状态全部移到 mainline_controller\n",
    re.MULTILINE,
)

MEMBERS_BLOCK_OLD_2 = re.compile(
    r"const _STATE_POLL_INTERVAL_SEC: float = 1\.0\n"
    r"var _state_poll_timer: Timer = null\n"
    r"# Batch A 搬走:_mainline_auto_retry_pending 移到 mainline_controller\n",
    re.MULTILINE,
)

# ── 3) _ready ml_* connects 段(355-393) ──
READY_ML_BLOCK_OLD = re.compile(
    r"\tif ml_back_btn != null and is_instance_valid\(ml_back_btn\):\n"
    r"\t\tml_back_btn\.pressed\.connect\(_on_ml_back_pressed\)\n"
    r"\tif ml_abandon_btn != null and is_instance_valid\(ml_abandon_btn\):\n"
    r"\t\tml_abandon_btn\.pressed\.connect\(_on_ml_abandon_pressed\)\n"
    r"\tif ml_apply_commander_btn != null and is_instance_valid\(ml_apply_commander_btn\):\n"
    r"\t\tml_apply_commander_btn\.pressed\.connect\(_on_apply_mainline_commander_pressed\)\n"
    r"\tif ml_prep_start_btn != null and is_instance_valid\(ml_prep_start_btn\):\n"
    r"\t\tml_prep_start_btn\.pressed\.connect\(_on_prepare_start_pressed\)\n"
    r"\t# P2:主线准备页准备好了按钮 → 触发 complete_mainline_prepare\(写自动存档\)\n"
    r"\tif ml_prep_complete_btn != null and is_instance_valid\(ml_prep_complete_btn\):\n"
    r"\t\tml_prep_complete_btn\.pressed\.connect\(_on_prepare_complete_pressed\)\n"
    r"\tif ml_prep_refresh_btn != null and is_instance_valid\(ml_prep_refresh_btn\):\n"
    r"\t\tml_prep_refresh_btn\.pressed\.connect\(_on_prepare_refresh_pressed\)\n"
    r"\tif ml_prep_action_btn != null and is_instance_valid\(ml_prep_action_btn\):\n"
    r"\t\tml_prep_action_btn\.pressed\.connect\(_on_prepare_primary_action_pressed\)\n"
    r"\tif ml_prep_alt_action_btn != null and is_instance_valid\(ml_prep_alt_action_btn\):\n"
    r"\t\tml_prep_alt_action_btn\.pressed\.connect\(_on_prepare_secondary_action_pressed\)\n"
    r"\tif ml_prep_heroes_tab_btn != null and is_instance_valid\(ml_prep_heroes_tab_btn\):\n"
    r"\t\tml_prep_heroes_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"heroes\"\)\)\n"
    r"\tif ml_prep_roster_tab_btn != null and is_instance_valid\(ml_prep_roster_tab_btn\):\n"
    r"\t\tml_prep_roster_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"roster\"\)\)\n"
    r"\tif ml_prep_equipment_tab_btn != null and is_instance_valid\(ml_prep_equipment_tab_btn\):\n"
    r"\t\tml_prep_equipment_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"equipment\"\)\)\n"
    r"\tif ml_prep_mercenary_tab_btn != null and is_instance_valid\(ml_prep_mercenary_tab_btn\):\n"
    r"\t\tml_prep_mercenary_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"mercenary\"\)\)\n"
    r"\tif ml_prep_shop_tab_btn != null and is_instance_valid\(ml_prep_shop_tab_btn\):\n"
    r"\t\tml_prep_shop_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"shop\"\)\)\n"
    r"\tif ml_prep_saves_tab_btn != null and is_instance_valid\(ml_prep_saves_tab_btn\):\n"
    r"\t\tml_prep_saves_tab_btn\.pressed\.connect\(_on_prepare_tab_pressed\.bind\(\"saves\"\)\)\n"
    r"\tif ml_prep_hero_select != null and is_instance_valid\(ml_prep_hero_select\):\n"
    r"\t\tml_prep_hero_select\.item_selected\.connect\(_on_prepare_hero_selected\)\n"
    r"\tif ml_prep_equipment_select != null and is_instance_valid\(ml_prep_equipment_select\):\n"
    r"\t\tml_prep_equipment_select\.item_selected\.connect\(_on_prepare_equipment_selected\)\n"
    r"\tif ml_prep_merc_unit_select != null and is_instance_valid\(ml_prep_merc_unit_select\):\n"
    r"\t\tml_prep_merc_unit_select\.item_selected\.connect\(_on_prepare_merc_unit_selected\)\n"
    r"\tif ml_prep_merc_stat_select != null and is_instance_valid\(ml_prep_merc_stat_select\):\n"
    r"\t\tml_prep_merc_stat_select\.item_selected\.connect\(_on_prepare_merc_stat_selected\)\n"
    r"\tif ml_prep_shop_select != null and is_instance_valid\(ml_prep_shop_select\):\n"
    r"\t\tml_prep_shop_select\.item_selected\.connect\(_on_prepare_shop_item_selected\)\n",
    re.MULTILINE,
)

# 替代以一行注释
READY_ML_BLOCK_NEW = (
    "\t# Batch A 搬走:ml_* connects 改在 mainline_controller._ready(节点已搬入组件)\n"
)

# ── 4) commander helpers 段(`_setup_mainline_commander_options` 到 `_on_select_mainline_commander_response`) ──
# 用 function-spanning regex(从 ^func ... 到下一个 ^func ... )
# 但更简单:用 fixed string 删除精确文本块

# ── 5) `_on_mainline_pressed` 函数(改写为 thin wrapper) ──
ON_MAINLINE_PRESSED_OLD = re.compile(
    r"# T:96 — MainlineView 章节列表 \+ 入口\n"
    r"func _on_mainline_pressed\(\) -> void:\n"
    r"[\s\S]*?"
    r"\tNetworkClient\.list_saves\(_user_name, Callable\(self, \"_on_ml_slots_response\"\)\)\n",
    re.MULTILINE,
)
ON_MAINLINE_PRESSED_NEW = (
    "# T:96 — MainlineView 入口 thin wrapper(完整逻辑搬到 mainline_controller.open())\n"
    "func _on_mainline_pressed() -> void:\n"
    "\tif mainline_view != null and is_instance_valid(mainline_view):\n"
    "\t\tmainline_view.open()\n"
)


def _strip_func_block(text: str, start_re: re.Pattern) -> str:
    """Strip function block: from start_re match to next ^func or ^# ."""
    m = start_re.search(text)
    if not m:
        raise RuntimeError(f"start_re not found: {start_re.pattern[:60]}")
    start = m.start()
    # find next ^func or ^# 或 EOF(从 start + 1 行开始)
    rest = text[m.end():]
    end_match = re.search(r"^(?=func |# |class |var [A-Za-z]|@onready)", rest, re.MULTILINE)
    if end_match:
        end = m.end() + end_match.start()
    else:
        end = len(text)
    return text[:start] + text[end:]


def main() -> None:
    text = MAIN_GD.read_text(encoding="utf-8")
    orig_len = len(text)

    # 1) onready 节点段(已部分 Edit,可能已替换;尝试)
    if ONREADY_BLOCK_OLD.search(text):
        text = ONREADY_BLOCK_OLD.sub(
            "# T:96 MainlineView — 节点全搬入 mainline_controller.gd (P2, Batch A),仅保留视图引用\n"
            "@onready var mainline_view = $MainlineView\n",
            text,
        )
        print("[ok] 1 onready block")
    else:
        # 旧版本(没替换成功)— 删 27 个 ml_*
        text = re.sub(
            r"@onready var ml_[a-z_]+: \w+ = \$MainlineView[^\n]*\n",
            "",
            text,
        )
        print("[ok] 1 onready (raw regex fallback)")

    # 2) mainline 成员
    if MEMBERS_BLOCK_OLD.search(text):
        text = MEMBERS_BLOCK_OLD.sub(
            "var _mainline_session: MainlineSession = null\n",
            text,
        )
    if MEMBERS_BLOCK_OLD_2.search(text):
        text = MEMBERS_BLOCK_OLD_2.sub(
            "const _STATE_POLL_INTERVAL_SEC: float = 1.0\n"
            "var _state_poll_timer: Timer = null\n",
            text,
        )
    print("[ok] 2 members")

    # 3) _ready ml_* connects
    if READY_ML_BLOCK_OLD.search(text):
        text = READY_ML_BLOCK_OLD.sub(READY_ML_BLOCK_NEW, text)
        print("[ok] 3 ready ml_* connects")
    else:
        print("[warn] 3 ready ml_* connects pattern not found, skipped")

    # 4) 改写 _on_mainline_pressed
    text = ON_MAINLINE_PRESSED_OLD.sub(ON_MAINLINE_PRESSED_NEW, text)
    print("[ok] 4 _on_mainline_pressed thin wrapper")

    # 5-14) 删除 batch A 函数,每个用 regex 锚定 ^func <name>
    batch_a_funcs = [
        r"^func _setup_mainline_commander_options\(",
        r"^func _commander_label\(",
        r"^func _selected_mainline_commander\(",
        r"^func _on_commanders_response\(",
        r"^func _on_apply_mainline_commander_pressed\(",
        r"^func _on_select_mainline_commander_response\(",
        r"^func _set_node_visible\(",
        r"^func _set_mainline_page\(",
        r"^func _on_ml_slots_response\(",
        r"^func _render_mainline_slots\(",
        r"^func _on_ml_slot_resume\(",
        r"^func _on_ml_slot_loaded_response\(",
        r"^func _on_ml_slot_delete\(",
        r"^func _on_ml_slot_delete_response\(",
        r"^func _on_ml_list_response\(",
        r"^func _on_ml_card_pressed\(",
        r"^func _on_ml_detail_response\(",
    ]
    for pat in batch_a_funcs:
        regex = re.compile(pat, re.MULTILINE)
        before = len(text)
        text = _strip_func_block(text, regex)
        delta = before - len(text)
        print(f"[ok] strip {pat[:50]} ({delta} chars)")

    MAIN_GD.write_text(text, encoding="utf-8")
    print(f"\n[done] main.gd: {orig_len} -> {len(text)} chars (saved {orig_len - len(text)})")


if __name__ == "__main__":
    main()