#!/bin/bash
# run_debug.sh — 一键启动 Godot console 模式,带日志文件 + dev auto-play
# 用法: bash tools/run_debug.sh [auto_play|quit_sec|godot_args...]

set -e

# 路径
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GODOT_EXE="/d/Python/godot/Godot_v4.7-stable_win64_console.exe"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

# 默认参数:从主菜单开始(不自动 free-play),默认不限时长由用户 Ctrl+C 终止
AUTO_PLAY="${BB_AUTO_PLAY:-0}"
# BB_AUTO_QUIT 留空 = 不自动退出(用户 Ctrl+C 终止)
QUIT_SEC="${BB_AUTO_QUIT:-}"

# 创建 logs 目录
mkdir -p "$LOG_DIR"

echo "=== Godot Debug Run ==="
echo "  Project: $PROJECT_DIR"
echo "  Godot:   $GODOT_EXE"
echo "  Log:     $LOG_FILE"
echo "  BB_AUTO_PLAY: $AUTO_PLAY"
echo "  BB_AUTO_QUIT: $QUIT_SEC sec"
echo ""

# 杀掉旧 godot 进程(避免端口冲突)
OLD_PID=$(ps -ef | grep -i "Godot.*stable.*console" | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$OLD_PID" ]; then
    echo "Killing old Godot PID $OLD_PID..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
fi

# 启动
cd "$PROJECT_DIR/.."
BB_AUTO_PLAY="$AUTO_PLAY" BB_AUTO_QUIT="$QUIT_SEC" \
  "$GODOT_EXE" --path "$PROJECT_DIR" res://scenes/main.tscn \
  > "$LOG_FILE" 2>&1 &
GODOT_PID=$!
echo "Godot started, PID=$GODOT_PID"
echo "Log file: $LOG_FILE"
echo ""

if [ -z "$QUIT_SEC" ]; then
    echo "无限时长 - Ctrl+C 终止 godot 后会自动出 log 总结"
    echo "实时查看日志: tail -f $LOG_FILE"
    # 等待进程退出(用户 Ctrl+C 不会终止它,但我们用 wait 等)
    trap "kill $GODOT_PID 2>/dev/null; echo 'Interrupted by Ctrl+C'" INT TERM
    wait "$GODOT_PID" 2>/dev/null
    echo ""
    echo "Godot exited (probably killed by Ctrl+C)"
else
    echo "等待 ${QUIT_SEC}s 或 Ctrl+C 退出..."
    echo "实时查看日志: tail -f $LOG_FILE"
    echo ""
    # 等待 quit 时间
    sleep "$QUIT_SEC"
fi

# 总结输出
echo ""
echo "=== Log Summary ==="
echo "Log file: $LOG_FILE"
echo "Total lines: $(wc -l < "$LOG_FILE")"
echo ""
echo "--- SCRIPT ERRORs ---"
grep -i "SCRIPT ERROR\|Parse Error\|Trying to assign" "$LOG_FILE" | grep -v WARNING | head -10 || echo "(none)"
echo ""
echo "--- Other ERRORs (non-WARNING) ---"
grep -i "ERROR" "$LOG_FILE" | grep -v WARNING | head -10 || echo "(none)"
echo ""
echo "--- WARNINGs (count) ---"
grep -c WARNING "$LOG_FILE"
echo ""
echo "--- Click events ---"
grep "\[CLICK\]" "$LOG_FILE" | head -5 || echo "(none - console mode has no mouse)"