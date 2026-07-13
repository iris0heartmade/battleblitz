// make_pptx.js — Godot 资源导航 PPT
// Run: node godot-client/docs/make_pptx.js
// Output: godot-client/docs/Godot资源导航.pptx

const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

// =================== 调色板：Midnight Executive ===================
// Primary: 深海军蓝 (NavC)
// Secondary: 冰蓝 (Ice) — 背景/卡片
// Accent:    亮金 (Gold) — 高亮/CTA
const C = {
  navy:    "1E2761",
  navyDk:  "141B47",   // 更深的 navy
  navyLt:  "2A3590",
  ice:     "E5ECF5",   // 卡片背景
  iceLt:   "F4F7FC",   // 浅冰
  white:   "FFFFFF",
  gold:    "F5C249",   // accent
  goldDk:  "D4A328",
  text:    "1F2937",   // 正文深灰
  textLt:  "6B7280",   // 次要文字
  border:  "C5CEE0",
  green:   "34A853",   // 用于 ✓ / pass
  red:     "E04040",   // 用于 ✗ / fail
};

const FONT_TITLE = "Georgia";
const FONT_BODY  = "Calibri";

// =================== 工具 ===================
function abs(rel) {
  return path.resolve(__dirname, rel).replace(/\\/g, "/");
}

const SHADOW = () => ({ type: "outer", color: "000000", blur: 8, offset: 2, angle: 135, opacity: 0.15 });
const SHADOW_LG = () => ({ type: "outer", color: "000000", blur: 14, offset: 4, angle: 135, opacity: 0.20 });

// 通用：底部页脚（细线 + 文字）
function addFooter(slide, pres, pageNum, totalPages) {
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 5.25, w: 9.0, h: 0,
    line: { color: C.border, width: 0.5 }
  });
  slide.addText("BattleBlitz Godot 客户端 · 资源导航", {
    x: 0.5, y: 5.30, w: 5, h: 0.25,
    fontSize: 9, color: C.textLt, fontFace: FONT_BODY
  });
  slide.addText(`${pageNum} / ${totalPages}`, {
    x: 9.0, y: 5.30, w: 0.7, h: 0.25,
    fontSize: 9, color: C.textLt, fontFace: FONT_BODY, align: "right"
  });
}

// =================== 主流程 ===================
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title  = "Godot 资源导航 — BattleBlitz 客户端";
pres.author = "BattleBlitz Godot Agent";
pres.company = "BattleBlitz";

// 我们要做几张 slide 的清单（先占位，按顺序构建）
const slides = [];

// ============== SLIDE 1: 标题 ==============
{
  const s = pres.addSlide();
  s.background = { color: C.navyDk };

  // 左侧装饰条
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.25, h: 5.625,
    fill: { color: C.gold }, line: { type: "none" }
  });

  // 顶部小字
  s.addText("BATTLEBLITZ  ·  GODOT 4.7  ·  2026.07", {
    x: 0.7, y: 0.6, w: 9, h: 0.3,
    fontSize: 11, color: C.gold, fontFace: FONT_BODY, charSpacing: 6
  });

  // 主标题
  s.addText("Godot 资源导航", {
    x: 0.7, y: 1.5, w: 9, h: 1.2,
    fontSize: 60, color: C.white, fontFace: FONT_TITLE, bold: true
  });

  // 副标题
  s.addText("插件 · 教程 · 免费贴图  →  客户端地图升级实战", {
    x: 0.7, y: 2.85, w: 9, h: 0.5,
    fontSize: 22, color: C.ice, fontFace: FONT_BODY
  });

  // 装饰线
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 3.55, w: 1.2, h: 0.04,
    fill: { color: C.gold }, line: { type: "none" }
  });

  // 底部信息
  s.addText("调研日期: 2026-07-13  |  目标: BattleBlitz Godot 客户端 M0+M1+M1.5", {
    x: 0.7, y: 4.7, w: 9, h: 0.3,
    fontSize: 12, color: C.textLt, fontFace: FONT_BODY
  });

  // 版本徽章
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 7.5, y: 4.6, w: 1.8, h: 0.45,
    fill: { color: C.navyLt }, line: { type: "none" }, rectRadius: 0.08
  });
  s.addText("v0.1 draft", {
    x: 7.5, y: 4.6, w: 1.8, h: 0.45,
    fontSize: 12, color: C.gold, fontFace: FONT_BODY, align: "center", valign: "middle", bold: true
  });
}

