"""matplotlib-side renderer (layout A per the design doc).

Consumes a :class:`ClassGrowthCurve` and produces one PNG.

Style follows dataviz skill's mark spec + marks-and-anatomy:
  - 2 px lines
  - ≥8 px dot markers with 2 px surface ring
  - Recessive 0.5 px gridlines
  - Categorical hue per stat (fixed order, never cycled)
  - Sequential colormap (YlOrRd) for the heat-graded table cells

The seven-color categorical palette below is a well-known CVD-tested
set (Tableau-10 first seven).  Run ``scripts/validate_palette.js``
to re-validate before tuning.
"""
from __future__ import annotations

import math
import os
from typing import Dict, Sequence

import matplotlib
matplotlib.use("Agg")  # headless on CI / win32
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from app.progression.policies import STAT_KEYS
from tools.growth_charts.dataset import ClassGrowthCurve


# ============================================================
# Style constants
# ============================================================

#: CN-EN stat label tuples for the 6 chart axes.  CN first.
#: (MOV/MP merged per spec §9 — only one panel for movement now.)
STAT_LABELS: Sequence[tuple] = (
    ("hp",   "HP",   "生命"),
    ("atk",  "ATK",  "攻击"),
    ("def",  "DEF",  "防御"),
    ("matk", "MATK", "魔攻"),
    ("mdef", "MDEF", "魔防"),
    ("mov",  "MOV",  "移力"),
)

#: Tableau-10 inspired 7-color categorical palette.  Fixed order —
#: NEVER cycled.  All categories carry their own hue; visual reader
#: gets identity from each mark beside the panel title.
STAT_PALETTE: Dict[str, str] = {
    "hp":   "#2E7DBC",  # royal blue
    "atk":  "#D1493C",  # brick red
    "def":  "#3D8C3A",  # moss green
    "matk": "#8E5CC0",  # grape purple
    "mdef": "#C49A2C",  # ochre yellow
    "mov":  "#2A8E92",  # cyan gray
}

#: Total-stats panel uses a single neutral hue — the line tells the
#: story of magnitude, not category.
NEUTRAL_LINE_COLOR = "#404040"

#: Sequential YlOrRd-like palette used to color-code Δ% cells.
HEATMAP_CMAP = LinearSegmentedColormap.from_list(
    "growth_yellow_orange",
    ["#FFF8E7", "#FCD17B", "#E8853A", "#A13815"],
)

#: Key levels we always highlight on every line / column.
KEY_LEVELS_DEFAULT: tuple = (1, 10, 20)


# ============================================================
# Font setup (Windows-safe CJK)
# ============================================================

def _configure_fonts() -> None:
    """Ensure Chinese stat labels render correctly on Windows.

    Order matters: matplotlib tries the first font in ``sans-serif``
    that has the requested glyph."""
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "Microsoft YaHei UI", "Noto Sans SC",
        "PingFang SC", "SimHei", "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.spines.right"] = False


# ============================================================
# Layout A — figure-level orchestration
# ============================================================

def render_class_growth(
    curve: ClassGrowthCurve,
    *,
    output_path: str,
    key_levels: tuple = KEY_LEVELS_DEFAULT,
) -> None:
    """Render a single curve to PNG.  Output directory is created."""
    _configure_fonts()

    fig = _new_figure()
    outer = fig.add_gridspec(
        nrows=3, ncols=4,
        height_ratios=[0.6, 2.4, 2.0],
        hspace=0.45, wspace=0.4,
    )

    _draw_title(fig.add_subplot(outer[0, :]), curve)
    _draw_small_multiples(
        fig,
        outer[1, :].subgridspec(2, 4, hspace=0.65, wspace=0.35),
        curve,
        key_levels,
    )
    _draw_table(fig.add_subplot(outer[2, :3]), curve, key_levels)
    _draw_total(fig.add_subplot(outer[2, 3]), curve, key_levels)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# Figure factory
# ============================================================

def _new_figure() -> Figure:
    return plt.figure(figsize=(14, 9), dpi=200, facecolor="white")


# ============================================================
# Panel: title (3 text lines, no chart)
# ============================================================

def _draw_title(ax, curve: ClassGrowthCurve) -> None:
    bl = curve.baseline
    ax.axis("off")

    tier_marker = " ★" if bl.tier > 1 else ""
    kind_marker = " | 物理" if bl.attack_kind == "physical" else (
                  " | 魔法" if bl.attack_kind == "magic" else "")
    hero_marker = "  (英雄)" if bl.is_hero else ""

    line1 = f"{bl.label_cn} / {bl.label_en}  ·  Tier {bl.tier}{tier_marker}{kind_marker}{hero_marker}"
    line2 = f"policy: {bl.formula_note.splitlines()[0] if bl.formula_note else 'n/a'}"
    extra_lines = bl.formula_note.splitlines()[1:] if bl.formula_note else []
    line3 = ("  ".join(extra_lines) if extra_lines
             else f"Lv 1..{curve.max_level}  ·  {len(STAT_LABELS)} 维成长可视化")

    ax.text(0.0, 0.85, line1, transform=ax.transAxes,
            fontsize=15, fontweight="bold", color="#1a1a1a",
            ha="left", va="top")
    ax.text(0.0, 0.50, line2, transform=ax.transAxes,
            fontsize=10.5, color="#404040",
            ha="left", va="top", style="italic")
    ax.text(0.0, 0.18, line3, transform=ax.transAxes,
            fontsize=9, color="#6e6e6e",
            ha="left", va="top")


