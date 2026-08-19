from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "scenes", ROOT / "scripts"]

ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_+\-/]*")
QUOTED = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
BBCODE = re.compile(r"\[[^\]]+\]")
PRINTF = re.compile(r"%[-+0-9.]*[sdif]")
TS_CN = re.compile(r'^\s*(text|placeholder_text|tooltip_text|item_\d+/text)\s*=')
GD_UI_HINTS = (
    "add_item(",
    "set_item_text(",
    "append_text(",
    "_update_status(",
    "_show_error(",
)

# 这些是国际通用的按键、网络协议、数值或游戏术语。其余面向玩家的自然
# 语言一律不在白名单内，避免英文错误提示被掩盖。
ALLOW_WORDS: set[str] = {"AI", "Esc", "HP", "HTTP", "Lv", "A", "B", "C", "D"}

ALLOW_PATTERNS = (
    re.compile(r"^res://"),
    re.compile(r"^user://"),
    re.compile(r"^https?://"),
    re.compile(r"^ws://"),
    re.compile(r"^/[A-Za-z0-9_{}?/=&%.\-]+$"),
    re.compile(r"^#[0-9A-Fa-f]{3,8}$"),
)


def is_ui_line(path: Path, line: str) -> bool:
    if path.suffix == ".tscn":
        return bool(TS_CN.search(line))
    if path.suffix == ".gd":
        stripped = line.strip()
        if stripped.startswith("#"):
            return False
        return (
            re.search(r"\b\w+\.(text|placeholder_text|tooltip_text)\s*=", line) is not None
            or any(hint in line for hint in GD_UI_HINTS)
        )
    return False


def should_skip_literal(text: str) -> bool:
    value = text.strip()
    if not value:
        return True
    if any(pattern.match(value) for pattern in ALLOW_PATTERNS):
        return True
    return False


def is_code_key(line: str, text: str) -> bool:
    stripped = line.strip()
    return (
        f'.get("{text}"' in line
        or f'get("{text}"' in line
        or stripped.startswith(f'"{text}":')
        or f'== "{text}"' in line
    )


def flagged_words(text: str, line: str) -> list[str]:
    if should_skip_literal(text):
        return []
    if is_code_key(line, text):
        return []
    text = BBCODE.sub(" ", text)
    text = PRINTF.sub(" ", text)
    text = text.replace("\\n", " ")
    text = re.sub(r"#[0-9A-Fa-f]{3,8}", " ", text)
    text = re.sub(r"\b\d+x\d+\b", " ", text)
    words = []
    for match in ASCII_WORD.finditer(text):
        word = match.group(0)
        if word in ALLOW_WORDS:
            continue
        words.append(word)
    return words


def iter_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        files.extend(base.rglob("*.gd"))
        files.extend(base.rglob("*.tscn"))
    return sorted(files)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    failures: list[str] = []
    for path in iter_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not is_ui_line(path, line):
                continue
            for literal in QUOTED.findall(line):
                words = flagged_words(literal, line)
                if words:
                    rel = path.relative_to(ROOT).as_posix()
                    failures.append(f"{rel}:{lineno}: {', '.join(words)} :: {literal}")
    if failures:
        print("发现疑似未汉化 UI 文案:")
        print("\n".join(failures))
        return 1
    print("Godot UI 文案扫描通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