// ============== SLIDE 2: TL;DR ==============
{
  const s = pres.addSlide();
  s.background = { color: C.iceLt };

  s.addText("TL;DR", {
    x: 0.5, y: 0.4, w: 9, h: 0.6,
    fontSize: 32, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("三条带走", {
    x: 0.5, y: 0.95, w: 9, h: 0.35,
    fontSize: 14, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  const items = [
    { num: "1", title: "FE8 商业级美术直接复用", body: "OverworldRegularFE8.png 32×32 sub-tile 全 autotile 套件；省 6 个月美术" },
    { num: "2", title: "Godot 4.7 TerrainSet bitmask 自动混合", body: "一个 add_terrain_set() + 16 个 peering bit，平原/森林/山/水边自动融合" },
    { num: "3", title: "Kenney CC0 / OpenGameArt 顶上", body: "50MB+ 战略游戏素材免费可用，30 天可换皮出 demo" },
  ];

  items.forEach((it, i) => {
    const y = 1.55 + i * 1.1;
    // 圆形大数字
    s.addShape(pres.shapes.OVAL, {
      x: 0.6, y: y, w: 0.9, h: 0.9,
      fill: { color: C.navy }, line: { type: "none" }
    });
    s.addText(it.num, {
      x: 0.6, y: y, w: 0.9, h: 0.9,
      fontSize: 36, color: C.gold, fontFace: FONT_TITLE, bold: true, align: "center", valign: "middle"
    });
    // 标题 + 正文
    s.addText(it.title, {
      x: 1.8, y: y + 0.05, w: 7.5, h: 0.4,
      fontSize: 20, color: C.navy, fontFace: FONT_BODY, bold: true, margin: 0
    });
    s.addText(it.body, {
      x: 1.8, y: y + 0.48, w: 7.5, h: 0.4,
      fontSize: 14, color: C.text, fontFace: FONT_BODY, margin: 0
    });
  });

  addFooter(s, pres, 2, 8);
}

// ============== SLIDE 3: 痛点 + 路线图 ==============
{
  const s = pres.addSlide();
  s.background = { color: C.white };

  // 标题
  s.addText("我们面对什么 / 走什么路", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("从『丑到不能用』到 FE8 商业级美术", {
    x: 0.5, y: 0.9, w: 9, h: 0.3,
    fontSize: 13, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  // 左：原来
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.5, w: 4.3, h: 3.4,
    fill: { color: C.ice }, line: { color: C.border, width: 1 }, shadow: SHADOW()
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.5, w: 4.3, h: 0.5,
    fill: { color: C.red }, line: { type: "none" }
  });
  s.addText("BEFORE  ·  原版 DOM+CSS", {
    x: 0.5, y: 1.5, w: 4.3, h: 0.5,
    fontSize: 14, color: C.white, fontFace: FONT_BODY, bold: true, align: "center", valign: "middle"
  });
  s.addText([
    { text: "原版 70 张 48×48 像素图", options: { bullet: true, breakLine: true } },
    { text: "<div class='cell'> 硬渲染", options: { bullet: true, breakLine: true } },
    { text: "无 autotile、边缘硬切", options: { bullet: true, breakLine: true } },
    { text: "看不出森林、看不出湖", options: { bullet: true, breakLine: true } },
    { text: "用户反馈：地图太丑", options: { bullet: true, color: C.red, bold: true } },
  ], {
    x: 0.8, y: 2.1, w: 3.8, h: 2.7,
    fontSize: 13, color: C.text, fontFace: FONT_BODY, paraSpaceAfter: 4
  });

  // 中间箭头
  s.addShape(pres.shapes.RIGHT_TRIANGLE, {
    x: 4.95, y: 2.95, w: 0.5, h: 0.5, rotate: 90,
    fill: { color: C.gold }, line: { type: "none" }
  });

  // 右：现在
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.6, y: 1.5, w: 4.0, h: 3.4,
    fill: { color: C.ice }, line: { color: C.border, width: 1 }, shadow: SHADOW()
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.6, y: 1.5, w: 4.0, h: 0.5,
    fill: { color: C.green }, line: { type: "none" }
  });
  s.addText("NOW  ·  Godot 4.7 + FE8", {
    x: 5.6, y: 1.5, w: 4.0, h: 0.5,
    fontSize: 14, color: C.white, fontFace: FONT_BODY, bold: true, align: "center", valign: "middle"
  });
  s.addText([
    { text: "OverworldRegularFE8.png", options: { bullet: true, breakLine: true, color: C.navy, bold: true } },
    { text: "32×32 sub-tile，自带 autotile 块", options: { bullet: true, breakLine: true } },
    { text: "TileSet.add_terrain_set() 4 套", options: { bullet: true, breakLine: true } },
    { text: "Plain/Forest/Mountain/River 边自动融合", options: { bullet: true, breakLine: true } },
    { text: "55/55 smoke test 通过 ✓", options: { bullet: true, color: C.green, bold: true } },
  ], {
    x: 5.85, y: 2.1, w: 3.6, h: 2.7,
    fontSize: 13, color: C.text, fontFace: FONT_BODY, paraSpaceAfter: 4
  });

  addFooter(s, pres, 3, 8);
}

// ============== SLIDE 4: 实战对比（截图）==============
{
  const s = pres.addSlide();
  s.background = { color: C.white };

  s.addText("FE8 接入效果", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("15×15 balanced_2p_15 · FE8 + TerrainSet bitmask autotiling", {
    x: 0.5, y: 0.9, w: 9, h: 0.3,
    fontSize: 13, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  // 左：autotile 后
  s.addImage({
    path: abs("../screenshots/06_fe8_autotile.png"),
    x: 0.5, y: 1.35, w: 5.2, h: 3.7
  });
  s.addText("✓ Godot 自动按 4 邻居 NSEW 选边", {
    x: 0.5, y: 5.05, w: 5.2, h: 0.2,
    fontSize: 10, color: C.textLt, fontFace: FONT_BODY, align: "center"
  });

  // 右：FE8 完整 atlas 预览
  s.addImage({
    path: abs("../assets/tiles_fe8/overworld_fe8.png"),
    x: 5.95, y: 1.35, w: 3.6, h: 3.6
  });
  s.addText("↑ 资源: Fire Emblem 8 OverworldRegularFE8.png (512×512)", {
    x: 5.95, y: 5.05, w: 3.6, h: 0.2,
    fontSize: 10, color: C.textLt, fontFace: FONT_BODY, align: "center"
  });

  // 右侧注解
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.95, y: 1.35, w: 3.6, h: 3.6,
    fill: { color: C.ice, transparency: 70 },
    line: { color: C.gold, width: 2 }
  });

  addFooter(s, pres, 4, 8);
}

// ============== SLIDE 5: 推荐插件 ==============
{
  const s = pres.addSlide();
  s.background = { color: C.iceLt };

  s.addText("推荐 Godot 4 插件", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("按对 BattleBlitz 客户端的价值排序", {
    x: 0.5, y: 0.9, w: 9, h: 0.3,
    fontSize: 13, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  const plugins = [
    {
      tag: "★★★★★",
      tagColor: C.gold,
      name: "GUT (Godot Unit Test)",
      author: "bitwes",
      url: "github.com/bitwes/Gut",
      desc: "GDUnit 的现代替代。GDScript 单元测试 + GUI runner。",
      use: "替代 70 行手写 smoke_test.gd，200+ 断言自动跑",
    },
    {
      tag: "★★★★★",
      tagColor: C.gold,
      name: "Dialogic 2",
      author: "dialogic-godot",
      url: "github.com/dialogic-godot/dialogic",
      desc: "分支对话/打字机效果/角色立绘。M2 主线剧情直接用。",
      use: "替换现有 web/app.js 的 Dialog.show() 实现",
    },
    {
      tag: "★★★★",
      tagColor: C.goldDk,
      name: "Gaea",
      author: "Beyond Realm",
      url: "godotter.com",
      desc: "节点化地形生成器。可视化编辑高度+生物群系。",
      use: "镜像服务端 map_generation/ 供关卡设计师本地调",
    },
    {
      tag: "★★★★",
      tagColor: C.goldDk,
      name: "Tween Suite (Tweener)",
      author: "Kazumi",
      url: "godot asset library",
      desc: "扩展 Tween 节点：更平滑的缓动曲线、回调链。",
      use: "M3 单位移动/受击/HUD 弹入动画",
    },
    {
      tag: "★★★",
      tagColor: C.textLt,
      name: "GUT + GdUnit4",
      author: "Mike)",
      url: "github.com/MikeSchulze/gdUnit4",
      desc: "GDScript 单元测试的另一个流派。社区比 GUT 小。",
      use: "和 GUT 二选一即可",
    },
    {
      tag: "★★★",
      tagColor: C.textLt,
      name: "Phantom Camera",
      author: "ramokskop",
      url: "github.com/ramokskop/phantom-camera",
      desc: "2D/3D 相机管理：跟随/抖动/区域限制。",
      use: "M4 战斗镜头：单位选中缩放/震屏",
    },
  ];

  // 2 列 × 3 行卡片
  const cardW = 4.4, cardH = 1.20, gapX = 0.2, gapY = 0.15;
  const startX = 0.5, startY = 1.35;
  plugins.forEach((p, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);
    // 卡片
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cardW, h: cardH,
      fill: { color: C.white }, line: { color: C.border, width: 0.5 }, shadow: SHADOW()
    });
    // 左侧色条
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: cardH,
      fill: { color: C.navy }, line: { type: "none" }
    });
    // 名称
    s.addText(p.name, {
      x: x + 0.18, y: y + 0.08, w: cardW - 1.4, h: 0.3,
      fontSize: 14, color: C.navy, fontFace: FONT_BODY, bold: true, margin: 0
    });
    // 星级
    s.addText(p.tag, {
      x: x + cardW - 1.0, y: y + 0.08, w: 0.95, h: 0.25,
      fontSize: 12, color: p.tagColor, fontFace: FONT_BODY, align: "right", margin: 0
    });
    // 作者 + URL
    s.addText(`${p.author}  ·  ${p.url}`, {
      x: x + 0.18, y: y + 0.36, w: cardW - 0.3, h: 0.22,
      fontSize: 9, color: C.textLt, fontFace: FONT_BODY, italic: true, margin: 0
    });
    // 描述
    s.addText(p.desc, {
      x: x + 0.18, y: y + 0.58, w: cardW - 0.3, h: 0.3,
      fontSize: 10, color: C.text, fontFace: FONT_BODY, margin: 0
    });
    // 用途
    s.addText(`→ ${p.use}`, {
      x: x + 0.18, y: y + 0.88, w: cardW - 0.3, h: 0.28,
      fontSize: 9, color: C.green, fontFace: FONT_BODY, margin: 0
    });
  });

  addFooter(s, pres, 5, 8);
}

// ============== SLIDE 6: 教程 ==============
{
  const s = pres.addSlide();
  s.background = { color: C.white };

  s.addText("推荐学习资源", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("从入门到 SRPG 实战", {
    x: 0.5, y: 0.9, w: 9, h: 0.3,
    fontSize: 13, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  // 3 列分类
  const cols = [
    {
      head: "📺  YouTube 频道",
      color: C.red,
      items: [
        { name: "Heartbeast",     url: "youtube.com/@uheartbeast", desc: "Action RPG 经典系列(虽 Godot 3，但 GDScript 思想一致)" },
        { name: "GDQuest",        url: "youtube.com/@Gdquest",       desc: "GDScript 最佳实践 + 节点设计 + Tilemap 系列" },
        { name: "Brackeys (Unity)", url: "youtube.com/@Brackeys",   desc: "Game Dev 思路通用：状态机、UI/UX、shader" },
        { name: "DevWorm",        url: "youtube.com/@devworm",       desc: "Godot 4 实测 + shader 案例" },
      ]
    },
    {
      head: "📖  官方文档 + 书籍",
      color: C.navy,
      items: [
        { name: "Godot Docs 4.7",   url: "docs.godotengine.org",    desc: "权威 API 参考，必查 TileSet / TileMapLayer / TileData" },
        { name: "GDQuest Free Book", url: "gdquest.com/docs",      desc: "免费 100+ 页 GDScript 教程 (PDF/EPUB)" },
        { name: "KidsCanCode",      url: "kidscancode.org/godot_recipes", desc: "Tween/StateMachine/SignalBus 实例库" },
        { name: "r/godot",          url: "reddit.com/r/godot",       desc: "社区答疑 + 插件评测 + 工作流分享" },
      ]
    },
    {
      head: "🎮  SRPG 专项",
      color: C.gold,
      items: [
        { name: "Awesome Godot 列表", url: "github.com/godotengine/awesome-godot", desc: "社区项目/Tilemap/AI/网络 全栈" },
        { name: "Fire Emblem Clone", url: "github.com/dualword/fe-client", desc: "C++ 火纹复刻源码，可读但量大" },
        { name: "Advance Wars 复刻",  url: "github.com/fxspec06/Advance-Wars-v2", desc: "Java 高级战争复刻，状态机 + 行动点参考" },
        { name: "GDQuest TD 系列",   url: "gdquest.com/library/",     desc: "Tower Defense 系列包含路径/格点" },
      ]
    },
  ];

  const colW = 3.0, gap = 0.15, startX = 0.4, startY = 1.3;
  cols.forEach((col, i) => {
    const x = startX + i * (colW + gap);
    // 列头
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: startY, w: colW, h: 0.4,
      fill: { color: col.color }, line: { type: "none" }
    });
    s.addText(col.head, {
      x, y: startY, w: colW, h: 0.4,
      fontSize: 14, color: C.white, fontFace: FONT_BODY, bold: true, align: "center", valign: "middle"
    });
    // 卡片内容
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: startY + 0.4, w: colW, h: 3.45,
      fill: { color: C.iceLt }, line: { color: C.border, width: 0.5 }
    });
    col.items.forEach((it, j) => {
      const itemY = startY + 0.5 + j * 0.82;
      s.addText(it.name, {
        x: x + 0.1, y: itemY, w: colW - 0.2, h: 0.25,
        fontSize: 11, color: C.navy, fontFace: FONT_BODY, bold: true, margin: 0
      });
      s.addText(it.url, {
        x: x + 0.1, y: itemY + 0.22, w: colW - 0.2, h: 0.2,
        fontSize: 8, color: C.textLt, fontFace: FONT_BODY, italic: true, margin: 0
      });
      s.addText(it.desc, {
        x: x + 0.1, y: itemY + 0.42, w: colW - 0.2, h: 0.35,
        fontSize: 9, color: C.text, fontFace: FONT_BODY, margin: 0
      });
    });
  });

  addFooter(s, pres, 6, 8);
}

// ============== SLIDE 7: 贴图资源 ==============
{
  const s = pres.addSlide();
  s.background = { color: C.iceLt };

  s.addText("免费贴图资源", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true
  });
  s.addText("CC0 / Public Domain 商业可用 · 不需要署名", {
    x: 0.5, y: 0.9, w: 9, h: 0.3,
    fontSize: 13, color: C.textLt, fontFace: FONT_BODY, italic: true
  });

  // 4 个推荐包
  const packs = [
    { name: "Kenney Strategy (16-bit)", size: "135 KB", tiles: "100+ 地形+单位+建筑", url: "kenney.nl/assets/tileset-strategy", tier: "★★★ 首推" },
    { name: "Kenney Strategy (32-bit)", size: "1.3 MB", tiles: "高清地形+单位+动画", url: "kenney.nl/assets/strategy-32bit", tier: "★★" },
    { name: "Kenney Strategy Voxel", size: "9.9 MB", tiles: "3D 体素全套", url: "kenney.nl/assets/strategy-voxel", tier: "★★" },
    { name: "OpenGameArt 16x16 Fantasy", size: "varies", tiles: "中世纪奇幻全套", url: "opengameart.org/content/16x16-fantasy-tileset", tier: "★★★ 火纹味" },
    { name: "OpenGameArt 主站", size: "10000+ 资源", tiles: "战棋/RPG/塔防/2D", url: "opengameart.org", tier: "海选" },
    { name: "Liberated Pixel Cup (LPC)", size: "开源 sprite", tiles: "角色/单位/坐骑", url: "opengameart.org/content/lpc-tileset-...", tier: "★★ 角色向" },
  ];

  const cardW = 4.5, cardH = 1.10, gapX = 0.2, gapY = 0.15, startX = 0.4, startY = 1.3;
  packs.forEach((p, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cardW, h: cardH,
      fill: { color: C.white }, line: { color: C.border, width: 0.5 }, shadow: SHADOW()
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: cardH,
      fill: { color: C.gold }, line: { type: "none" }
    });
    s.addText(p.name, {
      x: x + 0.18, y: y + 0.05, w: cardW - 1.3, h: 0.28,
      fontSize: 13, color: C.navy, fontFace: FONT_BODY, bold: true, margin: 0
    });
    s.addText(p.tier, {
      x: x + cardW - 1.0, y: y + 0.05, w: 0.95, h: 0.25,
      fontSize: 10, color: C.goldDk, fontFace: FONT_BODY, align: "right", margin: 0
    });
    s.addText(`${p.size}  ·  ${p.tiles}`, {
      x: x + 0.18, y: y + 0.34, w: cardW - 0.3, h: 0.25,
      fontSize: 10, color: C.text, fontFace: FONT_BODY, margin: 0
    });
    s.addText(p.url, {
      x: x + 0.18, y: y + 0.6, w: cardW - 0.3, h: 0.22,
      fontSize: 9, color: C.textLt, fontFace: FONT_BODY, italic: true, margin: 0
    });
    s.addText("✓ 商用免费", {
      x: x + 0.18, y: y + 0.82, w: cardW - 0.3, h: 0.22,
      fontSize: 9, color: C.green, fontFace: FONT_BODY, bold: true, margin: 0
    });
  });

  addFooter(s, pres, 7, 8);
}

