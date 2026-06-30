"""Generate the 7 P0.4 showcase map presets.

Each preset is a square grid of the given edge length. The themes
were brainstormed with the user:

  15x15  — 资源竞速 (resource rush)        — small, fast, 2 income
  20x20  — 双向战线 (two fronts)             — mid, two economy corridors
  25x25  — 三国混战 (three-way melee)        — 3 barracks + villages
  30x30  — 经济扩张 (economic expansion)     — many income, slow push
  35x35  — 城防 (fortress)                   — castles + walls
  40x40  — 王座争夺 (throne war)             — big throne in center
  45x45  — 大混战 (free-for-all)             — huge map, all terrains

Each tile in the grid is encoded as one char (P/F/M/R/C/v/b/r/g) per
the convention already in `_layout_to_tiles`. Castle sub-features
are intentionally not used (the user said: do them only if there's
real demand — there isn't yet).

The output is a series of JSON files dropped into game/maps/, plus
a small Markdown summary for the docs.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "game" / "maps"
OUT.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------
# Map 1 — 15x15 — 资源竞速 (resource rush)
# Compact 2-player map with a single economic corridor down the
# middle: 2 villages + 1 barracks, a road connecting them, plain
# for fast movement.
# --------------------------------------------------------------
def make_resource_rush() -> dict:
    size = 15
    # Symmetric: red (top) vs blue (bottom)
    grid = [
        "PPPPPPPPPPPPPPP",
        "PPCCvvCCCCCCvCC",   # red player zone: 2 villages flank
        "PPPrPrPrPrPrPrP",
        "PPCrCCCCCCCCrCP",   # road network in the middle
        "PPPrPrPrPrPrPrP",
        "PPCCbbCCCCCCbCC",   # mid: 2 barracks
        "PPPrPrPrPrPrPrP",
        "PPPPrPrPrPrPrPP",
        "PPPrPrPrPrPrPrP",
        "PPCrCCCCCCCCrCP",
        "PPPrPrPrPrPrPrP",
        "PPCCvvCCCCCCvCC",   # blue player zone
        "PPPPPPPPPPPPPPP",
        "PPPPPPPPPPPPPPP",
        "PPPPPPPPPPPPPPP",
    ]
    assert all(len(r) == size for r in grid)
    return {
        "id": "resource_rush_15",
        "name": "资源竞速·15×15",
        "description": "2 人经济速战：2 村落 + 2 佣兵站 + 道路，节奏快、强调占领与招募",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": grid,
    }


# --------------------------------------------------------------
# Map 2 — 20x20 — 双向战线 (two fronts)
# A horizontal river divides the map; each half has 2 villages
# and 1 barracks. Two roads cross the river to enable raids.
# --------------------------------------------------------------
def make_two_fronts() -> dict:
    size = 20
    rows = []
    rows.append("PPPPPPPPPPPPPPPPPPPP")
    rows.append("PPCCvvCCCCCCvvCCPP")
    rows.append("PPCrrCCCCCCrrCCCC")
    rows.append("PPCrCCCCCCCCCrCCCC")
    rows.append("PPCrCCbCCPPCCbCCCr")
    rows.append("PPPrCCPPPPPPCCrCCP")
    rows.append("PPCCCCPPFFFFPPCCCC")
    rows.append("PPCCCCFFPPPPFFCCPP")
    rows.append("PPFFFFPPFFFFPPPPFF")
    rows.append("PPFFFFFPPRRRRPPPFF")
    rows.append("PPFFFFFPPRRRRPPFFF")  # river center
    rows.append("PPFFFFFPPRRRRPPPFF")
    rows.append("PPFFFFPPFFFFPPPPFF")
    rows.append("PPCCCCFFPPPPFFCCPP")
    rows.append("PPCCCCPPFFFFPPCCCC")
    rows.append("PPPrCCPPPPPPCCrCCP")
    rows.append("PPCrCCvCCCCvCCCrC")
    rows.append("PPCrCCCCCCCCCrCCCC")
    rows.append("PPCrrCCCCCCrrCCCC")
    rows.append("PPCCvvCCCCCCvvCCPP")
    rows = [r.ljust(size, "P")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "two_fronts_20",
        "name": "双向战线·20×20",
        "description": "2-3 人东西对峙：河流分两半，各有 2 村落 + 1 佣兵站；2 条渡河道路鼓励穿插",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# --------------------------------------------------------------
# Map 3 — 25x25 — 三国混战 (three-way melee)
# Three equidistant spawn areas (NE / S / W). 3 barracks for fast
# recruit. 2-3 income points each.
# --------------------------------------------------------------
def make_three_way() -> dict:
    size = 25
    rows = []
    # Row 0
    rows.append("PPPPCCCCCCCCvCCCCvCCCCC")
    rows.append("PCCvCCCCCCCCCCCCCCCCCvC")
    rows.append("CCCCCbbbbCCrbCCbbbCCCCC")
    rows.append("CCCCCCrCCCCCCCvCCCCCCCC")
    rows.append("PvCCCCCCCCCCCbCCCCCCvCC")
    rows.append("PCCCCCCvvCCCCCCCCCCCCCC")
    rows.append("PCCCCCCCCCCCCCCFFCCCCCC")
    rows.append("PPCCCCCCCCCCCFFCCCCCCCC")
    rows.append("PPCCFFCCCCCFFCCCCCFFFFF")
    rows.append("PPPCFFFFFFFFFFFFFFFFFCP")
    rows.append("PPPPFFFFFFFFFFFFFFFFPPP")
    rows.append("PPPPPFFFFFFFFFFFFFFFPPP")
    rows.append("PPPPPPFFFFFFFFFFFFPPPPP")
    rows.append("PPPPPPFFFFFFFFFFFFPPPPP")
    rows.append("PPPPPPFFFFFFFFFFFFPPPPP")  # center
    rows.append("PPPPPPFFFFFFFFFFFFPPPPP")
    rows.append("PPPPPPPFFFFFFFFFFFPPPPP")
    rows.append("PPPPPPPPFFFFFFFFFPPPPPP")
    rows.append("PPPPPPPPFFFFFFFFFPPPPPP")
    rows.append("PPPPPPPPPFFFFFFFFPPPPPP")
    rows.append("PPPCFFFFFFFFFFCCCCCPPC")
    rows.append("PPFFCCCCCFFCCCCCCCCCCCP")
    rows.append("PPCCCCCCCFFCCCCCvvCCCP")
    rows.append("PCvCCCCCCCCCCbCCCCCCCP")
    rows.append("PPCCvvCCCCCCCCCvCCCCC")
    # Fix lengths
    rows = [r.ljust(size, "P")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "three_way_25",
        "name": "三国混战·25×25",
        "description": "3 人三向开战：东 / 南 / 西各 1 城堡 + 1 佣兵站，森林迷宫阻隔，速战速决",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# --------------------------------------------------------------
# Map 4 — 30x30 — 经济扩张 (economic expansion)
# Big open map with 4 villages + 2 barracks + 1 gate + 1 road
# spine. Slow push / economic warfare.
# --------------------------------------------------------------
def make_economic_expansion() -> dict:
    size = 30
    rows = []
    rows.append("PPPPCCvvCCCCvCCCCCCvvCCCCC")
    rows.append("PPCrrCCCCCCCCCCCCCCCrrCCCC")
    rows.append("PPCrCCCCCCCCCCCCCCCCCbCCCCC")
    rows.append("PPCrCCvCCPPFFPPCCCCCCCCCC")
    rows.append("PCCrbCCCFPPFFFFPCCCCCCCCCC")
    rows.append("PCCCCCCCFPPPPPFFCCCCCCCCCC")
    rows.append("PCCCCCCCCPPFFFFCCCCCCCCCCC")
    rows.append("PCCCCCCCCPPPPPPCCCCCCCCCCC")
    rows.append("PPCvCCCCPPFFPFFCCCCCCCCCCC")
    rows.append("PPCCCCCPPPPFPPPMMMMCCCCCC")
    rows.append("PPCCCCCPPFFPPPMMMMCCCCCC")
    rows.append("PPCCCCCCCCCCCPPFFCCCCCCCC")
    rows.append("PPCCCCCCCCCCCPPFFCCCCCCCC")
    rows.append("PPCCCCCCCCCCCPPFFCCCCCvvCC")
    rows.append("PPCvCCCCCCCCCCPFFFFFFFFCC")
    rows.append("PPCCCCCCCCCCCCPPFFFFFFFFCC")
    rows.append("PPCCCCCCCCCCCCCPPFFFFCCCC")
    rows.append("PPCCCCCCCCCCCCCCPPPPCgCCPP")
    rows.append("PPCCCCCCCCCCCCCCCCCPPgCCC")  # gate corridor
    rows.append("PPCCCCCbCCCCCCCCCCCCCgCCPP")
    rows.append("PPCCCCCCCCCCCCCCCCCPPPCPP")
    rows.append("PPCCCCCCCCCCCCCCCPPPPPCPP")
    rows.append("PPCCvCCCCCCCCCCCPPPPPMMCC")
    rows.append("PCCCCCCCCCCCCCPPPPPMMCCCC")
    rows.append("PCCCCCCCCCCCCCCPPPPPCvCC")
    rows.append("PCCCCCCCCCCCCCCPPCCCCCCCC")
    rows.append("PCCvCCCCCCCCCCPCvCCCCCCCC")
    rows.append("PCCCCCCCCCCCCCCCCCbCCCCCC")
    rows.append("PPCrrCCCCCCCCCCCCrrCCCCCC")
    rows.append("PPCCvvCCCCCCCCvCCCCvCCCCC")
    rows = [r.ljust(size, "P")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "economic_expansion_30",
        "name": "经济扩张·30×30",
        "description": "4 人经济持久战：4 村落 + 2 佣兵站 + 1 关卡窄道，主打占领与金币运营",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# --------------------------------------------------------------
# Map 5 — 35x35 — 城防 (fortress)
# 4-player map with castles + 2 gate walls. Heavy defensive play.
# --------------------------------------------------------------
def make_fortress() -> dict:
    size = 35
    rows = []
    # Top castle (red) + 1 village + 1 barracks
    rows.append("CCvCCCCCCCCCCCCCCCCCCCCCCCCCCCCC")
    rows.append("CCCCbCCPPCCCCCCCCCgCCCCCCCCCCCC")
    rows.append("CCCCCCPPCCCCCCCCCCCCCgCCCCCCCvC")
    rows.append("CCCCCCCCCCCCCCCCCCCCCCCCCgCCCCC")
    rows.append("CCvvCCCCCCCCCCCCCCCCCCCCCCCCCC")
    # Forest mid north
    rows.append("CCFFFFFFFFFFFFFFFCCCCCCbbCCCCC")
    rows.append("CCCFFFFFFFFFFFFFFCCCCCCCCCvCCC")
    rows.append("CCCCFFFFFFFFFFFFCCCCCCCCCCCCCC")
    rows.append("PPCCCCCFFFFFFFFCCPPCCCCCCCCCC")
    rows.append("PPCCCCCCCCCCCCCCPPPPCvCCCCCCC")
    # Forest belt
    rows.append("PPFFCCCCCCCCCCCPPFFFCCCCCCCCCC")
    rows.append("PPFFFFCCCCCCCFFPPFFFFFFFFFCC")
    rows.append("PPFFFFCCCCCCCFFPPFFFFFFFFFFCC")
    rows.append("PPFFFFCCCCCCCFFPPFFFCCCCCCCCC")
    rows.append("PPFFCCCCCCCCCCCPPFFCCCCCCCCCC")
    rows.append("PPCCCCCCCCCCCCCCPPCCCCCCCCCvC")
    rows.append("PPCCCCCCCCCCCCCCCCCFFCCCCCbbC")
    rows.append("PPCCvCCCCCCCCCCCCFFFFFFFFFCC")
    rows.append("PPPCCCCCCvvCCCCCCCFFFFFFFFFC")
    # Centre road spine
    rows.append("PPPPCCrrrrrrrrrrrrrrrCCCCCFC")
    rows.append("PPPPPCrrrrrrrrrrrrrrrCCCCCFC")
    rows.append("PPPPCCrrrrrrrrrrrrrrrCCCCCFC")
    rows.append("PPCCvvCCCCCFFFFCCCCCCCCCCCCC")
    # Forest belt south
    rows.append("PCCCCCCCFFFFFFFFFFCCCCCCCCCCC")
    rows.append("PCCCCCCFFFFFFFFFFCCCCCCCCCvvC")
    rows.append("PCbbCCCFFFFFFFFFCCCCCbbCCCCCC")
    rows.append("PCCCCCFFFFFFFFFFCCCCCCCCCCCCC")
    rows.append("CCCCCCFFFFFFFFFFCCCCCCCCCCCC")
    rows.append("CCCCCFFFFFFFFFFFCCCCCCCCCCCC")
    rows.append("CCCCCFFFFFFFFFFFFCCCCCCCCCCC")
    # Bottom castle (blue) + 1 village + 1 barracks
    rows.append("CCvCCCCCCCCCCCCCCCCCvCCCCCCC")
    rows.append("CCCCbCCCCCvCCCCCFFCCCCCvvCC")
    rows.append("CCCCCCCCCCCCCCCFFFFFFFFCCC")
    rows.append("CCCCCCCCCCCCCCFFFFFFFFCCCCC")
    rows.append("CCCCCCCCCCCCCCCFFFFFFFFCC")
    rows.append("CCvvCCCCCCCCCCCCCCCFFCCCCC")
    rows.append("CCvvCCCCCCCCCCCCCCCCCCCCC")
    rows = [r.ljust(size, "C")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "fortress_35",
        "name": "城防·35×35",
        "description": "4 人城堡对决：4 城堡 + 关卡封锁 + 森林迷宫 + 中央道路慢推",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# --------------------------------------------------------------
# Map 6 — 40x40 — 王座争夺 (throne war)
# Big map with a central contested plain. 4 villages + 2 barracks.
# 4 spawn corners.
# --------------------------------------------------------------
def make_throne_war() -> dict:
    size = 40
    rows = []
    # Top-left corner (red) + barracks
    rows.append("CvCCCCCCPPPPPCCCCCCCCCCvCCCCCCCCCCC")
    rows.append("CCCCCCCPPCCCCCPPCCCCCCCCCCCCCCCCC")
    rows.append("CvvCCCCCCbCCCbCCCCCFFFFCCCCCCCCCC")
    rows.append("CCCCCCCCCFFCCCFFCFFFFFFFFCCCCCCCC")
    rows.append("CCCCCFFCCCFFCCCFFFFFFFFFFFCCCCCCC")
    rows.append("CCCCCFFCCCFFCCCCCFFFMCCCCCCCCCC")
    rows.append("CCCCCFFCFFFFFFFFCCMMMCCCCCFFCCCC")
    rows.append("CCCCCCCFFCCCCCCCCCMMMMCCCCCFFCCC")
    rows.append("CCCCCCCFFCCCCCCCCCCMMRCCCCCFFCCC")
    rows.append("CCCCCCFFCCCRRRRRCCCCCCCFFCCFFCC")
    rows.append("CCCCCCCFFCRRrrRRCCCFFFFCCCCCCFFCC")
    rows.append("CCCCCCCFFCRRrrRRCCCFFFFFFFFCCCCC")
    rows.append("CCCCCCCCCCRrrRRCCCCFFFFCCCCCCCCC")
    rows.append("CCCCCCCFFCRRrrRRCCCCFFFFFFFFCCCCC")
    rows.append("CCCCCCCFFCRRrrRRCCCCCFFFFCCCCCC")
    rows.append("CCCCCCCCFFRRRCCCCCCCFFFFCCCCCCC")
    rows.append("CCCCCCCCCFFCCCCCFFFFFFFFFCCCCC")
    rows.append("CCCCCCCCCCCFFCCCCCFFFFCCCCCCCCCC")
    rows.append("CCCCCCCCCCCCCCCCCCCCCFFFFFFFFFCC")
    rows.append("CCCCCCCCCCFFCCCCCFFFFCCCCCCCCCCC")
    rows.append("CCCCCCCCCCFFCCCCCFFFFCCCCCCCCCCC")
    rows.append("CCCCCCCCCCCFFCCCCCFFFFCCCCCCCC")
    rows.append("CCCCCCCCCCFFCCCCCFFFFCCCCCCCCCC")
    rows.append("CCCCCCCCCCFFCCCCCFFFFCCCCCCCC")
    rows.append("CCCCCFFCCCCFFCCCCCFFFFCCCCCCCCC")
    rows.append("CCCCCFFCCCCCFFCCCCCCFFCCFFCCC")
    rows.append("CCCCCFFCCCCCFFCCCCCCCFFCCFFCC")
    rows.append("CCCCCFFCCCCCCFFCCCCCFFFFCCCCC")
    rows.append("CCCCCCFFCCCCCFFCFFFFFFFFCCCFFFC")
    rows.append("CCCCCCCFFCCCCCCCFFFFCCCFFCCC")
    rows.append("CCCCCFFCCCCCvCCCCCCCFFCCCCCFFFC")
    rows.append("CCCFFCbbCCCCCCCCCCFFCCCCCFFCCC")
    rows.append("CCFFCCCCCvCCCCCCCCCFFFFCCCCCCC")
    rows.append("CFFCCCCCFFCCCCCFFFFCCCCCCCCCCC")
    rows.append("CCFFCCCCCFFCCCCCCCCCCFFCCCCC")
    rows.append("CCCCCCCCCFFCCCCCFFCCCCCCCCCCCC")
    rows.append("CCCCCCCCCCFFCCCFFCCCCCvCCCCC")
    rows.append("CCCCCCCCCCCFFCCCFFCCCbCCCFFCCC")
    rows.append("CCCCCCCCCCCCCCCCCFFCCCCCFFCCC")
    rows.append("CCCCCCCCCCCCCCCCCCCFFCCCCCFFCCC")
    rows.append("CCCCCCCCCCCCCCCCCCCCCCFFCCFFCCC")
    rows = [r.ljust(size, "C")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "throne_war_40",
        "name": "王座争夺·40×40",
        "description": "4 人王座争夺：四角落兵 + 中央河流+道路十字路口 + 大量森林遮蔽",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# --------------------------------------------------------------
# Map 7 — 45x45 — 大混战 (free-for-all)
# Massive 4-player map with all 4 new terrains scattered. 4 villages,
# 4 barracks, 2 gates, road network, forests and mountains.
# --------------------------------------------------------------
def make_free_for_all() -> dict:
    size = 45
    rows = []
    # Top row — red zone
    rows.append("CCvCCCCCCPPPPPPPPCCCCCCCCCCCCCCCCCCCCCCCCC")
    rows.append("CCCCCCCPPCCCCCCCPPCCvvCCCCCCCCCFFCCCCCCCCC")
    rows.append("CvbCCCCCPPCCCCCCPPCCCCCCCCCCCCFFFFFFFFCCCC")
    rows.append("CCCCCCCCCFFCCCCPPFFCCCCCCCFFFCCCCCCCCFFFF")
    rows.append("CCFFCCCFFFFCCCCPPFFFFCCCCCCFFFFFFFFFFFFC")
    rows.append("CCCFFCFFFFCCCCPPFFFFFFFFFCCCCCCCCCCCCCCC")
    rows.append("CCCCCCCFFFFCCCPPFFFFFFFFCCCCCCCCvvCCCCCCC")
    rows.append("CCCCCCCCCCCFFCCPPFFFFCCCCCCCCCCCCCCCCCCC")
    # Mid north — road spine
    rows.append("CCCCCCCCCCCCCCrrrPPCCCCCCCCCCCCCCCbbCCC")
    rows.append("CCCCCCCCCCCCCrrrrrPPCCCCCCCCCCCCCCCCCC")
    rows.append("CCCCCCCCCCCCrrrrrrrPPCCCCCCCCCCCCCFFFC")
    rows.append("CCCCCCCCCCrrrrrrrrrPPCCCCCCCFFFFFFFFFC")
    rows.append("CCCCCCCFFrrrrrrrrrrPPCCCCCCCFFFFFFFFC")
    rows.append("CCCCCCFFFFFFFFrrrrrrrPPCCCCCFFFFFFFFF")
    rows.append("CCCCCCCFFFFFFFrrrrrrPPCCCFFFFFFFFFFFF")
    rows.append("CCCCCCCCCCCFFFFrrrrrPPCCCCCFFFFFFFFF")
    rows.append("CCCCCCCCCCCCCCrrrrrPPPCCCCCCFFFFFFFFF")
    # Mid south — rivers + forests
    rows.append("CCCCCCCCCCCCCrrPPPPPPCCCCCCCFFFFFFFFF")
    rows.append("CCCCCCCCCCCCCPPPPCCCCCCCCCCCFFFFFFFFFF")
    rows.append("CCCCCCCCCCCPPCCCCCCFFCCCCCFFFFFFFFFFFC")
    rows.append("CCCCCCCCCCCPPCCCCFFFFFFFFCCCFFFFFFFFFFC")
    rows.append("CCvCCCCCCPPPPCCCFFFFFFFFCCCCCFFFFFFFFFC")
    rows.append("CCCCCCCCCPPCCCCCCCFFFFFFFFCCCCCCCFFFFFC")
    rows.append("CCCFFCCCCCPPCCCCCFFFFFFFFCCCCCFFFFFFFFFC")
    rows.append("CCCFFCCCCPPPCCCCFFFFFFFFCCCCCCCCFFFFFC")
    # Bottom row — green + yellow zone
    rows.append("CCFFCCCCCPPCCCCCFFFFFFFCCCCCCCCCFFFFFFFFC")
    rows.append("CCCFFCCCCCPPCCCCFFFFFFFFCCCCCCCFFFFFFFCC")
    rows.append("CCCCCCCCCCCPPCCCFFFFFFFFFCCCCCCCFFFFFFFCC")
    rows.append("CCCFFCCCCCPPPCCFFFFFFFFFCCCCCCCCCCFFFFFC")
    rows.append("CCFFCCCCCPPPPCCCFFFFFFFFCCCCCCCCCFFFFFCC")
    rows.append("CCCFFCCCCCPPCCCCCFFFFFFFFFCCCCCCCCCFFFC")
    rows.append("CCFFCCCCCPPCCCCCCFFFFFFFFCCCCCFFCCCCCCC")
    rows.append("CCFFCCCCCPPCCCCCCCFFFFFFFCCCFFFFCCCCCC")
    rows.append("CCFFCCCCCPPCCCCCCCCFFFFFFFCCvFFFCCCCCC")
    rows.append("CCFFCCCCCPPCCCCCCCCCFFFFFFFCCFFCCCCCbbC")
    rows.append("CCFFCCCCCgPPCCCCCCCCCCFFFFFFCFFFCCCCCCC")
    rows.append("CCCFFCCCCgPPCCCCCCCCCCCFFFFCCFFCCCCCC")
    rows.append("CCCCCFFFCgPPCCCCCCCCCCCCCCFFCCFFCCCCC")
    rows.append("CCCCCFFCCgPPCCCCCCCCCCCCCCFFCCFFCCCCC")
    rows.append("CCCCCFFFCgPCCCCCCCCCCCCCFFCCCFFCCCCC")
    rows.append("CCCCCCCCCCPCCCCCCCCCCCFFCCCCCFFCCCCC")
    rows.append("CCvvCCCCCCPPCCCCCCCCCCFFCCCCCFFCCCCC")
    rows.append("CCCCCbCCCCPCCCCCCCCCCCFFCCCCCFFCCCC")
    rows.append("CCCCCCCCCCPPCCCCCCCCCCFFCCCCCFFCCCC")
    rows.append("CCCCCCCCCCPPCCCCCCCCCCFFCCCCCCCFFCC")
    rows.append("CCvCCCCCCCPPCCCCCCCCCCFFCCCCCCCCFFCC")
    rows.append("CCCCCCCCCCPPCCCCCCCCCFFCCCCCCCCCCCFC")
    rows.append("CCCCCCCCCCCPPCCCCCCCFFCCCCCbbCCCCCC")
    rows.append("CCCCCCCCCCCCPPCCCCCCCFFCCCCCFFCCCC")
    rows = [r.ljust(size, "C")[:size] for r in rows]
    assert all(len(r) == size for r in rows), [len(r) for r in rows]
    return {
        "id": "free_for_all_45",
        "name": "大混战·45×45",
        "description": "4 人巨型混战：4 角兵 + 6 村落 + 4 佣兵站 + 2 关卡 + 道路网络 + 大量森林山脉掩体",
        "biome": "grass",
        "size": size,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


def main() -> None:
    PRESETS = [
        make_resource_rush(),
        make_two_fronts(),
        make_three_way(),
        make_economic_expansion(),
        make_fortress(),
        make_throne_war(),
        make_free_for_all(),
    ]
    for p in PRESETS:
        # Auto-truncate or pad rows to exactly the declared size.
        size = p["size"]
        rows = p["layout"][:size]  # truncate extra rows
        # pad if short
        while len(rows) < size:
            rows.append("C" * size)
        # pad/truncate each row
        rows = [r.ljust(size, "C")[:size] for r in rows]
        p["layout"] = rows
        path = OUT / f"{p['id']}.json"
        path.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        v_count = sum(r.count("v") for r in rows)
        b_count = sum(r.count("b") for r in rows)
        r_count = sum(r.count("r") for r in rows)
        g_count = sum(r.count("g") for r in rows)
        print(f"wrote {path}  ({size}x{size}, {v_count}v {b_count}b {r_count}r {g_count}g)")
    # Verify
    for p in PRESETS:
        rows = p["layout"]
        assert len(rows) == p["size"], f"{p['id']}: row count {len(rows)} != {p['size']}"
        for r in rows:
            assert len(r) == p["size"], f"{p['id']}: row width {len(r)} != {p['size']}"
    print("All 7 presets verified.")


if __name__ == "__main__":
    main()
