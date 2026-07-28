#!/usr/bin/env python3
"""
score_maps_wizard.py — interactive scoring wizard for generated maps.

学长 2026-07-22:用户对自动生成地图打分 + 点评。流程:
  1. 扫描 game/maps/ 下的 preset JSON(或 map_previews/ 下的 PNG)。
  2. 弹 tkinter 窗口,显示一张地图 + 机器分。
  3. 用户拖 0-10 滑块 + 写评论。
  4. 上一张 / 跳过 / 保存下一张 / 退出。
  5. 写入 tools/map_scores.jsonl(每行 {image_id, score, comment, machine, ts})。

支持续评:再次运行会跳过已评过的图。

用法
----
    # 评 map_previews/ 下的所有 PNG
    python tools/score_maps_wizard.py

    # 评特定目录
    python tools/score_maps_wizard.py --maps-dir game/maps

    # 改输出文件
    python tools/score_maps_wizard.py --out tools/my_scores.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageTk = None  # type: ignore


# ============================================================
# 路径与默认值
# ============================================================

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_MAPS_DIR = ROOT / "game" / "maps"
DEFAULT_PREVIEWS_DIR = ROOT / "map_previews"
DEFAULT_OUT = HERE / "map_scores.jsonl"

# 中国常见的舒适配色
BG = "#f4f4f0"
FG = "#222"
ACCENT = "#2266cc"
OK = "#22aa66"
WARN = "#cc8800"


# ============================================================
# 工具
# ============================================================


def load_existing_scores(path: Path) -> Dict[str, Dict]:
    """读取 jsonl,返回 {image_id: {score, comment, ...}}。"""
    out: Dict[str, Dict] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[rec["image_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def append_score(path: Path, record: Dict) -> None:
    """追加一条 jsonl 记录。"""
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def list_map_ids(maps_dir: Path, previews_dir: Path) -> List[str]:
    """扫描所有 *_Np.json 文件,按字母排序。"""
    ids = sorted(
        p.stem for p in maps_dir.glob("*.json")
        if p.stem.endswith(("2p", "3p", "4p"))
        and not p.stem.startswith(("balanced_", "realistic_", "test_"))
    )
    return ids


def load_map_meta(maps_dir: Path, image_id: str) -> Dict:
    """读 preset JSON 拿 meta(name, biome, machine_score 等)。"""
    path = maps_dir / f"{image_id}.json"
    if not path.exists():
        return {"id": image_id}
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return {"id": image_id}


def get_machine_score(maps_dir: Path, image_id: str) -> Optional[float]:
    """读 preset JSON 里的 target_share 重新算 S7 当机器参考分。"""
    meta = load_map_meta(maps_dir, image_id)
    target_share = meta.get("target_share")
    if not target_share:
        return None
    # 简单估算:fitness 与 target_share 不直接相关,需要从 quality 读
    # 这里简化:直接读 score 字段(preset 自带)
    return None  # 由 wizard 内部用 check_map_constraints.py 算


# ============================================================
# 主窗口
# ============================================================


class ScoringWizard:
    """tkinter 交互式打分向导。

    布局:
      顶部:进度文字 (3 / 39)
      中部:地图 PNG (用 PIL.ImageTk 显示)
      右侧/底部:slider + 评论 + 按钮
    """

    def __init__(
        self,
        map_ids: List[str],
        maps_dir: Path,
        previews_dir: Path,
        out_path: Path,
    ) -> None:
        if tk is None or Image is None:
            raise RuntimeError(
                "score_maps_wizard requires tkinter and Pillow"
            )

        self.map_ids = map_ids
        self.maps_dir = maps_dir
        self.previews_dir = previews_dir
        self.out_path = out_path
        self.existing = load_existing_scores(out_path)
        # Filter out already-scored ones (resume support)
        self.queue = [mid for mid in map_ids if mid not in self.existing]
        self.idx = 0  # index within self.queue
        self.total_new = len(self.queue)
        self.total_all = len(map_ids)

        self.root = tk.Tk()
        self.root.title("地图打分向导 — BattleBlitz 地图评价")
        self.root.configure(bg=BG)
        self.root.geometry("900x780")

        # ============================================================
        # UI 元素
        # ============================================================

        # 顶部进度
        self.progress_var = tk.StringVar()
        top = tk.Frame(self.root, bg=BG, pady=8)
        top.pack(fill="x")
        tk.Label(
            top, textvariable=self.progress_var,
            font=("Microsoft YaHei", 12), bg=BG, fg=FG,
        ).pack(side="left", padx=12)
        tk.Label(
            top, text=f"剩余 {self.total_new} / 总 {self.total_all} 张",
            font=("Microsoft YaHei", 10), bg=BG, fg="#666",
        ).pack(side="left", padx=8)

        # 地图显示
        self.image_label = tk.Label(self.root, bg=BG)
        self.image_label.pack(pady=8, expand=True)

        # 信息条:地图 meta
        self.meta_var = tk.StringVar()
        meta_bar = tk.Frame(self.root, bg="#eeeee8")
        meta_bar.pack(fill="x", padx=12)
        tk.Label(
            meta_bar, textvariable=self.meta_var,
            font=("Microsoft YaHei", 10), bg="#eeeee8", fg=FG, anchor="w",
            padx=8, pady=6, justify="left",
        ).pack(fill="x")

        # ============================================================
        # 评分区(slider + 数字)
        # ============================================================
        score_frame = tk.Frame(self.root, bg=BG, pady=8)
        score_frame.pack(fill="x", padx=12)
        tk.Label(
            score_frame, text="评分(0=烂,10=完美):",
            font=("Microsoft YaHei", 11), bg=BG, fg=FG,
        ).pack(side="left", padx=(0, 8))

        self.score_var = tk.IntVar(value=5)
        self.score_label_var = tk.StringVar(value="5")
        scale = ttk.Scale(
            score_frame, from_=0, to=10, orient="horizontal",
            variable=self.score_var, length=400,
            command=lambda v: self.score_label_var.set(f"{int(float(v))}"),
        )
        scale.pack(side="left", padx=8)
        tk.Label(
            score_frame, textvariable=self.score_label_var,
            font=("Consolas", 16, "bold"), bg=BG, fg=ACCENT, width=3,
        ).pack(side="left", padx=8)

        # ============================================================
        # 评论框
        # ============================================================
        tk.Label(
            self.root, text="点评(选填,直接说问题):",
            font=("Microsoft YaHei", 11), bg=BG, fg=FG, anchor="w",
        ).pack(fill="x", padx=12)
        self.comment_text = tk.Text(
            self.root, height=4, font=("Microsoft YaHei", 10),
            bg="white", fg=FG, relief="solid", bd=1,
        )
        self.comment_text.pack(fill="x", padx=12, pady=4)

        # ============================================================
        # 按钮区
        # ============================================================
        btn_frame = tk.Frame(self.root, bg=BG, pady=8)
        btn_frame.pack(fill="x", padx=12)
        tk.Button(
            btn_frame, text="← 上一张",
            font=("Microsoft YaHei", 10), bg="#ddd", fg=FG,
            command=self._on_prev, width=10,
        ).pack(side="left", padx=4)
        tk.Button(
            btn_frame, text="跳过(不评)",
            font=("Microsoft YaHei", 10), bg="#eee", fg="#666",
            command=self._on_skip, width=10,
        ).pack(side="left", padx=4)
        tk.Button(
            btn_frame, text="保存下一张 →",
            font=("Microsoft YaHei", 11, "bold"), bg=OK, fg="white",
            command=self._on_save_next, width=14,
        ).pack(side="right", padx=4)
        tk.Button(
            btn_frame, text="保存退出",
            font=("Microsoft YaHei", 10), bg=WARN, fg="white",
            command=self._on_save_exit, width=10,
        ).pack(side="right", padx=4)

        # 键盘快捷键
        self.root.bind("<Right>", lambda e: self._on_save_next())
        self.root.bind("<Left>", lambda e: self._on_prev())
        self.root.bind("<Escape>", lambda e: self._on_save_exit())
        # Ctrl+S = save & exit
        self.root.bind("<Control-s>", lambda e: self._on_save_exit())

        # 显示第一张
        self._show_current()

    # ============================================================
    # 操作
    # ============================================================

    def _current_id(self) -> Optional[str]:
        if self.idx < 0 or self.idx >= len(self.queue):
            return None
        return self.queue[self.idx]

    def _show_current(self) -> None:
        image_id = self._current_id()
        if image_id is None:
            self._on_queue_done()
            return

        # 进度文字
        self.progress_var.set(f"进度:{self.idx + 1} / {len(self.queue)}    当前:{image_id}")

        # 加载 PNG
        png_path = self.previews_dir / f"{image_id}.png"
        if png_path.exists():
            try:
                img = Image.open(png_path)
                # 缩放到窗口宽度
                max_w = 850
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize(
                        (max_w, int(img.height * ratio)),
                        Image.Resampling.LANCZOS,
                    )
                photo = ImageTk.PhotoImage(img)
                self.image_label.configure(image=photo, text="")
                self.image_label.image = photo  # 防止被 GC
            except Exception as e:
                self.image_label.configure(
                    image="", text=f"加载图片失败:{e}",
                    fg="red", font=("Microsoft YaHei", 12),
                )
        else:
            self.image_label.configure(
                image="", text=f"未找到 PNG:{png_path}",
                fg="red", font=("Microsoft YaHei", 12),
            )

        # Meta 信息
        meta = load_map_meta(self.maps_dir, image_id)
        lines = [
            f"id: {image_id}",
            f"name: {meta.get('name', '?')}",
            f"size: {meta.get('size', '?')}  ·  rec_p: {meta.get('recommended_players', '?')}  ·  biome: {meta.get('biome', '?')}",
            f"style: {meta.get('style', '?')}  ·  category: {meta.get('category', '?')}  ·  objective: {meta.get('objective', '?')}",
        ]
        target = meta.get("target_share", {})
        if target:
            tparts = ", ".join(f"{k}:{int(v*100)}%" for k, v in target.items())
            lines.append(f"target_share: {tparts}")
        self.meta_var.set("\n".join(lines))

        # 重置评分控件
        prev = self.existing.get(image_id)
        if prev:
            self.score_var.set(int(prev.get("score", 5)))
            self.score_label_var.set(str(int(prev.get("score", 5))))
            self.comment_text.delete("1.0", "end")
            self.comment_text.insert("1.0", prev.get("comment", ""))
        else:
            self.score_var.set(5)
            self.score_label_var.set("5")
            self.comment_text.delete("1.0", "end")

    def _save_current(self) -> None:
        """把当前评分写入 jsonl。"""
        image_id = self._current_id()
        if image_id is None:
            return
        score = int(self.score_var.get())
        comment = self.comment_text.get("1.0", "end").strip()
        meta = load_map_meta(self.maps_dir, image_id)
        record = {
            "image_id": image_id,
            "score": score,
            "comment": comment,
            "style": meta.get("style"),
            "size": meta.get("size"),
            "recommended_players": meta.get("recommended_players"),
            "ts": int(time.time()),
        }
        # 如果 jsonl 里已有同 image_id 的旧记录,删掉再 append
        # (避免重复打分时 jsonl 里有两条)
        if image_id in self.existing:
            # Rewrite file without this id
            tmp = self.out_path.with_suffix(".tmp")
            with open(self.out_path, encoding="utf-8") as fp_in, \
                 open(tmp, "w", encoding="utf-8") as fp_out:
                for line in fp_in:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("image_id") != image_id:
                            fp_out.write(line)
                    except json.JSONDecodeError:
                        continue
                fp_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            tmp.replace(self.out_path)
            self.existing[image_id] = record
        else:
            append_score(self.out_path, record)
            self.existing[image_id] = record

    def _on_prev(self) -> None:
        if self.idx > 0:
            self.idx -= 1
            self._show_current()

    def _on_skip(self) -> None:
        if self.idx < len(self.queue) - 1:
            self.idx += 1
            self._show_current()
        else:
            self._on_queue_done()

    def _on_save_next(self) -> None:
        self._save_current()
        if self.idx < len(self.queue) - 1:
            self.idx += 1
            self._show_current()
        else:
            self._on_queue_done()

    def _on_save_exit(self) -> None:
        self._save_current()
        self.root.destroy()

    def _on_queue_done(self) -> None:
        messagebox.showinfo(
            "打分完成",
            f"所有地图都评完了!\n\n共 {len(self.existing)} / {self.total_all} 张已评\n输出:{self.out_path}",
        )
        self.root.destroy()

    # ============================================================
    # 启动
    # ============================================================

    def run(self) -> None:
        self.root.mainloop()


# ============================================================
# CLI
# ============================================================


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument(
        "--maps-dir", type=Path, default=DEFAULT_MAPS_DIR,
        help=f"preset JSON 目录(默认 {DEFAULT_MAPS_DIR})",
    )
    p.add_argument(
        "--previews-dir", type=Path, default=DEFAULT_PREVIEWS_DIR,
        help=f"PNG 预览目录(默认 {DEFAULT_PREVIEWS_DIR})",
    )
    p.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"评分输出文件(默认 {DEFAULT_OUT})",
    )
    p.add_argument(
        "--ids", nargs="*", default=None,
        help="只评指定的 image_id(默认评所有)",
    )
    args = p.parse_args(argv)

    if not args.maps_dir.exists():
        print(f"maps dir not found: {args.maps_dir}", file=sys.stderr)
        return 2
    if not args.previews_dir.exists():
        print(f"previews dir not found: {args.previews_dir}", file=sys.stderr)
        return 2

    if args.ids:
        map_ids = list(args.ids)
    else:
        map_ids = list_map_ids(args.maps_dir, args.previews_dir)

    if not map_ids:
        print("no map files found to score", file=sys.stderr)
        return 2

    print(f"将评 {len(map_ids)} 张地图。输出:{args.out}")
    print(f"  (按 → 保存下一张,← 上一张,Esc 退出,Ctrl+S 保存退出)")

    try:
        wiz = ScoringWizard(
            map_ids=map_ids,
            maps_dir=args.maps_dir,
            previews_dir=args.previews_dir,
            out_path=args.out,
        )
        wiz.run()
    except RuntimeError as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    except tk.TclError as e:
        print(f"Tk error: {e}", file=sys.stderr)
        return 1

    print(f"\n已评 {len(load_existing_scores(args.out))} 张,写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))