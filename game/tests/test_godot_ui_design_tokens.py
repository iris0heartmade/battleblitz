## test_godot_ui_design_tokens.py — UI V3 设计语言 token + 组件的合约测试。
##
## 守护 spec `docs/规范/UI/2026-07-25-UI-设计语言规范.md` 第 3-7 节:
##   - MenuTheme 必须暴露 V3 新增 token
##   - 4 个公共组件必须存在且 class_name 注册
##   - scene / script 里禁止 inline 颜色字面量(除 menu_theme.gd 外)
##   - tscn 里 offset_* / separation / content_margin_* 必须命中 8px 网格

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MENU_THEME = ROOT / "godot-client" / "scripts" / "ui" / "menu_theme.gd"
COMPONENTS = ROOT / "godot-client" / "scripts" / "ui" / "_components"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_menu_theme_exposes_all_v3_tokens():
    src = _read(MENU_THEME)
    # V3 新增配色 token
    for tok in ["C_LOADING", "C_ERROR", "C_PLACEHOLDER"]:
        assert f"const {tok}:" in src, f"missing color token {tok}"
    # V3 新增字号
    for tok in ["FS_LOADING", "FS_PLACEHOLDER", "FS_BODY_SM", "FS_SUBTITLE"]:
        assert f"const {tok}:" in src, f"missing font token {tok}"
    # V3 网格 token
    for tok in ["GRID_1", "GRID_2", "GRID_3", "GRID_4", "GRID_5", "GRID_6"]:
        assert f"const {tok}:" in src, f"missing grid token {tok}"
    # V3 padding/gap
    for tok in ["PAD_S", "PAD_M", "PAD_L", "GAP_S", "GAP_M", "GAP_L"]:
        assert f"const {tok}:" in src, f"missing pad/gap token {tok}"


def test_v3_components_exist_with_class_name():
    expected = {
        "status_badge.gd": "StatusBadge",
        "section_header.gd": "SectionHeader",
        "section_card.gd": "SectionCard",
        "button_row.gd": "ButtonRow",
    }
    for fname, class_name in expected.items():
        p = COMPONENTS / fname
        assert p.exists(), f"missing component {p}"
        src = _read(p)
        assert f"class_name {class_name}" in src, f"{fname} missing class_name {class_name}"


def test_no_inline_color_literals_outside_menu_theme():
    """扫所有 .gd,除 menu_theme.gd / autoload config(游戏数据色)外不允许出现 Color('#xxxxxx') 字面量。"""
    bad: list[str] = []
    pattern = re.compile(r'Color\("#[0-9a-fA-F]{6,8}"\)')
    exempt = {
        MENU_THEME,
        ROOT / "godot-client" / "scripts" / "autoload" / "config.gd",
        # tile_set_builder 用 Config.TERRAIN_COLORS 的 fallback,游戏数据色
        ROOT / "godot-client" / "scripts" / "core" / "tile_set_builder.gd",
    }
    for gd in (ROOT / "godot-client" / "scripts").rglob("*.gd"):
        if gd in exempt:
            continue
        for i, line in enumerate(_read(gd).splitlines(), 1):
            if pattern.search(line):
                bad.append(f"{gd.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not bad, "inline Color() literals found (must use MenuTheme.C_*):\n" + "\n".join(bad)


def test_no_inline_grid_offsets_in_tscn():
    """扫所有 .tscn,offset_* / separation / content_margin_* 必须是 GRID_* 倍数或 0。
    只检查新增/重构的 scene;legacy main.tscn 留待 V4 布局重排。
    """
    allowed = {0, 4, 8, 16, 24, 32, 48, 64, 96}
    bad: list[str] = []
    pattern = re.compile(
        r'^(offset_(?:left|right|top|bottom)|separation|content_margin_(?:left|right|top|bottom))\s*=\s*(-?\d+\.?\d*)$'
    )
    # 检查 _components/ 下以及新建的工具 scene;main.tscn 留给布局重排(V4)
    target = [
        ROOT / "godot-client" / "scenes" / "ui",  # 新建 UI scene
    ]
    scenes: list[Path] = []
    for d in target:
        if d.exists():
            scenes.extend(d.rglob("*.tscn"))
    for tscn in scenes:
        for i, line in enumerate(_read(tscn).splitlines(), 1):
            m = pattern.match(line)
            if not m:
                continue
            v = float(m.group(2))
            if int(v) not in allowed and round(v) not in allowed:
                bad.append(
                    f"{tscn.relative_to(ROOT)}:{i}: {m.group(1)}={v} not on 8px grid"
                )
    assert not bad, "tscn offsets not on 8px grid:\n" + "\n".join(bad[:20])


def test_components_use_only_menu_theme_tokens():
    """组件自身不允许自己定义颜色/字号常量,必须引用 MenuTheme.*"""
    for gd in COMPONENTS.glob("*.gd"):
        src = _read(gd)
        # 允许 MenuTheme.C_*, MenuTheme.FS_*, MenuTheme.GRID_*, MenuTheme.PAD_* 等
        # 不允许 Color("#...") 或 const FS_X = N 这种裸定义
        assert 'Color("' not in src, f"{gd.name} has inline Color()"
        assert "const C_" not in src, f"{gd.name} defines own color (use MenuTheme.C_*)"
        assert "const FS_" not in src, f"{gd.name} defines own font size (use MenuTheme.FS_*)"