"""Generate the P2.3 mission presets (Reach + Defend).

These are designed to be loaded by the standard _load_map_presets
loader (game/app/game_logic.py). The loader already auto-truncates /
pads layouts to the declared size, so each generator just needs to
declare a `size` and emit that many rows of `size` chars.

Maps produced:

  Reach:
    reach_heaven_25    25x25  reach  (2, 2)  -- 1v1 速战
    reach_corner_30     30x30  reach  (0, 0)  -- 2p 抢角
    reach_corner_40     40x40  reach  (0, 0)  -- 4p 抢角
  Defend:
    defend_15_turns_20 20x20  defend 15 rounds
    defend_25_turns_30 30x30  defend 25 rounds
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "game" / "maps"
OUT.mkdir(parents=True, exist_ok=True)


def _char_grid(rows: list[str], size: int) -> list[str]:
    """Pad / truncate each row to `size`, drop extra rows, pad short ones."""
    out = []
    for r in rows[:size]:
        out.append(r.ljust(size, "P")[:size])
    while len(out) < size:
        out.append("C" * size)
    return out


# 25x25 Reach — target the north-east corner; 2 castles 1v1
def make_reach_heaven_25() -> dict:
    size = 25
    rows = _char_grid([
        "PPPPPPPPPPPPPPPPPPPPPPPPP",
        "PvCCCCCCCCCCCCCCCCCCCCCC",
        "PCCCCCCCCCCCCCCCCCCCCCCC",
        "PCCCCCCCCCCbCCCCCCCCCCCC",
        "PCCCCCCCCCCCCCCCCCCCCCCC",
        "PCCCCCCCCCCCCCCCCCCCCFFF",
        "PCCCCCCCCCCCCCCCCCCCFFFF",
        "PCCCCCCCCCCCCCCCCCCFFFFF",
        "PCCCCCCCCCCCCCCCCCCFFFFF",
        "PCCCCCCCCCCCCCCCCCCFFFFF",
        "PPCCCCCCCCCCCCCCCCFFFFFF",
        "PFFCCCCCCCCCCCCCCCFFFFFF",
        "PFFCCCCCCCCCCCCCCCFFFFFF",
        "PFFCCCCCCCCCCCCCCFFFFFFF",
        "PPFFCCCMMMMCCCCFFFFFFFFF",
        "PFFCCCMMMMCCCCFFFFFFFFFP",
        "PFFCCCMMMMCCCCFFFFFFFFFP",
        "PFFCCCMMMMCCCCFFFFFFFFFP",
        "PFFCCCMMMMCCCCFFFFFFFFFP",
        "PFFCCCCCCCCCCCFFFFFFFFFF",
        "PPCCCCCCCCCCCCCFFFFFFFFFF",
        "PPCvCCCCCCCCCCFFFFFFFFFF",
        "PCCCCCCCCCCCCCFFFFFFFFFP",
        "PCCCCCCCCCCCCCCCCCCCCCC",
        "PPPPPPPPPPPPPPPPPPPPPPPPP",
    ], size)
    return {
        "id": "reach_heaven_25",
        "name": "抵达天堂·25×25",
        "description": "Reach 模式：单位冲到对方城堡后角即胜",
        "biome": "grass",
        "size": size,
        "win_condition": "reach",
        "reach_tile": {"x": 2, "y": 2},  # NW corner of the opponent's HQ
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# 30x30 Reach — target the corner; 4 corners each with a castle cluster
def make_reach_corner_30() -> dict:
    size = 30
    rows = _char_grid([
        "vCCCCCCCCCCCCCCCCCCCCCCCvCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCbCCCCCFFFFFFFFFFCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFCCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFCCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFCCCCCCCC",
        "CCCCCCCCCCCCFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCCFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCCCRRRRRRCCCCCCCCCC",
        "CCCCCCCCCCCCRRRRRRRCCCCCCCCCC",
        "CCCCCCCCCCCCCFFCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCFFCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCFFCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCFFCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCFFCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCFFCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCFFCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCFFCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCFFCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCFF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCb",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "vCCCCCCCCCCCCCCCCCCCCCCCCvCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    ], size)
    return {
        "id": "reach_corner_30",
        "name": "抢角·30×30",
        "description": "Reach 模式：冲到 (0,0) 即胜（4 角各 1 城堡）",
        "biome": "grass",
        "size": size,
        "win_condition": "reach",
        "reach_tile": {"x": 0, "y": 0},
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# 40x40 Reach — bigger 4-player corner reach
def make_reach_corner_40() -> dict:
    size = 40
    rows = _char_grid([
        "vCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCbCCCCCFFFFFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCFFFFFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCCFFFFFFFFFFFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCFFFFFFFFFFFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCCRRRRRRRRRRRRRRRCCCCCCCCC",
        "CCCCCCCCCCCCCRRRRRRRRRRRRRRCCCCCCCCC",
        "CCCCCCCCCCCCCCRRRRRRRRRRRRRCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCCCCCCFFFFFFFFFFFFCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCFFFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCFFFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCFFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCFFFFFFFFCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCFFFFFFFFCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCFFFFFFFFFCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCFFFFFFFFC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCFFFFFFFF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCFFFFFF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCFFFFF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCFFFF",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "vCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCvCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "vCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCvCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    ], size)
    return {
        "id": "reach_corner_40",
        "name": "抢角·40×40",
        "description": "Reach 模式：4 人抢 (0,0)，节奏快、有大量森林屏障",
        "biome": "grass",
        "size": size,
        "win_condition": "reach",
        "reach_tile": {"x": 0, "y": 0},
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


# ============================================================
# Defend presets
# ============================================================

def make_defend_15_turns_20() -> dict:
    """20x20 Defend 15 rounds. 2 castles 1v1, 4 villages + 2 barracks
    for income, road network for fast movement. The attacker has
    to wipe the defender in 15 rounds or the defender wins."""
    size = 20
    rows = _char_grid([
        "CCvCCCCCCCCCCCCCCvCC",
        "CCCbCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCC",
        "CCCPPPPPPPPPPPPCCCC",
        "CCCPrrrrrrrrrrPCCCC",
        "CCCPrCCCCCCCCrPCCCC",
        "CCCPrCFFFFFFFCCrPCC",
        "CCCPrCFFFFFFFFCrPC",
        "CCCPrCFFFFFFFCCrPCC",
        "CCCPrCCCCCCCCrPCCCC",
        "CCCPrCFFFFFFFCCrPCC",
        "CCCPrCFFFFFFFCCrPCC",
        "CCCPrCCCCCCCCrPCCCC",
        "CCCPrrrrrrrrrrPCCCC",
        "CCCPPPPPPPPPPPPCCCC",
        "CCCCCCCCCCCCCCCCCCC",
        "CCCbCCCCCCCCCCCCCCC",
        "CCvCCCCCCCCCCCCCCvCC",
        "CCCCCCCCCCCCCCCCCCC",
        "PPPPPPPPPPPPPPPPPPP",
    ], size)
    return {
        "id": "defend_15_turns_20",
        "name": "坚守15回合·20×20",
        "description": "Defend 模式：2 人对战，守方撑过 15 回合即胜",
        "biome": "grass",
        "size": size,
        "win_condition": "defend",
        "defend_turns": 15,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


def make_defend_25_turns_30() -> dict:
    """30x30 Defend 25 rounds. 4 castles 4 players, mountains
    block the middle, road network connects corners."""
    size = 30
    rows = _char_grid([
        "CCvCCCCCCCCCCCCCCCCCCvCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCbCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCPPPPPPPPPPPPPPCCCCCCCCCC",
        "CCCPrrrrrrrrrrrPCCCCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCCCCCCCCCCCCrPCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCFFFFFFFFFFrPCCCCCCCC",
        "CCCPrCCCCCCMMMMCrPCCCCCCCC",
        "CCCPrCCCCCCMMMMCrPCCCCCCCC",
        "CCCPrCCCCCCMMMMCrPCCCCCCCC",
        "CCCPrCCCCCCMMMMCrPCCCCCCCC",
        "CCCPrCCCCCCCCCCCCrPCCCCCCCC",
        "CCCPrrrrrrrrrrrrPCCCCCCCCCC",
        "CCCPPPPPPPPPPPPPPCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCbCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCvCCCCCCCCCCCCCCCCCCvCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCbCCCCCCCCCCCCCCCCCCCCCCC",
        "CCCCCCCCCCCCCCCCCCCCCCCCCCC",
        "CCvCCCCCCCCCCCCCCCCCCvCCCCC",
    ], size)
    return {
        "id": "defend_25_turns_30",
        "name": "坚守25回合·30×30",
        "description": "Defend 模式：4 城堡，撑过 25 回合即胜",
        "biome": "grass",
        "size": size,
        "win_condition": "defend",
        "defend_turns": 25,
        "chars": {
            "P": "plain", "F": "forest", "M": "mountain", "R": "river", "C": "castle",
            "v": "village", "b": "barracks", "r": "road", "g": "gate",
        },
        "layout": rows,
    }


def main() -> None:
    PRESETS = [
        make_reach_heaven_25(),
        make_reach_corner_30(),
        make_reach_corner_40(),
        make_defend_15_turns_20(),
        make_defend_25_turns_30(),
    ]
    for p in PRESETS:
        path = OUT / f"{p['id']}.json"
        path.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        n_v = sum(r.count("v") for r in p["layout"])
        n_b = sum(r.count("b") for r in p["layout"])
        n_c = sum(r.count("C") for r in p["layout"])
        reach = p.get("reach_tile", "-")
        defend = p.get("defend_turns", "-")
        print(f"wrote {path}  ({p['size']}x{p['size']}, win={p['win_condition']}, "
              f"reach={reach}, defend={defend}, {n_v}v {n_b}b {n_c}C)")
    # Verify
    for p in PRESETS:
        rows = p["layout"]
        assert len(rows) == p["size"]
        for r in rows:
            assert len(r) == p["size"]
    print("All mission presets verified.")


if __name__ == "__main__":
    main()
