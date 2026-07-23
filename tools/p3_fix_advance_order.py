"""p3_fix_advance_order.py — P3.1 修 advance 顺序:
  1. is_last 分支:apply_victory 必须在 auto_save 之前(写完 gold/unlock 入 snapshot)
  2. 非 last 分支:apply_battle_victory + mark_scene_done 必须都在 auto_save 之前
  3. auto_save 块本身保留原 chapter_index=next_index(不变,本来就在用推进后值)
"""
from __future__ import annotations
import re
from pathlib import Path

FILE = Path("game/app/routes/mainline/battle_lifecycle.py")


def main() -> None:
    text = FILE.read_text(encoding="utf-8")
    orig = len(text)

    # 锚定 auto_save_checkpoint 块,把它的 # 注释改写 + 整块位置前移到 if is_last 之后
    # 因为 GDScript 的 "string not found" 暗示有 unicode 空格问题 — 用 line-by-line 处理

    # 找到 auto_save_checkpoint 块的 start 行号(从 line 1 数)
    lines = text.splitlines(keepends=True)
    save_block_start = None
    save_block_end = None
    for i, line in enumerate(lines):
        if "auto_save_out = await auto_save_checkpoint(" in line:
            save_block_start = i
            # 找块结束(下一个非缩进行 或 return / except / if / else 行)
            j = i + 1
            depth = 1
            while j < len(lines):
                lj = lines[j]
                # 块结束条件:以 `    )` 结束且下一行是 `    if is_last:` 或 `    else:` 或 `    return`
                if lj.rstrip().endswith(")") and not lj.lstrip().startswith("#"):
                    # 这是 `chapter_index=next_index,` 后的参数右括号?或函数右括号?
                    # 看下一行
                    if j + 1 < len(lines) and lines[j + 1].lstrip().startswith(("if ", "else:", "    return", "    battle", "    rewards")):
                        save_block_end = j
                        break
                j += 1
            break

    if save_block_start is None:
        raise RuntimeError("auto_save_checkpoint block not found")
    print(f"[find] auto_save block: lines {save_block_start + 1} - {save_block_end + 1}")

    # 找到 if is_last: 的行号
    is_last_start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("if is_last:"):
            is_last_start = i
            break
    if is_last_start is None:
        raise RuntimeError("if is_last block not found")

    # 找到非 last 分支的"apply_battle_victory" / "mark_scene_done" 块行
    apply_bv_line = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("battle = ml.battles[battle_index]"):
            apply_bv_line = i
            break

    # 1) 标记 auto_save_block 的注释(改写为 P3 注释)
    # 用 Python 替换注释行 — 行 save_block_start 上面几行是注释
    new_lines = []
    for i, line in enumerate(lines):
        if i >= save_block_start - 4 and i < save_block_start:
            # 替换注释块(4 行)
            if i == save_block_start - 4:
                new_lines.append("    # P3 auto-save 顺序统一(plan §P3.1):先 apply 奖励 + 推 cursor,再 auto-save,\n")
            elif i == save_block_start - 3:
                new_lines.append("    # 这样 snapshot.cursor 与 slot.chapter_index 都 = next_index(推进后),\n")
            elif i == save_block_start - 2:
                new_lines.append('    # "载入结束档 = 准备打下一章"。\n')
            elif i == save_block_start - 1:
                new_lines.append("    rewards = None\n")
                new_lines.append("    next_mainline_id = None\n")
                new_lines.append("    next_mainline_title = None\n")
                new_lines.append("    post_url = None\n")
                new_lines.append("    post_key = None\n")
                new_lines.append("    battle = ml.battles[battle_index]\n")
                new_lines.append("    if is_last:\n")
                new_lines.append("        rewards = await engine.apply_victory(completed_battle=battle)\n")
                new_lines.append("        next_mainline_id = ml.next_mainline_id\n")
                new_lines.append("        if next_mainline_id:\n")
                new_lines.append("            try:\n")
                new_lines.append("                next_mainline_title = mainline_pkg.load_mainline(next_mainline_id).title\n")
                new_lines.append("            except MainlineNotFound:\n")
                new_lines.append("                logger.warning(\n")
                new_lines.append('                    "mainline_advance successor missing: mainline=%s next=%s",\n')
                new_lines.append("                    mainline_id, next_mainline_id,\n")
                new_lines.append("                )\n")
                new_lines.append("                next_mainline_id = None\n")
                new_lines.append("        logger.info(\n")
                new_lines.append('            "mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=victory "\n')
                new_lines.append('            "gold=+%d unlock=%s exp_per_unit=+%d",\n')
                new_lines.append("            body.user_name, mainline_id, battle_index, next_index,\n")
                new_lines.append('            rewards.gold or 0, rewards.unlock_class or "-",\n')
                new_lines.append("            rewards.exp_per_unit or 0,\n")
                new_lines.append("        )\n")
                new_lines.append("    else:\n")
                new_lines.append("        # 非 last:apply 战斗奖励 + mark_scene_done 推 cursor(snapshot 会包含全部)\n")
                new_lines.append("        engine.apply_battle_victory(battle)\n")
                new_lines.append("        post_key = battle.post_battle_dialogue\n")
                new_lines.append("        post_url = ml.dialogues.get(post_key) if post_key else None\n")
                new_lines.append("        if post_key:\n")
                new_lines.append("            await engine.mark_scene_done(post_key, next_battle=True)\n")
                new_lines.append("        else:\n")
                new_lines.append("            # No post-battle dialogue; just bump the cursor with no scene change.\n")
                new_lines.append("            await engine.mark_scene_done(\n")
                new_lines.append("                ml.battles[next_index - 1].pre_battle_dialogue or \"intro\",\n")
                new_lines.append("                next_battle=True,\n")
                new_lines.append("            )\n")
                new_lines.append("        logger.info(\n")
                new_lines.append('            "mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=%s post_dlg=%s",\n')
                new_lines.append("            body.user_name, mainline_id, battle_index, next_index,\n")
                new_lines.append('            "dialogue" if post_url else "battle", post_key or "-",\n')
                new_lines.append("        )\n")
                new_lines.append("\n")
                new_lines.append("    # Auto-save at chapter-end(per FE8 design v2 §2.3)。snapshot cursor\n")
                new_lines.append("    # 已推到 next_index(应用奖励 + mark_scene_done 之后),slot.chapter_index\n")
                new_lines.append("    # 也是 next_index — 单一真相一致(plan §P3.1)。\n")
            continue
        if save_block_start <= i <= save_block_end:
            # 跳过原 auto_save 块(已在前面重组)
            continue
        new_lines.append(line)

    # 现在还要删原来的 `if is_last:` 块(含到 `return MainlineAdvanceOut` )和
    # 原非 last 分支的 apply_battle_victory + mark_scene_done 块
    # 找 if is_last 行(原版的) - 已经被替换掉注释后的 lines 中
    # 实际:原 `if is_last:` 块在文件中现在仍存在,我们要删它

    # 在 new_lines 中找原 `if is_last:` 块(现在孤立的,从行 is_last_start 起)
    final_lines = new_lines
    if is_last_start is None:
        raise RuntimeError("is_last start not found after edit")

    # 找到原 if is_last 块的结束(下一个 `    # Otherwise:` 或 `    else:` 注释或 `    return`)
    # 实际:原文件结构是 `if is_last: ... return ... \n # Otherwise: ...` 而我们的注释替换删掉了 auto_save 块 + 添加了新逻辑,
    # 原 `if is_last:` 仍存在,需要删除

    # 简单处理:从已重组的 new_lines 中再次找 `if is_last:` 并删到 `    return MainlineAdvanceOut`
    # 注意:我们的重组在前面已 include "if is_last:"!所以这里找的是"第二次"的
    # 但我们的重组是从 save_block_start - 1 行替换的,is_last_start 是原文件的行号,
    # 在 new_lines 中位置不一样(因为前面替换 insert 了更多行)

    # 算了,直接用正则 — 删除从原 `if is_last: ... \n return MainlineAdvanceOut(...)` + 后续 `\n\n    # Otherwise:` + apply_battle_victory + mark_scene_done 整段
    final_text = "".join(final_lines)

    # 删除原 is_last 块:从 `    if is_last:` 到 `        auto_save=auto_save_out.model_dump(),\n        )`
    # 因为我们已经在前面替换里加了 if is_last 块,需要把后面这个删除

    # 模式:`    if is_last:` 后跟 `        rewards = await engine.apply_victory(\n            completed_battle=ml.battles[battle_index]\n        )` 然后一堆,然后 `        auto_save=auto_save_out.model_dump(),\n        )\n    # Otherwise:` 注释

    pattern = re.compile(
        r"    if is_last:\n"
        r"        rewards = await engine\.apply_victory\(\n"
        r"            completed_battle=ml\.battles\[battle_index\]\n"
        r"        \)\n"
        r"        next_mainline_id = ml\.next_mainline_id\n"
        r"        next_mainline_title = None\n"
        r"        if next_mainline_id:\n"
        r"            try:\n"
        r"                next_mainline_title = mainline_pkg\.load_mainline\(next_mainline_id\)\.title\n"
        r"            except MainlineNotFound:\n"
        r"                logger\.warning\(\n"
        r'                    "mainline_advance successor missing: mainline=%s next=%s",\n'
        r"                    mainline_id, next_mainline_id,\n"
        r"                \)\n"
        r"                next_mainline_id = None\n"
        r"        logger\.info\(\n"
        r'            "mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=victory "\n'
        r'            "gold=+%d unlock=%s exp_per_unit=+%d",\n'
        r"            body\.user_name, mainline_id, battle_index, next_index,\n"
        r'            rewards\.gold or 0, rewards\.unlock_class or "-",\n'
        r"            rewards\.exp_per_unit or 0,\n"
        r"        \)\n"
        r"        audit\.info\(\n"
        r"            \"USER_ACTION \| user=%s \| action=MAINLINE_ADVANCE \| mainline=%s \| \"\n"
        r"            \"battle_index=%d \| result=SUCCESS \| state=victory\",\n"
        r"            body\.user_name, mainline_id, next_index,\n"
        r"        \)\n"
        r"        return MainlineAdvanceOut\(\n"
        r"            state=\"victory\",\n"
        r"            mainline_id=mainline_id,\n"
        r"            battle_index=next_index,\n"
        r"            total_battles=total_battles,\n"
        r"            post_battle_dialogue_url=None,\n"
        r"            post_battle_dialogue_key=None,\n"
        r"            rewards=rewards,\n"
        r"            victory_dialogue_url=ml\.dialogues\.get\(\"victory\"\),\n"
        r"            victory_dialogue_key=\"victory\" if ml\.dialogues\.get\(\"victory\"\) else None,\n"
        r"            next_mainline_id=next_mainline_id,\n"
        r"            next_mainline_title=next_mainline_title,\n"
        r"            auto_save=auto_save_out\.model_dump\(\),\n"
        r"        \)\n"
        r"\n"
        r"    # Otherwise: advance the cursor and return the post-battle dialogue\n"
        r"    # for the battle we just won \(so the frontend can play it before\n"
        r"    # requesting /next-battle\)\.\n"
        r"    battle = ml\.battles\[battle_index\]\n"
        r"    engine\.apply_battle_victory\(battle\)\n"
        r"    post_key = battle\.post_battle_dialogue\n"
        r"    post_url = ml\.dialogues\.get\(post_key\) if post_key else None\n"
        r"\n"
        r"    # Bump the cursor via the service so the JSON column is well-formed\.\n"
        r"    # We use next_battle=True here to advance battle_index by 1, AND set\n"
        r"    # the cursor's scene_id to the post_battle_dialogue key \(or fall back\n"
        r"    # to the only dialogue key if the battle has no post_battle_dialogue\)\.\n"
        r"    if post_key:\n"
        r"        await engine\.mark_scene_done\(post_key, next_battle=True\)\n"
        r"    else:\n"
        r"        # No post-battle dialogue; just bump the cursor with no scene change\.\n"
        r"        await engine\.mark_scene_done\(\n"
        r"            ml\.battles\[next_index - 1\]\.pre_battle_dialogue or \"intro\",\n"
        r"            next_battle=True,\n"
        r"        \)\n"
        r"\n"
        r"    logger\.info\(\n"
        r"        \"mainline_advance ok: user=%s mainline=%s battle_index=%d→%d state=%s post_dlg=%s\",\n"
        r"        body\.user_name, mainline_id, battle_index, next_index,\n"
        r'        "dialogue" if post_url else "battle", post_key or "-",\n'
        r"    \)\n",
        re.MULTILINE,
    )

    n_replaced = len(pattern.findall(final_text))
    final_text = pattern.sub("", final_text)
    print(f"[regex del] original is_last+otherwise blocks: {n_replaced}")

    FILE.write_text(final_text, encoding="utf-8")
    print(f"\n[done] file size {orig} -> {len(final_text)}")


if __name__ == "__main__":
    main()