# ============================================================
# Panel: small multiples (6 stat panels + 1 note, 2×4 grid)
# ============================================================

def _draw_small_multiples(fig, sm: GridSpecFromSubplotSpec,
                          curve: ClassGrowthCurve,
                          key_levels: tuple) -> None:
    """2 rows × 4 cols.  Cells 0..5 → 6 stats.  Cell 6 → static-key note."""
    bl = curve.baseline
    positions = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2)]
    axes = [fig.add_subplot(sm[r, c]) for (r, c) in positions]
    for ax, (key, label_en, label_cn) in zip(axes, STAT_LABELS):
        _draw_one_stat_panel(ax, curve, key, label_en, label_cn, key_levels)

    note_ax = fig.add_subplot(sm[1, 3])
    note_ax.axis("off")
    static_keys = [k for k in STAT_KEYS
                   if all(curve.values[lv][k] == bl.base_stats[k]
                          for lv in range(1, curve.max_level + 1))]
    label_index = {k: (cn, en) for k, en, cn in STAT_LABELS}
    if static_keys:
        msg_lines = ["静态维度(不随等级变化):"]
        for k in static_keys:
            cn, en = label_index[k]
            msg_lines.append(f"  · {cn} ({k})")
    else:
        msg_lines = ["(全部维度都参与成长)"]
    note_ax.text(
        0.05, 0.95, "\n".join(msg_lines),
        transform=note_ax.transAxes,
        fontsize=9, color="#5e5e5e", va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.5", fc="#F7F7F2", ec="#E5E5DC", lw=0.6),
    )


def _draw_one_stat_panel(ax, curve: ClassGrowthCurve, key: str,
                         label_en: str, label_cn: str, key_levels: tuple) -> None:
    color = STAT_PALETTE[key]
    levels = list(range(1, curve.max_level + 1))
    series = [curve.values[lv][key] for lv in levels]

    # Faint wash under the curve
    ax.fill_between(levels, series, [0] * len(series),
                    color=color, alpha=0.06, linewidth=0)

    # Main 2 px line
    ax.plot(levels, series, color=color, linewidth=2.0,
            solid_capstyle="round", solid_joinstyle="round", zorder=3)

    # Key-level dots + numeric labels
    show_levels = sorted({lv for lv in key_levels if 1 <= lv <= curve.max_level}
                         | {1, curve.max_level})
    for lv in show_levels:
        v = curve.values[lv][key]
        ax.scatter([lv], [v], s=64, facecolor=color, edgecolor="white",
                   linewidth=2.0, zorder=4)
        ax.annotate(str(v), xy=(lv, v), xytext=(0, 7),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=8, color="#202020")

    # Title (CN 主, EN 副)
    ax.set_title(f"{label_cn}  ·  {label_en}", fontsize=10.5, color="#1a1a1a", pad=4)

    ax.set_xlim(0.5, curve.max_level + 0.5)
    ymin, ymax = min(series), max(series)
    pad = max(1, (ymax - ymin) * 0.18)
    ax.set_ylim(max(0, ymin - pad), ymax + pad)
    ax.grid(True, axis="y", linewidth=0.5, color="#E0E0E0", zorder=1)
    ax.tick_params(axis="both", labelsize=8, color="#888")
    ax.set_xticks(sorted({1, 5, 10, 15, 20} & set(levels)))
    ax.set_yticks(_nice_ticks(ymin, ymax))


def _nice_ticks(ymin: float, ymax: float) -> list:
    """Round to clean integer ticks (per marks-and-anatomy spec)."""
    if ymax - ymin < 1.0:
        return sorted({int(math.floor(ymin)), int(math.ceil(ymax))})
    step = max(1, int(math.ceil((ymax - ymin) / 3.0)))
    nice = []
    v = int(math.floor(ymin / step) * step)
    while v <= ymax + 1:
        nice.append(int(v))
        v += step
    return nice


# ============================================================
# Panel: heat-graded table  (Lv1 / mid / Lv_max + Δ%)
# ============================================================