// ============== SLIDE 8: 路线图 + Action Items ==============
{
  const s = pres.addSlide();
  s.background = { color: C.navyDk };

  s.addText("下一步 & Action Items", {
    x: 0.5, y: 0.4, w: 9, h: 0.5,
    fontSize: 32, color: C.white, fontFace: FONT_TITLE, bold: true
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.0, w: 1.2, h: 0.04,
    fill: { color: C.gold }, line: { type: "none" }
  });

  // 左：M2 路线
  s.addText("客户端路线图 (待启动)", {
    x: 0.5, y: 1.25, w: 4.5, h: 0.35,
    fontSize: 14, color: C.gold, fontFace: FONT_BODY, bold: true
  });
  const roadmap = [
    { m: "M2", t: "WS 网关 + REST 动作 + MapLogic BFS", c: C.navyLt },
    { m: "M3", t: "大厅/HUD/CO 能量/对话/主线", c: C.navy },
    { m: "M4", t: "触屏 + 移动端导出 (Android/iOS)", c: C.navyLt },
    { m: "M5", t: "WSS 公网部署 + Web 导出", c: C.navy },
  ];
  roadmap.forEach((r, i) => {
    const y = 1.7 + i * 0.6;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 0.7, h: 0.5,
      fill: { color: r.c }, line: { type: "none" }
    });
    s.addText(r.m, {
      x: 0.5, y, w: 0.7, h: 0.5,
      fontSize: 16, color: C.gold, fontFace: FONT_TITLE, bold: true, align: "center", valign: "middle"
    });
    s.addText(r.t, {
      x: 1.35, y: y + 0.1, w: 3.7, h: 0.4,
      fontSize: 12, color: C.white, fontFace: FONT_BODY, margin: 0
    });
  });

  // 右：action items
  s.addText("等待你的决定", {
    x: 5.4, y: 1.25, w: 4.0, h: 0.35,
    fontSize: 14, color: C.gold, fontFace: FONT_BODY, bold: true
  });
  s.addText([
    { text: "□ 切换 Kenney 16-bit 替换 FE8? (1 天)", options: { bullet: true, breakLine: true, color: C.white } },
    { text: "□ 走 M2 路线 (WS+REST+MapLogic)?", options: { bullet: true, breakLine: true, color: C.white } },
    { text: "□ 装 GUT 替换手写 smoke_test?", options: { bullet: true, breakLine: true, color: C.white } },
    { text: "□ Dialogic 2 接入主线剧情?", options: { bullet: true, breakLine: true, color: C.white } },
    { text: "□ 切到 32×32 tile + 高级相机?", options: { bullet: true, color: C.white } },
  ], {
    x: 5.4, y: 1.7, w: 4.0, h: 2.4,
    fontSize: 12, fontFace: FONT_BODY, paraSpaceAfter: 6
  });

  // 底部 CTA
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 4.5, w: 9, h: 0.6,
    fill: { color: C.gold }, line: { type: "none" }, rectRadius: 0.1
  });
  s.addText("Commit df39cbc · 分支 codex/godot-map-port · smoke test 55/55 · 6 张截图 · 0 个临时文件残留", {
    x: 0.5, y: 4.5, w: 9, h: 0.6,
    fontSize: 13, color: C.navy, fontFace: FONT_BODY, bold: true, align: "center", valign: "middle"
  });

  // 页脚
  s.addText("BattleBlitz Godot 客户端 · 资源导航", {
    x: 0.5, y: 5.30, w: 5, h: 0.25,
    fontSize: 9, color: C.iceLt, fontFace: FONT_BODY
  });
  s.addText(`8 / 8`, {
    x: 9.0, y: 5.30, w: 0.7, h: 0.25,
    fontSize: 9, color: C.iceLt, fontFace: FONT_BODY, align: "right"
  });
}

// =================== 写出 ===================
const out = path.resolve(__dirname, "Godot资源导航.pptx");
pres.writeFile({ fileName: out })
  .then((fn) => {
    console.log(`✓ Wrote: ${fn}`);
    console.log(`  Size: ${(fs.statSync(fn).size / 1024).toFixed(1)} KB`);
    console.log(`  Slides: 8`);
  })
  .catch((err) => {
    console.error(`✗ Failed:`, err);
    process.exit(1);
  });
