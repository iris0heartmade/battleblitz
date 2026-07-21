# BattleBlitz 主线叙事弧

> 给后续文案 / 测试 / 玩家参考用,记录 5 章的整体剧情、角色弧、解锁链路。

## 三幕式结构

```
第一幕:内乱之始 (Chapter 01-02)
  ├── 01 钢铁起义 — 卡尔德边境叛变,山口/围城
  └── 02 边境烽火 — 卡尔德残部东撤,联合异族雇佣兵,补给线/攻城

第二幕:内忧外患 (Chapter 03-04)
  ├── 03 王都暗影 — 王城内部派系斗争,阴谋家毒杀国王,主角被召回平叛
  └── 04 异族入侵 — 北境异族乘虚南下,卡尔德残部投敌,雪地/桥头/祭坛

第三幕:王朝统一 (Chapter 05)
  └── 05 王朝统一 — 卡尔德与异族联手反扑,王都保卫/王朝会战/终局对决
```

## 主角团与角色弧

| 角色 | class_id | hero_id | chapter_01 | chapter_02 | chapter_03 | chapter_04 | chapter_05 |
|---|---|---|---|---|---|---|---|
| 云 | swordsman → paladin → blade_master | yun | Lv1 剑士,初上战场 | Lv3 剑士,转 paladin 前兆 | Lv5 paladin,率军回王都 | Lv8 blade_master,雪地王牌 | Lv12 blade_master,最终决战 |
| 红 | archer → sniper → dragon_rider | (无) | Lv1 弓手,辅助输出 | Lv3 sniper,远程压制 | Lv5 sniper,王城屋顶狙击 | Lv8 dragon_rider,飞龙出场 | Lv12 dragon_rider,空中支援 |
| 安娜 | healer → sage → saint | anna | Lv1 治疗,初登场 | Lv3 healer,战后治愈 | Lv5 sage,智囊出场 | Lv8 sage,智破祭坛 | Lv12 saint,加冕祝福 |

## 反派弧

- **卡尔德**:Ch01 边境领主 → Ch02 残部 → Ch03 幕后操纵王都内斗 → Ch04 投敌引异族 → Ch05 终局决战
- **乌格**(异族首领):Ch04 出场 → Ch05 与卡尔德联手 → 最终战败

## 火纹式对话钩子设计原则

1. **三段式**:每个 chapter 必有 intro / 每个 battle_after / victory,后章 victory 提到前章事件
2. **角色连贯**:同一组主角在 5 章中都出现,通过 `speaker` 字段引用(云/红/安娜),并在前情上叠加新的纠结
3. **choice 节点**:每个 victory 末尾留一个 choice(回大厅/继续/观看回放),部分 chapter 在 battle_after 留战术选择
4. **跨章引用**:Ch02 intro 提到"山口一战后……",Ch03 提到"边境战事平定后回到王都……",Ch04 提到"王都政变后北境空虚……",Ch05 提到"异族祭坛被毁后卡尔德勾结残部反扑"

## 顺序解锁(对应 `_has_cleared_mainline`)

- 玩家通关 chapter_01 才能进入 chapter_02
- 通关 chapter_02 才能进入 chapter_03
- 通关 chapter_03 才能进入 chapter_04
- 通关 chapter_04 才能进入 chapter_05
- 通关 chapter_05 视为王朝统一,主线结束

(顺序解锁由后端 `game/app/routes/mainline.py:_ensure_test_mainline_unlocked` 保证,见 `2026-07-21 Task 2` 工作)