def _draw_table(ax, curve: ClassGrowthCurve, key_levels: tuple) -> None:
    """Lv1 / mid / L_max comparison table with Δ% heat-graded column."""
    ax.axis("off")

    cols = [lv for lv in key_levels if 1 <= lv <= curve.max_level]
    if 1 not in cols:
        cols = [1] + cols
    if curve.max_level not in cols:
        cols = cols + [curve.max_level]
    cols = list(dict.fromkeys(cols))

    rows = list(STAT_LABELS)
    has_delta = cols[-1] > cols[0]

    header = ["维度 (stat)"] + [f"Lv {lv}" for lv in cols]
    if has_delta:
        header.append("Δ% (L1 → Lmax)")

    cell_text: list[list[str]] = []
    cell_colors: list[list[object]] = []
    delta_values: list[float] = []

    for key, _en, cn in rows:
        l1 = curve.values[1][key]
        row_text = [f"{cn}  ({key})"]
        row_color = ["#FAFAF5"]  # stat-name column gets a neutral wash

        for lv in cols:
            v = curve.values[lv][key]
            row_text.append(str(v))
            row_color.append("white")

        if has_delta:
            final_delta = 0.0 if l1 == 0 else (curve.values[cols[-1]][key] - l1) / l1 * 100.0
            sign = "+" if final_delta >= 0 else ""
            row_text.append(f"{sign}{final_delta:.1f}%")
            row_color.append("#FFFFFF")  # painted after cmap norm
            delta_values.append(final_delta)

        cell_text.append(row_text)
        cell_colors.append(row_color)

    # Normalize Δ% → heatmap color for the last column.
    if has_delta and delta_values:
        dmin, dmax = min(delta_values), max(delta_values)
        if dmax == dmin:
            dmax = dmin + 1.0
        for i, d in enumerate(delta_values):
            norm = (d - dmin) / (dmax - dmin)
            cell_colors[i][-1] = HEATMAP_CMAP(norm)

    tbl = ax.table(
        cellText=cell_text,
        colLabels=header,
        cellColours=cell_colors,
        loc="center",
        cellLoc="center",
        colLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.0, 1.35)

    # Style header row + stat-name column.
    n_data_cols = len(header)
    for col in range(n_data_cols):
        cell = tbl[0, col]
        cell.set_text_props(weight="bold", color="#1a1a1a")
        cell.set_facecolor("#F2F2EC")
    for r in range(1, len(rows) + 1):
        name_cell = tbl[r, 0]
        name_cell.set_text_props(weight="bold", color="#1a1a1a")
        name_cell.set_facecolor("#FAFAF5")

    ax.set_title(
        "Lv1 / mid / L_max 值对比  ·  Δ% 列表示 L1 → Lmax 的总成长",
        fontsize=10.5, pad=10, loc="left", color="#1a1a1a",
    )


# ============================================================
# Panel: total-stats line + headline number
# ============================================================

def _draw_total(ax, curve: ClassGrowthCurve, key_levels: tuple) -> None:
    totals = curve.totals_curve()
    levels = list(totals.keys())
    vals = [totals[lv] for lv in levels]

    ax.plot(levels, vals, color=NEUTRAL_LINE_COLOR, linewidth=2.0,
            solid_capstyle="round", solid_joinstyle="round", zorder=3)
    ax.fill_between(levels, vals, [vals[0]] * len(vals),
                    color=NEUTRAL_LINE_COLOR, alpha=0.06, linewidth=0)

    for lv in sorted({lv for lv in key_levels if 1 <= lv <= curve.max_level}
                     | {1, curve.max_level}):
        v = totals[lv]
        ax.scatter([lv], [v], s=64, facecolor=NEUTRAL_LINE_COLOR,
                   edgecolor="white", linewidth=2.0, zorder=4)
        ax.annotate(str(v), xy=(lv, v), xytext=(0, 7),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=8.5, color="#202020")

    ymin, ymax = min(vals), max(vals)
    pad = max(1, (ymax - ymin) * 0.18)
    # Reserve top 35% of the panel for the headline block, so the
    # big number doesn't overlap with the Lv20 / Lv10 markers.
    headroom = max(1, (ymax - ymin) * 0.55)
    ax.set_ylim(ymin - pad, ymax + pad + headroom)
    ax.set_xlim(0.5, curve.max_level + 0.5)
    ax.grid(True, axis="y", linewidth=0.5, color="#E0E0E0", zorder=1)
    ax.tick_params(axis="both", labelsize=8, color="#888")
    ax.set_xticks(sorted({1, 5, 10, 15, 20} & set(levels)))
    ax.set_yticks(_nice_ticks(ymin, ymax + pad))  # data-only range for ticks
    ax.set_title(f"总和  ·  sum across {len(STAT_LABELS)} stats",
                 fontsize=10.5, color="#1a1a1a", pad=4)

    headline_lv = curve.max_level
    headline_value = totals[headline_lv]
    ax.text(0.5, 0.95, f"Lv {headline_lv}  总和",
            transform=ax.transAxes, fontsize=10, color="#404040",
            ha="center", va="top")
    ax.text(0.5, 0.78, f"{headline_value}",
            transform=ax.transAxes, fontsize=26, fontweight="bold",
            color="#1a1a1a", ha="center", va="top", family="monospace")
    growth_pct = round((totals[headline_lv] - totals[1]) / totals[1] * 100.0, 1)
    sign = "+" if growth_pct >= 0 else ""
    ax.text(0.5, 0.62, f"vs L1: {sign}{growth_pct}%",
            transform=ax.transAxes, fontsize=9.5, color="#5e5e5e",
            ha="center", va="top")


__all__ = ["render_class_growth", "STAT_PALETTE", "KEY_LEVELS_DEFAULT"]
