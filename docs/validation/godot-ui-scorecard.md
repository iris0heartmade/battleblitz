# Godot UI 验收评分卡

基线：`71092d74`。本评分卡把 UI 改动的完成条件固定为可重复的自动化门槛和截图评审，不以“能启动”作为完成标准。

## 通过条件

1. Godot 烟测必须零失败。
2. `check_chinese_ui.py` 必须通过；白名单仅限按键、协议和数值等不可本地化术语，不能屏蔽自然语言。
3. 在 1280×720、1600×900、1920×1080 三档中，截图工具每档均须生成完整的 11 张 PNG。
4. 每张截图按视觉层次、信息密度、操作引导、状态反馈、中文排版、整体一致性六项评估，单张平均不低于 8.5/10，所有截图总平均不低于 8.5/10。

截图必须用 GPU 渲染而非 `--headless`：headless 模式无法读取 viewport 纹理，不能作为视觉验收依据。

```bash
GODOT_BIN=/path/to/Godot_v4.7-stable_linux.x86_64
"$GODOT_BIN" --headless --editor --path godot-client --quit
"$GODOT_BIN" --headless --path godot-client res://tools/smoke_test.tscn
python3 godot-client/tools/check_chinese_ui.py

for res in 1280x720 1600x900 1920x1080; do
  BB_REVIEW_RES="$res" "$GODOT_BIN" --rendering-method gl_compatibility \
    --resolution "$res" --path godot-client res://tools/ui_review_screenshot.tscn
done
```

## 本轮结果

验收日期：2026-08-19

| 项目 | 结果 |
| --- | --- |
| Godot 烟测 | 608 通过 / 0 失败 |
| 中文文案扫描 | 通过 |
| 截图完整性 | 三档均 11/11 张 |
| 最低单图评分 | 8.7/10（战斗行动菜单） |
| 全部截图平均 | 8.85/10 |

结论：达到本评分卡定义的 UI 验收线。后续 UI 改动必须重新执行本卡全部门槛。
