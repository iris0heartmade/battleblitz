/* ============================================================
   BattleBlitz client - vanilla JS
   ============================================================ */

const API = "";  // same origin

// ----- Persistent settings (localStorage) -----
const STORAGE_KEY = "battleblitz.settings.v1";
const SESSION_KEY = "battleblitz.session.v1";
const defaultSettings = {
  playerName: "",
  preferredColor: "",
  theme: "classic",
  refreshSeconds: 3,
  soundOn: false,
};
function loadSettings() {
  try {
    return { ...defaultSettings, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return { ...defaultSettings };
  }
}
function saveSettings(s) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

// Session: persists {game_id, player_id, user_name} so a refresh returns you to your game.
function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}
function saveSession(s) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}
function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

// ----- App state -----
const state = {
  settings: loadSettings(),
  me: { player_id: null, user_name: null, color: null, game_id: null, seat: null },
  game: null,            // GameStateOut
  selectedUnit: null,    // UnitOut (the unit whose bubble is currently open)
  actionMode: null,      // "move" | "attack" | "range" | null (driven by bubble)
  pendingMove: null,     // { toX, toY } - awaiting move confirmation
  path: null,            // [{x, y}, ...] - computed path for mouse hover
  refreshTimer: null,
  presets: null,         // { maps: [], unit_compositions: [] }
  refPanelOpen: false,
  refTab: "terrain",
  lastTurnKey: null,     // for detecting turn changes (banner trigger)
  actionsTaken: 0,
  actionsRequired: 2,
  bannerTimeout: null,
  // ----- 主线模式状态 -----
  mainline: null,             // { id, title, total_battles, battle_index, state }  活跃主线
  mainlineGameId: null,       // 主线中正在进行的 game.id
  mainlinePlayerId: null,     // 该 game 中的人类玩家 id
  mainlineAdvancePending: false, // 防止 advance 重复触发
};

// ----- API helpers -----
async function api(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  let r;
  try {
    r = await fetch(API + path, opts);
  } catch (netErr) {
    // 网络层失败（如 fetch 本身抛 TypeError）
    const err = new Error(`network error: ${netErr.message || netErr}`);
    err.status = 0;
    err.body = null;
    throw err;
  }
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    // 关键：保留 status / body / detail 让 catch 能精准判断
    const detail = (data && typeof data === "object") ? data.detail : null;
    const msgText = (() => {
      if (typeof detail === "string") return detail;
      if (detail && typeof detail === "object") {
        // 结构化 detail：取 hint / message / error 任意一项作 message
        return detail.hint || detail.message || detail.error || JSON.stringify(detail);
      }
      return r.statusText || `HTTP ${r.status}`;
    })();
    const err = new Error(msgText);
    err.status = r.status;          // 关键：让 catch 能判 409
    err.body = data;                // 关键：完整 body
    err.detail = detail;            // 关键：直接拿 FastAPI detail
    err.url = `${method} ${path}`;
    throw err;
  }
  return data;
}

// ----- View switching -----
function showView(name) {
  document.querySelectorAll(".view").forEach(v => { v.hidden = true; });
  const el = document.getElementById("view-" + name);
  if (el) el.hidden = false;
}

function toast(msg, ms = 2200) {
  const t = document.getElementById("game-toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

// ============================================================
// Generic in-game modal — replaces window.alert/confirm/prompt
// for editor flows. Returns a Promise that resolves with the
// clicked button's `value`, or null if dismissed.
// ============================================================
let _modalResolve = null;
function showModal({ title = "", body = "", buttons = [] } = {}) {
  const modal = document.getElementById("generic-modal");
  const titleEl = document.getElementById("generic-modal-title");
  const bodyEl = document.getElementById("generic-modal-body");
  const btnRow = document.getElementById("generic-modal-buttons");
  if (!modal) return Promise.resolve(null);
  titleEl.textContent = title;
  // body can be a string or a DOM node
  bodyEl.innerHTML = "";
  if (typeof body === "string") {
    bodyEl.textContent = body;
  } else if (body instanceof Node) {
    bodyEl.appendChild(body);
  }
  btnRow.innerHTML = "";
  buttons.forEach((b) => {
    const btn = document.createElement("button");
    btn.className = `btn ${b.kind === "danger" ? "btn-accent" : (b.kind === "primary" ? "btn-primary" : "btn-secondary")}`;
    btn.textContent = b.label;
    btn.addEventListener("click", () => {
      modal.hidden = true;
      const r = _modalResolve;
      _modalResolve = null;
      if (r) r(b.value);
    });
    btnRow.appendChild(btn);
  });
  modal.hidden = false;
  return new Promise((resolve) => { _modalResolve = resolve; });
}

// Convenience: yes/no confirm
function showConfirm(message, { title = "请确认", confirmLabel = "确定", cancelLabel = "取消", danger = false } = {}) {
  return showModal({
    title,
    body: message,
    buttons: [
      { label: cancelLabel, value: false, kind: "secondary" },
      { label: confirmLabel, value: true, kind: danger ? "danger" : "primary" },
    ],
  });
}

// Convenience: alert/info
function showAlert(message, { title = "提示", okLabel = "好" } = {}) {
  return showModal({
    title,
    body: message,
    buttons: [{ label: okLabel, value: true, kind: "primary" }],
  });
}

// ----- View renderers -----
function renderSettings() {
  document.getElementById("setting-name").value = state.settings.playerName;
  document.getElementById("setting-color").value = state.settings.preferredColor || "";
  document.getElementById("setting-theme").value = state.settings.theme;
  document.getElementById("setting-refresh").value = state.settings.refreshSeconds;
  document.getElementById("setting-sound").checked = state.settings.soundOn;
  applyTheme(state.settings.theme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme === "dark" ? "dark" : "");
}

// ----- 存档管理视图 -----

const SAVE_STATUS_LABEL = {
  waiting: "等待中",
  playing: "进行中",
  finished: "已结束",
};

function formatGameName(g) {
  // 主线模式的存档名形如 "mainline:chapter_01_steel_rebellion:battle_01"
  // 开房模式是用户输入的任意名字
  if (g.name && g.name.startsWith("mainline:")) {
    const parts = g.name.split(":");
    return `主线 · ${parts[1] || g.name}`;
  }
  return g.name || `#${g.id}`;
}

async function renderSavesView() {
  const openEl = document.getElementById("saves-open");
  const mlEl = document.getElementById("saves-mainline");
  openEl.innerHTML = `<p class="muted">加载中…</p>`;
  mlEl.innerHTML = `<p class="muted">加载中…</p>`;
  // Only fetch the current user's games (don't show other players' saves)
  const userName = (state.settings.playerName || "").trim();
  let games = [];
  try {
    const query = userName ? `?user_name=${encodeURIComponent(userName)}` : "";
    games = await api("GET", "/games" + query);
  } catch (e) {
    openEl.innerHTML = `<p class="error-text">加载失败：${escapeHtml(e.message)}</p>`;
    mlEl.innerHTML = "";
    return;
  }
  const open = games.filter(g => !(g.name || "").startsWith("mainline:"));
  const ml = games.filter(g => (g.name || "").startsWith("mainline:"));
  renderSavesList(openEl, open, "暂无开房模式存档。");
  renderSavesList(mlEl, ml, "暂无主线模式存档。");
}

function renderSavesList(container, games, emptyMsg) {
  if (!games.length) {
    container.innerHTML = `<p class="muted">${escapeHtml(emptyMsg)}</p>`;
    return;
  }
  container.innerHTML = "";
  for (const g of games) {
    const card = document.createElement("div");
    card.className = "save-card";
    const statusLabel = SAVE_STATUS_LABEL[g.status] || g.status;
    card.innerHTML = `
      <div class="save-info">
        <div class="save-name">${escapeHtml(formatGameName(g))} <span class="muted">#${g.id}</span></div>
        <div class="muted small">
          状态: ${escapeHtml(statusLabel)} · 回合 ${g.turn_number ?? "?"} · 种子 ${g.map_seed ?? "?"}
        </div>
        <div class="muted small">${escapeHtml(g.created_at || "")}</div>
      </div>
      <button class="btn btn-danger btn-sm" data-action="save-delete" data-game-id="${g.id}" data-game-name="${escapeHtml(formatGameName(g))}">🗑️ 删除</button>
    `;
    container.appendChild(card);
  }
}

async function renderJoinList() {
  const list = document.getElementById("join-list");
  list.innerHTML = `<p class="muted">加载中…</p>`;
  try {
    const games = await api("GET", "/games");
    const waiting = games.filter(g => g.status === "waiting");
    if (!waiting.length) {
      list.innerHTML = `<p class="muted">当前没有等待中的房间。回到主菜单创建一个吧～</p>`;
      return;
    }
    list.innerHTML = "";
    for (const g of waiting) {
      const item = document.createElement("div");
      item.className = "join-item";
      item.innerHTML = `
        <div class="info">
          <div class="name">#${g.id} · ${escapeHtml(g.name)}</div>
          <div class="meta">种子 ${g.map_seed} · 创建于 ${new Date(g.created_at).toLocaleTimeString()}</div>
        </div>
        <div class="arrow">→</div>
      `;
      item.addEventListener("click", () => joinGame(g.id));
      list.appendChild(item);
    }
  } catch (e) {
    list.innerHTML = `<p class="error-text">加载失败：${escapeHtml(e.message)}</p>`;
  }
}

async function createGame() {
  const name = document.getElementById("new-name").value.trim() || `房间-${Date.now()}`;
  const max = parseInt(document.getElementById("new-max-players").value);
  const seedRaw = document.getElementById("new-seed").value.trim();
  const mapPreset = document.getElementById("new-map-preset").value;
  const unitComp = document.getElementById("new-unit-composition").value;
  const errEl = document.getElementById("new-error");
  errEl.hidden = true;
  try {
    const body = { name, max_players: max };
    if (seedRaw) body.map_seed = parseInt(seedRaw);
    if (mapPreset) body.map_preset = mapPreset;
    if (unitComp) body.unit_composition = unitComp;
    const g = await api("POST", "/games", body);
    // Immediately join as creator
    await joinGame(g.id);
  } catch (e) {
    errEl.textContent = "创建失败：" + e.message;
    errEl.hidden = false;
  }
}

async function loadPresets() {
  if (state.presets) return state.presets;
  state.presets = await api("GET", "/games/presets");
  return state.presets;
}

async function fetchUnitClasses() {
  if (Object.keys(UNIT_CLASSES).length > 0) return;
  try {
    const units = await api("GET", "/games/units");
    for (const u of units) {
      UNIT_CLASSES[u.type_id] = u;
      CAN_MOVE_AFTER[u.type_id] = u.can_move_after_action;
    }
    // Re-render editor board now that glyphs are known (fixes "?" placeholders
    // when units are placed before this async fetch completes).
    if (typeof renderEditorBoard === "function") renderEditorBoard();
    if (typeof refreshEditorToolGlyphs === "function") refreshEditorToolGlyphs();
    const skills = await api("GET", "/games/skills");
    for (const s of skills) {
      SKILL_REF.push({ name: `${s.display_cn} (${s.skill_id})`, desc: `${s.is_passive ? "被动" : "主动"} · 默认拥有: ${(s.default_users||[]).join(",")}` });
      SKILL_MAP[s.skill_id] = s.display_cn;
    }
  } catch (e) {
    // fallback
  }
}

async function populatePresetSelects() {
  const presets = await loadPresets();
  const mapSel = document.getElementById("new-map-preset");
  const unitsSel = document.getElementById("new-unit-composition");
  for (const m of presets.maps) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.name} — ${m.description}`;
    opt.dataset.desc = m.description;
    mapSel.appendChild(opt);
  }
  for (const u of presets.unit_compositions) {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = `${u.name} — ${u.description}`;
    opt.dataset.desc = u.description;
    unitsSel.appendChild(opt);
  }
  updatePresetDescription(mapSel, document.getElementById("new-map-desc"));
  updatePresetDescription(unitsSel, document.getElementById("new-units-desc"));
}

function updatePresetDescription(sel, target) {
  const opt = sel.options[sel.selectedIndex];
  target.textContent = opt?.dataset?.desc || "";
}

async function joinGame(gid) {
  const userName = (state.settings.playerName || "").trim() || `玩家-${Math.floor(Math.random() * 999)}`;
  try {
    const p = await api("POST", `/games/${gid}/join`, {
      user_name: userName,
      color: state.settings.preferredColor || undefined,
    });
    state.me = {
      player_id: p.id, user_name: p.user_name, color: p.color,
      game_id: gid, seat: p.seat,
    };
    state.settings.playerName = p.user_name; // remember name
    saveSettings(state.settings);
    saveSession({ game_id: gid, player_id: p.id, user_name: p.user_name });
    await enterLobby(gid);
  } catch (e) {
    toast("加入失败：" + e.message, 3000);
  }
}

// Try to resume a previously-saved session. Returns true if rejoin succeeded.
async function tryResumeSession() {
  const sess = loadSession();
  if (!sess || !sess.game_id || !sess.player_id) {
    updateResumeButton(null);
    return false;
  }
  try {
    const r = await api("POST", `/games/${sess.game_id}/rejoin`, { player_id: sess.player_id });
    state.me = {
      player_id: r.player.id,
      user_name: r.player.user_name,
      color: r.player.color,
      game_id: r.game_id,
      seat: r.player.seat,
    };
    if (r.game_status === "waiting") {
      await enterLobby(r.game_id);
    } else if (r.game_status === "playing") {
      await enterGame();
    } else {
      // finished -> drop session and let user return to menu
      clearSession();
      updateResumeButton(null);
      return false;
    }
    return true;
  } catch (e) {
    // game or player no longer exists -> clear stale session
    clearSession();
    updateResumeButton(null);
    return false;
  }
}

function updateResumeButton(sess) {
  const btn = document.getElementById("resume-btn");
  if (!btn) return;
  if (sess && sess.game_id && sess.player_id) {
    btn.hidden = false;
    btn.textContent = `▶ 继续房间 #${sess.game_id}（${sess.user_name || ""}）`;
  } else {
    btn.hidden = true;
  }
}

async function enterLobby(gid) {
  showView("lobby");
  document.getElementById("lobby-id").textContent = gid;
  await refreshLobby(gid);
  // Poll for player list updates
  state.lobbyTimer = setInterval(() => refreshLobby(gid), 2000);
}

async function refreshLobby(gid) {
  try {
    const st = await api("GET", `/games/${gid}/state`);
    renderLobby(st);
    // Auto-start: if creator (seat 0) and 2+ players and still waiting → maybe auto-start
    // We let user click Start manually.
  } catch (e) {
    // game might not exist
    document.getElementById("lobby-status").textContent = "加载失败：" + e.message;
  }
}

function renderLobby(st) {
  const status = document.getElementById("lobby-status");
  const list = document.getElementById("lobby-players");
  const startBtn = document.getElementById("lobby-start-btn");
  const addAiBtn = document.getElementById("lobby-add-ai-btn");

  if (st.game.status === "playing") {
    clearInterval(state.lobbyTimer);
    enterGame();
    return;
  }
  if (st.game.status === "finished") {
    status.textContent = "游戏已结束。";
    return;
  }

  const realPlayerCount = st.players.filter(p => !p.is_ai).length;
  status.textContent = `等待玩家加入…（${st.players.length} / ${st.game.status === "waiting" ? "..." : ""}, 真人 ${realPlayerCount}）`;
  list.innerHTML = "";
  for (const p of st.players) {
    const div = document.createElement("div");
    div.className = "lobby-player" + (p.id === state.me.player_id ? " is-self" : "") + (p.is_ai ? " ai" : "");
    let html = `
      <div class="swatch" style="background: ${playerColorCss(p.color)}"></div>
      <div>${escapeHtml(p.user_name)}${p.id === state.me.player_id ? " (你)" : ""}</div>
    `;
    if (p.is_ai) {
      const kind = p.agent_kind || "rules";
      const pers = p.agent_personality || "balanced";
      const badgeText = kind === "llm"
        ? `LLM (${pers})`
        : "规则 AI";
      html += `<span class="ai-badge">${badgeText}</span>`;
    }
    // Only the room creator (seat 0) can remove AI players
    if (p.is_ai && state.me.seat === 0) {
      html += `<button class="remove-btn" data-action="remove-ai" data-player-id="${p.id}" title="移除 AI">✕</button>`;
    }
    div.innerHTML = html;
    list.appendChild(div);
  }

  // Only creator can add AI, and only while game is waiting and slots available
  addAiBtn.hidden = state.me.seat !== 0 || st.players.length >= 4;
  const canStart = st.players.length >= 2 && state.me.seat === 0;
  startBtn.disabled = !canStart;
}

async function addAIPlayer() {
  const gid = state.me.game_id;
  const kind = document.getElementById("lobby-ai-kind")?.value || "rules";
  const personality = document.getElementById("lobby-ai-personality")?.value || "balanced";
  try {
    await api("POST", `/games/${gid}/add-ai`, {
      difficulty: "normal",
      agent_kind: kind,
      personality: personality,
    });
    toast(`已加入 ${kind === "llm" ? "LLM Agent" : "规则 AI"}`);
    await refreshLobby(gid);
  } catch (e) {
    toast("加入 AI 失败：" + e.message, 3000);
  }
}

async function removeAIPlayer(playerId) {
  const gid = state.me.game_id;
  if (!confirm("确定要移除这个 AI 吗？")) return;
  try {
    await api("DELETE", `/games/${gid}/players/${playerId}`);
    toast("已移除 AI");
    await refreshLobby(gid);
  } catch (e) {
    toast("移除失败：" + e.message, 3000);
  }
}

async function startGame() {
  const gid = state.me.game_id;
  try {
    await api("POST", `/games/${gid}/start`);
    clearInterval(state.lobbyTimer);
    await enterGame();
  } catch (e) {
    toast("开始失败：" + e.message, 3000);
  }
}

// ============================================================
// Game view
// ============================================================

async function enterGame() {
  showView("game");
  await refreshGame();
  // start polling
  clearInterval(state.refreshTimer);
  const interval = Math.max(1000, state.settings.refreshSeconds * 1000);
  state.refreshTimer = setInterval(refreshGame, interval);
}

async function refreshGame() {
  if (!state.me.game_id) return;
  try {
    const st = await api("GET", `/games/${state.me.game_id}/state`);
    state.game = st;
    renderGame(st);
  } catch (e) {
    toast("状态获取失败：" + e.message, 2500);
  }
}

function renderGame(st) {
  // Header
  document.getElementById("game-turn").textContent = st.game.turn_number;
  const cur = st.players.find(p => p.id === st.current_player_id);
  const curIsAI = cur?.is_ai;
  document.getElementById("game-current-player").textContent = cur ? `${cur.user_name}${curIsAI ? " 🤖" : ""}` : "—";
  document.getElementById("game-map-seed").textContent = st.game.map_seed;
  const mapNameEl = document.getElementById("game-map-name");
  if (mapNameEl) mapNameEl.textContent = st.game.map_preset || "经典随机";

  // Show "AI thinking" badge when current player is AI and game is playing
  const thinkingEl = document.getElementById("game-thinking");
  thinkingEl.hidden = !(st.game.status === "playing" && curIsAI);

  // Turn-change banner
  const turnKey = `${st.game.turn_number}|${st.current_player_id}|${st.game.status}`;
  if (turnKey !== state.lastTurnKey && st.game.status === "playing") {
    state.lastTurnKey = turnKey;
    if (cur) showTurnBanner(cur, st.game.turn_number);
  }

  // Action counter (only count my units)
  if (cur && cur.id === state.me.player_id) {
    const myUnits = st.players.find(p => p.id === state.me.player_id)?.units || [];
    const acted = myUnits.filter(u => u.hp > 0 && u.has_acted).length;
    state.actionsTaken = acted;
    // Required: 2 normally; 1 if I'm first player on first turn (heuristic:
    // the first turn is turn 1, and the only "first player" is seat 0)
    const myPlayer = st.players.find(p => p.id === state.me.player_id);
    state.actionsRequired = (myPlayer?.seat === 0 && st.game.turn_number === 1) ? 1 : 2;
    updateActionCounter();
  } else {
    // Reset when not my turn
    state.actionsTaken = 0;
    state.actionsRequired = 2;
    updateActionCounter();
  }

  // Game over modal
  if (st.game.status === "finished") {
    clearInterval(state.refreshTimer);

    // 主线模式中：把胜负判定交给 MainlineView 处理；不显示原生 modal
    if (state.mainline && state.mainlineGameId === st.game.id && !state.mainlineAdvancePending) {
      state.mainlineAdvancePending = true;
      // 异步触发 advance，不阻塞 render 后续
      MainlineView.onBattleFinished(st).catch((e) => {
        toast("主线推进失败：" + e.message, 3000);
        state.mainlineAdvancePending = false;
        // 退化：还是显示原生 modal，让用户能返回大厅
        document.getElementById("game-over-modal").hidden = false;
      });
    } else {
      document.getElementById("game-over-modal").hidden = false;
      const alive = st.players.filter(p => p.is_alive);
      if (alive.length === 1) {
        document.getElementById("game-over-title").textContent = `🏆 ${alive[0].user_name} 获胜！`;
        document.getElementById("game-over-body").textContent = `对手全灭。`;
      } else if (alive.length === 0) {
        document.getElementById("game-over-title").textContent = `⚖️ 平局`;
        document.getElementById("game-over-body").textContent = `所有玩家都被淘汰。`;
      } else {
        document.getElementById("game-over-title").textContent = `🏆 游戏结束`;
        document.getElementById("game-over-body").textContent = `有玩家获胜了。`;
      }
    }
  } else {
    document.getElementById("game-over-modal").hidden = true;
    state.mainlineAdvancePending = false;
  }

  renderBoard(st);
  renderUnitInfo(st);
  renderPlayersList(st);
  renderActionLog(st);
}

function showTurnBanner(player, turnNum) {
  const banner = document.getElementById("turn-banner");
  document.getElementById("banner-title").textContent = `${player.user_name} 的回合`;
  document.getElementById("banner-sub").textContent = `第 ${turnNum} 回合 · ${player.is_ai ? "🤖 电脑" : "🎮 玩家"}`;
  document.getElementById("banner-icon").textContent = player.is_ai ? "🤖" : "⚔️";
  // Re-trigger the CSS animation
  banner.hidden = true;
  // Force reflow to restart animation
  void banner.offsetWidth;
  banner.hidden = false;
  clearTimeout(state.bannerTimeout);
  state.bannerTimeout = setTimeout(() => {
    banner.hidden = true;
  }, 3000);
}

function updateActionCounter() {
  // No-op: per-player action counter was removed. Each unit acts
  // independently and the player may end their turn at any time.
  // The end-turn button is enabled whenever it's the player's turn.
  const endBtn = document.querySelector('[data-action="end-turn"]');
  if (endBtn) {
    const isMyTurn = state.game?.current_player_id === state.me.player_id;
    endBtn.disabled = !isMyTurn;
    endBtn.title = isMyTurn ? "" : "还没轮到你";
  }
}

// Auto-fit board to viewport so a 15x15 grid never overflows on small
// screens. Sets the --cell-size CSS var on #board; both .board's grid
// template and .cell width/height read from the same var. Bound to
// resize / orientationchange, plus called once at startup and at the
// start of every renderBoard (cheap: ~5 arithmetic ops + 1 setProperty).
const BOARD_SIZE = 15;            // MAP_SIZE — keep in sync with backend
const CELL_MIN = 14;              // hard floor so tiles stay readable
const CELL_MAX = 48;              // hard ceiling (desktop default 44)

function fitBoard() {
  const board = document.getElementById("board");
  if (!board) return;
  // Avoid running before layout exists
  const viewportW = window.innerWidth  || document.documentElement.clientWidth;
  const viewportH = window.innerHeight || document.documentElement.clientHeight;
  if (!viewportW || !viewportH) return;

  // Reserve room for top toolbar + bottom browser chrome + breathing room.
  // Measured from style.css: .game-header ≈ 56px, chat-float/banner etc.
  // add up to ~80px on mobile; use 160px safety budget.
  const RESERVED_H = 160;
  // .board's own padding (16px) + 1px borders (left+top) add 34px to width.
  // Without this, 15*cellSize exactly fits but the board still overflows by 34px.
  const BOARD_BOX_W = 34;
  const BOARD_BOX_H = 34;

  const maxByW = (viewportW - BOARD_BOX_W) / BOARD_SIZE;
  const maxByH = (viewportH - RESERVED_H - BOARD_BOX_H) / BOARD_SIZE;
  const cellSize = Math.max(
    CELL_MIN,
    Math.min(CELL_MAX, Math.floor(Math.min(maxByW, maxByH)))
  );

  // DEBUG: helps the user verify the calc from DevTools. Remove once confirmed.
  console.log("[fitBoard]", { viewportW, viewportH, maxByW, maxByH, cellSize });

  board.style.setProperty("--cell-size", cellSize + "px");
}

window.addEventListener("resize",            fitBoard);
window.addEventListener("orientationchange", fitBoard);
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", fitBoard);
} else {
  fitBoard();
}

// Tile image lookup: terrain + biome → asset URL (with deterministic variant)
// variant count per terrain:
const TILE_VARIANTS = {
  plain: 2, forest: 2, mountain: 2, river: 4, castle: 2, desert: 2, snow: 2,
};
// Terrains whose palette depends on game biome
const BIOME_AWARE_TERRAINS = new Set(["forest", "castle"]);

function pickTileVariant(terrain, x, y) {
  const n = TILE_VARIANTS[terrain] || 2;
  // Deterministic pseudo-random based on (x, y, terrain)
  let h = 0;
  for (const c of terrain) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  h = (h ^ (x * 73856093) ^ (y * 19349663)) >>> 0;
  return h % n;
}

function tileImageUrl(terrain, biome, x, y) {
  const variant = pickTileVariant(terrain, x, y);
  const base = BIOME_AWARE_TERRAINS.has(terrain) ? `${terrain}_${biome}` : terrain;
  return `/ui/assets/tiles/${base}_v${variant}.png`;
}

// Editor stores terrain as single chars (P/F/M/R/C) for compact JSON.
// Convert to full terrain names for rendering and CSS class lookup.
const TERRAIN_CHAR_TO_NAME = {
  P: "plain", F: "forest", M: "mountain", R: "river", C: "castle",
};
function terrainNameFromChar(ch) {
  return TERRAIN_CHAR_TO_NAME[ch] || "plain";
}

function renderBoard(st) {
  const board = document.getElementById("board");
  // Determine board dimensions from tiles (supports custom-sized maps)
  let boardW = BOARD_SIZE, boardH = BOARD_SIZE;
  for (const t of st.tiles) {
    if (t.x + 1 > boardW) boardW = t.x + 1;
    if (t.y + 1 > boardH) boardH = t.y + 1;
  }
  const biome = st.game?.map_biome || "grass";
  // Force grid layout via inline style (overrides any CSS issues).
  board.style.display = "grid";
  board.style.gridTemplateColumns = `repeat(${boardW}, var(--cell-size))`;
  board.style.gridTemplateRows = `repeat(${boardH}, var(--cell-size))`;
  fitBoard();
  // Build cells map for quick lookup
  const tileMap = new Map();
  for (const t of st.tiles) tileMap.set(`${t.x},${t.y}`, t);

  const unitMap = new Map();
  for (const p of st.players) {
    for (const u of p.units) unitMap.set(`${u.x},${u.y}`, { unit: u, player: p });
  }

  // FLIP step 1 (First): capture old positions of every unit currently in the DOM
  const oldPositions = new Map(); // unit_id -> {left, top}
  for (const u of document.querySelectorAll(".unit")) {
    const id = u.dataset.unitId;
    if (!id) continue;
    const r = u.getBoundingClientRect();
    oldPositions.set(id, { left: r.left, top: r.top });
  }

  const frag = document.createDocumentFragment();
  for (let y = 0; y < boardH; y++) {
    for (let x = 0; x < boardW; x++) {
      const tile = tileMap.get(`${x},${y}`);
      const cell = document.createElement("div");
      const terrain = tile?.terrain || "plain";
      cell.className = "cell t-" + terrain;
      cell.dataset.x = x;
      cell.dataset.y = y;
      cell.style.gridColumn = String(x + 1);
      cell.style.gridRow = String(y + 1);
      // Background tile image (pixel art)
      cell.style.backgroundImage = `url(${tileImageUrl(terrain, biome, x, y)})`;

      const occupant = unitMap.get(`${x},${y}`);
      if (occupant) {
        const u = occupant.unit;
        const uEl = document.createElement("div");
        uEl.className = `unit u-${occupant.player.color}` + (u.has_acted ? " acted" : "");
        uEl.dataset.unitId = u.id;
        uEl.textContent = unitGlyph(u.unit_type);
        uEl.title = `${u.name} (Lv.${u.level}) HP ${u.hp}/${u.max_hp} MP ${u.mp ?? u.mov}/${u.mov} 士气 ${u.morale ?? 0}/3`;
        const hp = document.createElement("div");
        hp.className = "hpbar";
        const fill = document.createElement("div");
        const pct = u.max_hp ? (u.hp / u.max_hp) * 100 : 0;
        fill.style.width = pct + "%";
        if (pct < 35) fill.classList.add("low");
        hp.appendChild(fill);
        uEl.appendChild(hp);
        // MP badge: small "MP x/y" text at top-right corner
        const mpBadge = document.createElement("div");
        mpBadge.className = "mp-badge";
        mpBadge.textContent = `⚡${u.mp ?? u.mov}`;
        uEl.appendChild(mpBadge);
        // Morale stars (3 slots)
        const moraleEl = document.createElement("div");
        moraleEl.className = "morale-stars";
        const m = u.morale ?? 0;
        moraleEl.textContent = "★".repeat(m) + "☆".repeat(Math.max(0, 3 - m));
        moraleEl.title = `士气 ${m}/3 (攻击 +${(m * 10)}%, 防御 +${(m * 5)}%)`;
        uEl.appendChild(moraleEl);
        cell.appendChild(uEl);
      }

      // Highlights
      if (state.selectedUnit && state.selectedUnit.x === x && state.selectedUnit.y === y) {
        cell.classList.add("selected");
      }
      if (state.actionMode === "range") {
        // Range-view mode: red translucent overlay on attackable tiles
        if (state.attackTargets?.has(`${x},${y}`)) {
          cell.classList.add("range-hint");
        }
      } else {
        // Normal mode: show movement range (green) and attack targets (red)
        if (state.reachableTiles?.has(`${x},${y}`) && !state.pendingMove) {
          cell.classList.add("move-hint");
        }
        if (state.attackTargets?.has(`${x},${y}`)) {
          cell.classList.add("target");
        }
      }

      // Mouse-hover movement path dots
      if (state.path && state.path.length > 2) {
        const pi = state.path.findIndex(p => p.x === x && p.y === y);
        if (pi > 0 && pi < state.path.length - 1) {
          cell.classList.add("path-dot");
        }
        if (pi === state.path.length - 1) {
          cell.classList.add("path-dot", "path-end");
        }
      }

      cell.addEventListener("click", () => onCellClick(x, y, st));
      cell.addEventListener("mouseenter", () => onCellHover(x, y));
      frag.appendChild(cell);
    }
  }
  board.innerHTML = "";
  board.appendChild(frag);

  // FLIP step 2 (Last -> Invert -> Play): for each unit that moved, animate
  // from its old screen position back to the new one.
  const newPositions = new Map();
  for (const u of document.querySelectorAll(".unit")) {
    const id = u.dataset.unitId;
    if (!id) continue;
    const r = u.getBoundingClientRect();
    newPositions.set(id, { left: r.left, top: r.top });
  }
  for (const [id, newPos] of newPositions) {
    const old = oldPositions.get(id);
    if (!old) continue; // brand new unit - no animation
    const dx = old.left - newPos.left;
    const dy = old.top - newPos.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    const el = document.querySelector(`.unit[data-unit-id="${id}"]`);
    if (!el) continue;
    // Invert: jump back to old position with no transition
    el.style.transition = "none";
    el.style.transform = `translate(${dx}px, ${dy}px)`;
    // Play: next frame, animate to natural position
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.transition = "transform 320ms cubic-bezier(0.4, 0, 0.2, 1)";
        el.style.transform = "";
      });
    });
  }
}

// ============================================================
// Bubble-based unit interaction
// ============================================================
//
// Flow:
// 1. Click own unit (can act)        -> unit bubble: 移动 / 射程 / 状态 / 待机
// 2. Click "移动"                    -> move mode (green hints, small hint bubble)
// 3. Click destination               -> confirm bubble: ✅ / ❌
// 4. After ✅                        -> if enemies in attack range:
//                                        action bubble: ⚔️[enemy1] ⚔️[enemy2] ⏭ 待机
//                                      else close bubble
// 5. Click own unit (acted)          -> inspect bubble: just info
// 6. Click any unit                  -> inspect bubble: stats + HP bar

function findUnitAt(st, x, y) {
  for (const p of st.players) {
    for (const u of p.units) {
      if (u.x === x && u.y === y && u.hp > 0) return { unit: u, player: p };
    }
  }
  return null;
}

function findEnemyAt(st, x, y) {
  const occ = findUnitAt(st, x, y);
  if (!occ) return null;
  if (occ.player.id === state.me.player_id) return null;
  return occ;
}

function computeReachable(unit) {
  // Estimate reachable tiles client-side (server pathfind is authoritative).
  // Budget is the unit's remaining MP (falls back to full MOV if MP is unset).
  const st = state.game;
  const tileMap = new Map();
  for (const t of st.tiles) tileMap.set(`${t.x},${t.y}`, t);
  const occupied = new Set();
  for (const p of st.players) for (const u of p.units) {
    if (u.id !== unit.id && u.hp > 0) occupied.add(`${u.x},${u.y}`);
  }
  const budget = (typeof unit.mp === "number" && unit.mp > 0) ? unit.mp : unit.mov;
  const reachable = new Set();
  const queue = [{ x: unit.x, y: unit.y, cost: 0 }];
  const visited = new Map([[`${unit.x},${unit.y}`, 0]]);
  // Manhattan-adjacency only (no diagonals): movement is 4-directional.
  const dirs = [[1,0],[-1,0],[0,1],[0,-1]];
  const costs = { plain: 1, forest: 2, mountain: 3, river: 3, castle: 1 };
  while (queue.length) {
    const cur = queue.shift();
    for (const [dx, dy] of dirs) {
      const nx = cur.x + dx, ny = cur.y + dy;
      if (nx < 0 || nx >= 15 || ny < 0 || ny >= 15) continue;
      const key = `${nx},${ny}`;
      const t = tileMap.get(key);
      if (!t) continue;
      if (t.terrain === "castle" && t.owner_id !== null && t.owner_id !== state.me.player_id) continue;
      if (occupied.has(key)) continue;
      const stepCost = costs[t.terrain] ?? 1;
      const newCost = cur.cost + stepCost;
      if (newCost > budget) continue;
      if ((visited.get(key) ?? Infinity) <= newCost) continue;
      visited.set(key, newCost);
      reachable.add(key);
      queue.push({ x: nx, y: ny, cost: newCost });
    }
  }
  return reachable;
}

function getUnitAttackProfile(unit) {
  // Returns {minRange, maxRange} where attacks hit enemies at distance d
  // (Manhattan distance: |dx| + |dy|) when minRange < d <= maxRange.
  //
  // IMPORTANT: do NOT hard-code per-unit ranges here. The server pushes the
  // class-level `attack_range` / `min_attack_range` on every unit in the
  // game-state payload, and skills like archer's `snipe` are applied on
  // top of that. Hard-coded values drift out of sync and the user ends up
  // seeing attackable tiles they can't actually hit.
  const baseMax = (typeof unit.attack_range === "number") ? unit.attack_range : 1;
  const baseMin = (typeof unit.min_attack_range === "number") ? unit.min_attack_range : 0;
  // +snipe skill on ranged extends maxRange by 1 (mirrors the server's
  // skill.modify_attack_range). If we ever add more range-modifying skills,
  // switch to a server endpoint that returns the *effective* range.
  let maxRange = baseMax;
  if ((unit.skills || []).includes("snipe")) maxRange += 1;
  return { minRange: baseMin, maxRange };
}

function manhattan(ax, ay, bx, by) {
  return Math.abs(ax - bx) + Math.abs(ay - by);
}

function canUnitAttack(unit, fromX, fromY, toX, toY) {
  const d = manhattan(fromX, fromY, toX, toY);
  if (d === 0) return false;
  const prof = getUnitAttackProfile(unit);
  return d > prof.minRange && d <= prof.maxRange;
}

// ============================================================
// Combat forecast — client-side damage prediction
// ============================================================
// Replicates the server's calculate_damage() formula so the player sees
// the predicted outcome before committing to an attack.

// Counter damage multiplier (mirrors app.config.COUNTER_DAMAGE_MULT).
const COUNTER_DAMAGE_MULT = 0.5;

const TERRAIN_DEF_BONUS = {
  plain: 0, forest: 2, mountain: 3, river: 0, castle: 5,
};

const TYPE_ADVANTAGE_FRONT = {
  swordsman: { knight: 1.20 },
  knight:    { archer: 1.20 },
};

function getTypeMultiplier(attackerType, defenderType) {
  return TYPE_ADVANTAGE_FRONT[attackerType]?.[defenderType] ?? 1.0;
}

function forecastSingleHit(attacker, defender, tileDefBonus, crit) {
  // Mirrors app.game_logic.calculate_damage
  const MORALE_ATK_PER_STAR = 0.10;
  const MORALE_DEF_PER_STAR = 0.05;
  const CRIT_MULTIPLIER = 1.5;
  const BASE_CRIT_RATE = 0.05;
  const CRIT_PER_LEVEL = 0.01;

  const atkM = attacker.morale || 0;
  const defM = defender.morale || 0;
  const effAtk = Math.max(1, attacker.atk * (1 + atkM * MORALE_ATK_PER_STAR));
  const effDef = Math.max(1, (defender.def_ + tileDefBonus) * (1 + defM * MORALE_DEF_PER_STAR));

  const base = effAtk * (effAtk / (effAtk + effDef));
  const typeMult = getTypeMultiplier(attacker.unit_type, defender.unit_type);
  const mult = crit ? typeMult * CRIT_MULTIPLIER : typeMult;
  const dmg = Math.max(1, Math.round(base * mult));

  const critRate = Math.min(1.0, BASE_CRIT_RATE + CRIT_PER_LEVEL * ((attacker.level || 1) - 1));
  const normalDmg = Math.max(1, Math.round(base * typeMult));
  const critDmg = Math.max(1, Math.round(base * typeMult * CRIT_MULTIPLIER));

  return {
    damage: dmg,
    isCrit: !!crit,
    isKill: dmg >= (defender.hp || 0),
    normalDamage: normalDmg,
    critDamage: critDmg,
    critChance: critRate,
    typeMultiplier: typeMult,
  };
}

function getDefenderTerrainBonus(targetUnit) {
  const t = state.game.tiles.find(t => t.x === targetUnit.x && t.y === targetUnit.y);
  return t ? (TERRAIN_DEF_BONUS[t.terrain] || 0) : 0;
}

function forecastAttack(attacker, defender) {
  // Main forecast: returns the predicted outcome of a normal attack + counter.
  // Counter rules: only if defender survives AND defender is currently in
  // attack range of the original attacker (i.e. can hit back).
  const tileDefBonus = getDefenderTerrainBonus(defender);
  const mainHit = forecastSingleHit(attacker, defender, tileDefBonus, /*crit=*/false);
  const mainCrit = forecastSingleHit(attacker, defender, tileDefBonus, /*crit=*/true);
  const critRate = mainHit.critChance;
  // Use the most-likely outcome (non-crit) for the headline damage.
  const mainDmg = mainHit.damage;
  const attackerHpAfter = (attacker.hp || 0) - mainDmg;
  const defenderHpAfter = (defender.hp || 0) - mainDmg;
  const mainKills = mainDmg >= (defender.hp || 0);

  // Counter attack prediction (if defender survives)
  let counter = null;
  if (!mainKills) {
    const counterRange = getUnitAttackProfile(defender).maxRange;
    const counterMin = getUnitAttackProfile(defender).minRange;
    const distToAttacker = manhattan(
      attacker.x, attacker.y,
      defender.x, defender.y
    );
    if (distToAttacker > counterMin && distToAttacker <= counterRange) {
      const counterTileBonus = getDefenderTerrainBonus(attacker);
      const counterHit = forecastSingleHit(defender, attacker, counterTileBonus, false);
      const counterDmg = Math.max(1, Math.floor(counterHit.damage * COUNTER_DAMAGE_MULT));
      counter = {
        damage: counterDmg,
        attackerHpAfter: (attacker.hp || 0) - mainDmg - counterDmg,
        willKill: counterDmg >= (attacker.hp || 0) - mainDmg,
      };
    }
  }

  return {
    main: {
      damage: mainDmg,
      normalDamage: mainHit.normalDamage,
      critDamage: mainHit.critDamage,
      critRate: critRate,
      typeMultiplier: mainHit.typeMultiplier,
      defenderHpAfter: Math.max(0, defenderHpAfter),
      willKill: mainKills,
    },
    counter,
  };
}

function computeAttackTargets(unit) {
  const st = state.game;
  const targets = new Set();
  for (const p of st.players) {
    if (p.id === state.me.player_id) continue;
    for (const u of p.units) {
      if (u.hp <= 0) continue;
      if (canUnitAttack(unit, unit.x, unit.y, u.x, u.y)) {
        targets.add(`${u.x},${u.y}`);
      }
    }
  }
  return targets;
}

function computeThreatArea(unit, reachableTiles) {
  // Compute the full "threat zone" — every tile that this unit COULD attack
  // this turn by moving to any reachable position first.
  // reachableTiles: Set of "x,y" strings that the unit can move to.
  // Returns a Set of "x,y" strings representing all attackable tiles.
  const prof = getUnitAttackProfile(unit);

  const threat = new Set();

  function addFromPosition(px, py) {
    for (let dx = -prof.maxRange; dx <= prof.maxRange; dx++) {
      for (let dy = -prof.maxRange; dy <= prof.maxRange; dy++) {
        const d = Math.abs(dx) + Math.abs(dy);  // Manhattan distance
        if (d <= prof.minRange) continue;
        if (d > prof.maxRange) continue;
        const nx = px + dx;
        const ny = py + dy;
        if (nx < 0 || nx >= 15 || ny < 0 || ny >= 15) continue;
        threat.add(`${nx},${ny}`);
      }
    }
  }

  // Threat from current position
  addFromPosition(unit.x, unit.y);

  // Threat from each reachable tile
  if (reachableTiles) {
    for (const key of reachableTiles) {
      const [rx, ry] = key.split(",").map(Number);
      addFromPosition(rx, ry);
    }
  }

  return threat;
}

// ----- Bubble rendering -----

function showBubbleAt(tileX, tileY, html, opts = {}) {
  const bubble = document.getElementById("action-bubble");
  bubble.innerHTML = html;
  bubble.classList.toggle("compact", !!opts.compact);
  bubble.hidden = false;
  // Defer positioning so the DOM is updated
  requestAnimationFrame(() => {
    const cell = document.querySelector(`.cell[data-x="${tileX}"][data-y="${tileY}"]`);
    if (!cell) { hideBubble(); return; }
    const rect = cell.getBoundingClientRect();
    // Default: above the cell, centered horizontally
    let left = rect.left + rect.width / 2;
    let top = rect.top;
    let translate = "translate(-50%, calc(-100% - 10px))";
    if (opts.position === "below") {
      top = rect.bottom;
      translate = "translate(-50%, 10px)";
      bubble.style.setProperty("--ab-arrow-side", "top");
    }
    bubble.style.left = `${left}px`;
    bubble.style.top = `${top}px`;
    bubble.style.transform = translate;
  });
}

function hideBubble() {
  const bubble = document.getElementById("action-bubble");
  if (bubble) bubble.hidden = true;
}

function renderUnitHtml(u, p) {
  const pct = u.max_hp ? Math.round(u.hp / u.max_hp * 100) : 0;
  const barColor = pct >= 50 ? "var(--good)" : pct >= 25 ? "var(--accent)" : "var(--danger)";
  return `
    <p class="name">${escapeHtml(u.name)} <span class="muted small">Lv.${u.level}</span></p>
    <p class="muted small">${unitTypeName(u.unit_type)} · ${escapeHtml(p.user_name)}</p>
    <div style="background:var(--bg);height:6px;border-radius:3px;margin:6px 0;overflow:hidden;">
      <div style="width:${pct}%;height:100%;background:${barColor};"></div>
    </div>
    <p class="muted small">HP ${u.hp}/${u.max_hp} · ATK ${u.atk} · DEF ${u.def_} · MOV ${u.mov}</p>
    ${u.skills?.length ? `<p class="muted small">技能：${u.skills.map(skillName).join("、")}</p>` : ""}
  `;
}

function showUnitActionBubble(unit) {
  state.selectedUnit = unit;
  const targets = computeAttackTargets(unit);
  const reachable = computeReachable(unit);
  state.reachableTiles = reachable;
  state.attackTargets = targets;
  state.actionMode = null;
  state.pendingMove = null;

  // Per-unit capability: each unit acts independently. If THIS unit
  // has already acted, the caller (onCellClick) shows the read-only
  // bubble instead. There is no per-player action cap.
  const canMove = reachable.size > 0;
  const canAttack = targets.size > 0;
  const canHeal = (unit.skills || []).includes("heal");
  const canRally = (unit.skills || []).includes("rally");
  const canWait = true;

  let html = `<div class="ab-title">${escapeHtml(unit.name)} · ⚡${unit.mp ?? unit.mov}/${unit.mov}</div>`;
  html += `<div class="ab-row">`;
  html += `<button class="ab-btn primary" data-ab="move" ${canMove ? "" : "disabled"}>🚶 移动</button>`;
  html += `<button class="ab-btn danger" data-ab="attack" ${canAttack ? "" : "disabled"} title="${canAttack ? `可攻击 ${targets.size} 个敌人` : "范围内无目标"}">⚔️ 攻击${canAttack ? "" : ""}</button>`;
  html += `<button class="ab-btn" data-ab="range">🎯 射程</button>`;
  html += `</div><div class="ab-row">`;
  if (canHeal) html += `<button class="ab-btn heal" data-ab="heal">💚 治疗</button>`;
  if (canRally) html += `<button class="ab-btn rally" data-ab="rally">📯 集结</button>`;
  html += `<button class="ab-btn" data-ab="info">👁 状态</button>`;
  html += `<button class="ab-btn cancel" data-ab="wait" ${canWait ? "" : "disabled"}>⏭ 待机</button>`;
  html += `</div>`;

  showBubbleAt(unit.x, unit.y, html);
  // Delegate clicks inside the bubble
  const bubble = document.getElementById("action-bubble");
  bubble.querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
}

function showMoveConfirmBubble(unit, toX, toY) {
  state.pendingMove = { toX, toY };
  state.actionMode = "move-confirm";
  const steps = state.path ? state.path.length - 1 : "?";
  const cost = state.path ? (() => {
    const tileMap = new Map();
    for (const t of state.game.tiles) tileMap.set(`${t.x},${t.y}`, t);
    const costs = { plain: 1, forest: 2, mountain: 3, river: 3, castle: 1 };
    let total = 0;
    for (let i = 1; i < state.path.length; i++) {
      const t = tileMap.get(`${state.path[i].x},${state.path[i].y}`);
      total += costs[t?.terrain] ?? 1;
    }
    return total;
  })() : "?";
  const html = `
    <div class="ab-title">移动到 (${toX}, ${toY}) · ${steps} 步 ⚡${cost}</div>
    <div class="ab-row">
      <button class="ab-btn primary" data-ab="confirm-move">✅ 确认移动</button>
      <button class="ab-btn cancel" data-ab="cancel-move">❌ 取消</button>
    </div>
  `;
  showBubbleAt(toX, toY, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
}

function showAttackConfirmBubble(attacker, target) {
  state.pendingAttack = { targetId: target.id };
  state.actionMode = "attack-confirm";
  // Compute forecast
  const fc = forecastAttack(attacker, target);
  const stars = (n) => "★".repeat(n) + "☆".repeat(Math.max(0, 3 - n));
  const m = fc.main;
  const counterLine = fc.counter
    ? `🔁 反击：${fc.counter.damage}  → 攻击者后：${fc.counter.attackerHpAfter}/${attacker.hp || "?"}HP${fc.counter.willKill ? " ☠️" : ""}`
    : (m.willKill ? "" : "（目标太远无法反击）");
  const killLine = m.willKill ? " ☠️ 击杀" : "";
  const critLine = m.critRate > 0.05 ? `暴击率 ${Math.round(m.critRate * 100)}% → ${m.critDamage} 伤害` : "";
  const typeLine = m.typeMultiplier > 1 ? `兵种克制 ×${m.typeMultiplier}` : (m.typeMultiplier < 1 ? `被克制 ×${m.typeMultiplier}` : "无克制");

  const html = `
    <div class="forecast-card">
      <div class="forecast-title">⚔️ 战斗预测</div>
      <div class="forecast-row">
        <div class="forecast-side">
          <div class="forecast-name">${escapeHtml(attacker.name)}</div>
          <div class="forecast-meta">${stars(attacker.morale || 0)} · Lv.${attacker.level || 1}</div>
          <div class="forecast-stat">ATK ${attacker.atk}</div>
          <div class="forecast-hp">HP ${attacker.hp || "?"}/${attacker.max_hp || "?"}</div>
        </div>
        <div class="forecast-vs">VS</div>
        <div class="forecast-side">
          <div class="forecast-name">${escapeHtml(target.name)}</div>
          <div class="forecast-meta">${stars(target.morale || 0)} · Lv.${target.level || 1}</div>
          <div class="forecast-stat">DEF ${target.def_}</div>
          <div class="forecast-hp">HP ${target.hp || "?"}/${target.max_hp || "?"}</div>
        </div>
      </div>
      <div class="forecast-line forecast-dmg">💥 预计伤害：${m.damage}${killLine}</div>
      <div class="forecast-line forecast-after">→ 目标后：${m.defenderHpAfter}/${target.max_hp || "?"}HP</div>
      ${critLine ? `<div class="forecast-line">${critLine}</div>` : ""}
      <div class="forecast-line forecast-aux">🎖️ ${typeLine}</div>
      ${counterLine ? `<div class="forecast-line forecast-counter">${counterLine}</div>` : ""}
    </div>
    <div class="ab-row">
      <button class="ab-btn danger" data-ab="confirm-attack">⚔️ 确认攻击</button>
      <button class="ab-btn cancel" data-ab="cancel-attack">❌ 取消</button>
    </div>
  `;
  // Use a wider bubble for the forecast
  showBubbleAt(target.x, target.y, html);
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, attacker));
  });
}

function showPostMoveBubble(unit) {
  // Called after a successful move. Decide what to offer:
  //   - enemies in range → attack options + (continue moving if can_move_after_action) + wait
  //   - no enemies, MP left and can_move_after_action → "continue moving"
  //   - otherwise → close bubble (unit is done this turn)
  const targets = computeAttackTargets(unit);
  const enemyList = [];
  for (const p of state.game.players) {
    if (p.id === state.me.player_id) continue;
    for (const u of p.units) {
      if (u.hp <= 0) continue;
      if (targets.has(`${u.x},${u.y}`)) enemyList.push(u);
    }
  }
  enemyList.sort((a, b) => a.hp - b.hp);

  const canContinue = unit.mp > 0 && unitCanMoveAfter(unit.unit_type);
  const hasContent = enemyList.length > 0 || canContinue;
  if (!hasContent) {
    toast("移动完成，当前范围内无目标");
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    state.pendingMove = null;
    return;
  }

  const parts = [`<div class="ab-title">📍 ${escapeHtml(unit.name)} · ⚡${unit.mp}/${unit.mov}</div>`];
  if (enemyList.length > 0) {
    parts.push(`<div class="ab-row">`);
    for (const e of enemyList) {
      parts.push(`<button class="ab-btn danger" data-target="${e.id}" data-ab="pick-attack">⚔️ ${escapeHtml(e.name)} (${e.hp}HP)</button>`);
    }
    parts.push(`</div>`);
  }
  parts.push(`<div class="ab-row">`);
  if (canContinue) {
    parts.push(`<button class="ab-btn primary" data-ab="move-more">🚶 继续移动 (${unit.mp} MP)</button>`);
  }
  parts.push(`<button class="ab-btn cancel" data-ab="wait">⏭ 待机</button>`);
  parts.push(`</div>`);
  showBubbleAt(unit.x, unit.y, parts.join(""));
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit, btn.dataset.target));
  });
}

function showPostAttackBubble(unit) {
  // Called after a successful attack. Only offered if class can move after
  // action and MP remains. Otherwise close.
  if (!(unit.mp > 0 && unitCanMoveAfter(unit.unit_type))) {
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    return;
  }
  const html = `
    <div class="ab-title">⚔️ ${escapeHtml(unit.name)} 已攻击 · ⚡${unit.mp}/${unit.mov}</div>
    <div class="ab-row">
      <button class="ab-btn primary" data-ab="move-more">🚶 继续移动 (${unit.mp} MP)</button>
      <button class="ab-btn cancel" data-ab="wait">⏭ 待机</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
}

function showInspectBubble(unit, player) {
  state.selectedUnit = unit;
  state.actionMode = null;
  state.reachableTiles = null;
  state.attackTargets = null;
  const html = `
    ${renderUnitHtml(unit, player)}
    <div class="ab-row">
      <button class="ab-btn" data-ab="range">🎯 射程</button>
      <button class="ab-btn cancel" data-ab="close">✕ 关闭</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
}

function showActedBubble(unit, player) {
  state.selectedUnit = unit;
  state.actionMode = null;
  const html = `
    <div class="ab-title" style="color:var(--text-dim);">⏸ 已行动</div>
    ${renderUnitHtml(unit, player)}
    <div class="ab-row">
      <button class="ab-btn" data-ab="range">🎯 射程</button>
      <button class="ab-btn cancel" data-ab="close">✕ 关闭</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
}

// ----- Bubble click dispatch -----

async function onBubbleClick(action, unit, targetId) {
  switch (action) {
    case "move":
      enterMoveMode(unit);
      break;
    case "attack":
      enterAttackMode(unit);
      break;
    case "range":
      // Compute the full threat area: all tiles this unit can attack from
      // ANY reachable position (current position + tiles within MP movement).
      state.actionMode = "range";
      state.reachableTiles = computeReachable(unit);
      state.attackTargets = computeThreatArea(unit, state.reachableTiles);
      const threatCount = state.attackTargets?.size || 0;
      renderBoard(state.game);
      toast(`威胁范围 ${threatCount} 格 · 点击任意处取消查看`);
      break;
    case "info":
      // Show full info inline (re-render bubble as info card)
      showInspectBubble(unit, state.game.players.find(p => p.id === unit.player_id));
      return;
    case "wait":
      await doWait(unit);
      break;
    case "heal":
      enterHealMode(unit);
      return;
    case "rally":
      await doSkill("rally", null, unit);
      return;
    case "confirm-move": {
      const m = state.pendingMove;
      if (!m) return;
      await doMove(unit, m.toX, m.toY);
      return;
    }
    case "cancel-move":
      state.actionMode = null;
      state.pendingMove = null;
      state.path = null;
      showUnitActionBubble(unit);
      renderBoard(state.game);
      return;
    case "move-more":
      // Re-enter move mode with the unit's remaining MP budget.
      state.actionMode = "move";
      state.reachableTiles = computeReachable(unit);
      state.attackTargets = computeAttackTargets(unit);
      enterMoveMode(unit);
      return;
    case "confirm-attack": {
      const a = state.pendingAttack;
      if (!a) return;
      await doAttack(unit, a.targetId);
      return;
    }
    case "cancel-attack":
      state.actionMode = null;
      state.pendingAttack = null;
      showUnitActionBubble(unit);
      renderBoard(state.game);
      return;
    case "pick-attack":
      if (!targetId) return;
      {
        const st = state.game;
        const target = st.players.flatMap(p => p.units).find(u => u.id === parseInt(targetId));
        if (target) showAttackConfirmBubble(unit, target);
      }
      return;
    case "close":
      hideBubble();
      state.selectedUnit = null;
      state.actionMode = null;
      return;
    case "confirm-heal":
      if (!targetId) return;
      await doSkill("heal", parseInt(targetId), unit);
      return;
    case "cancel-heal":
      state.actionMode = null;
      if (unit) showUnitActionBubble(unit);
      renderBoard(state.game);
      return;
  }
}

function enterMoveMode(unit) {
  state.actionMode = "move";
  state.path = null;
  // Small hint bubble
  const html = `
    <div class="ab-title">选择目的地 — 鼠标悬浮预览路径</div>
    <div class="ab-row">
      <button class="ab-btn cancel" data-ab="cancel-move">❌ 取消</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
  renderBoard(state.game);
}

function enterAttackMode(unit) {
  state.actionMode = "attack";
  // Recompute targets from fresh game state (refreshGame may have run)
  state.attackTargets = computeAttackTargets(unit);
  const targets = state.attackTargets;
  const count = targets?.size ?? 0;
  const html = `
    <div class="ab-title">选择攻击目标 · 可攻击 ${count} 个敌人</div>
    <div class="ab-row">
      <button class="ab-btn cancel" data-ab="cancel-attack">❌ 取消</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
  renderBoard(state.game);
}

function enterHealMode(unit) {
  state.actionMode = "heal";
  const html = `
    <div class="ab-title">💚 选择要治疗的友军</div>
    <div class="ab-row">
      <button class="ab-btn cancel" data-ab="cancel-heal">❌ 取消</button>
    </div>
  `;
  showBubbleAt(unit.x, unit.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit));
  });
  renderBoard(state.game);
}

// ----- Cell hover (for path preview) -----

function computeClientPath(unit, toX, toY, reachable) {
  // BFS-based path from unit position to (toX, toY) using terrain costs.
  // Returns array of {x, y} steps (unit position first, destination last).
  if (!reachable?.has(`${toX},${toY}`)) return null;
  const st = state.game;
  const tileMap = new Map();
  for (const t of st.tiles) tileMap.set(`${t.x},${t.y}`, t);
  const occupied = new Set();
  for (const p of st.players) for (const u of p.units) {
    if (u.id !== unit.id && u.hp > 0) occupied.add(`${u.x},${u.y}`);
  }
  const costs = { plain: 1, forest: 2, mountain: 3, river: 3, castle: 1 };

  // Dijkstra / A* with cost
  const start = { x: unit.x, y: unit.y };
  const goal = { x: toX, y: toY };
  const open = [{ ...start, cost: 0, dist: Math.abs(toX - unit.x) + Math.abs(toY - unit.y) }];
  const cameFrom = new Map();
  const bestCost = new Map([[`${unit.x},${unit.y}`, 0]]);
  // Manhattan-adjacency only (no diagonals): movement is 4-directional.
  const dirs = [[1,0],[-1,0],[0,1],[0,-1]];

  while (open.length) {
    open.sort((a, b) => (a.cost + a.dist) - (b.cost + b.dist));
    const cur = open.shift();
    const ck = `${cur.x},${cur.y}`;
    if (cur.x === goal.x && cur.y === goal.y) {
      // Reconstruct
      const path = [{ x: cur.x, y: cur.y }];
      while (cameFrom.has(`${path[0].x},${path[0].y}`)) {
        const prev = cameFrom.get(`${path[0].x},${path[0].y}`);
        path.unshift({ x: prev.x, y: prev.y });
      }
      return path;
    }
    if (cur.cost > bestCost.get(ck)) continue;
    for (const [dx, dy] of dirs) {
      const nx = cur.x + dx, ny = cur.y + dy;
      if (nx < 0 || nx >= 15 || ny < 0 || ny >= 15) continue;
      const k = `${nx},${ny}`;
      const t = tileMap.get(k);
      if (!t) continue;
      if (t.terrain === "castle" && t.owner_id !== null && t.owner_id !== state.me.player_id) continue;
      if (occupied.has(k)) continue;
      const step = costs[t.terrain] ?? 1;
      const newCost = cur.cost + step;
      if (newCost > unit.mp) continue;
      if ((bestCost.get(k) ?? Infinity) <= newCost) continue;
      bestCost.set(k, newCost);
      cameFrom.set(k, { x: cur.x, y: cur.y });
      open.push({ x: nx, y: ny, cost: newCost, dist: Math.abs(nx - toX) + Math.abs(ny - toY) });
    }
  }
  return null;
}

function updatePathPreview() {
  // Lightweight update: only mutate path-dot / path-end classes in place.
  // Do NOT call renderBoard here — that rebuilds all cells, which destroys
  // the DOM nodes that the browser is currently hovering, fires a fresh
  // mouseenter, and creates an infinite render-loop.
  const board = document.getElementById("board");
  if (!board) return;
  // Clear any prior path dots
  for (const el of board.querySelectorAll(".path-dot, .path-end")) {
    el.classList.remove("path-dot", "path-end");
  }
  if (!state.path || state.path.length < 3) return;
  // path[0] is start, path[last] is end; middle tiles get path-dot, end gets path-end
  for (let i = 1; i < state.path.length - 1; i++) {
    const p = state.path[i];
    const cell = board.querySelector(`.cell[data-x="${p.x}"][data-y="${p.y}"]`);
    if (cell) cell.classList.add("path-dot");
  }
  const end = state.path[state.path.length - 1];
  const endCell = board.querySelector(`.cell[data-x="${end.x}"][data-y="${end.y}"]`);
  if (endCell) endCell.classList.add("path-dot", "path-end");
}

function onCellHover(x, y) {
  if (state.actionMode !== "move" || !state.selectedUnit) return;
  const key = `${x},${y}`;
  if (!state.reachableTiles?.has(key)) {
    if (state.path) {
      state.path = null;
      updatePathPreview();
    }
    return;
  }
  const newPath = computeClientPath(state.selectedUnit, x, y, state.reachableTiles);
  if (newPath) {
    state.path = newPath;
    updatePathPreview();
  } else if (state.path) {
    state.path = null;
    updatePathPreview();
  }
}

// ----- Cell click handler -----

function onCellClick(x, y, st) {
  const occupant = findUnitAt(st, x, y);
  const isMyTurn = st.current_player_id === state.me.player_id;

  // Mode: awaiting move confirmation
  if (state.actionMode === "move" && state.selectedUnit) {
    if (state.reachableTiles?.has(`${x},${y}`) && (!occupant || occupant.unit.id === state.selectedUnit.id)) {
      showMoveConfirmBubble(state.selectedUnit, x, y);
    } else {
      // Click on non-reachable tile → exit move mode, go back to idle
      state.actionMode = null;
      state.path = null;
      state.reachableTiles = null;
      state.attackTargets = null;
      state.selectedUnit = null;
      hideBubble();
      renderBoard(state.game);
      renderUnitInfo(state.game);
    }
    return;
  }

  // Mode: awaiting attack target
  if (state.actionMode === "attack" && state.selectedUnit) {
    if (state.attackTargets?.has(`${x},${y}`) && occupant) {
      showAttackConfirmBubble(state.selectedUnit, occupant.unit);
    } else {
      toast("该目标无法攻击");
    }
    return;
  }

  // Mode: awaiting heal target
  if (state.actionMode === "heal" && state.selectedUnit) {
    if (occupant && occupant.player.id === state.me.player_id && occupant.unit.id !== state.selectedUnit.id) {
      // confirm via bubble inline
      const html = `
        <div class="ab-title">💚 治疗 ${escapeHtml(occupant.unit.name)}</div>
        <div class="ab-row">
          <button class="ab-btn heal" data-ab="confirm-heal" data-target="${occupant.unit.id}">✅ 确认</button>
          <button class="ab-btn cancel" data-ab="cancel-heal">❌ 取消</button>
        </div>
      `;
      showBubbleAt(occupant.unit.x, occupant.unit.y, html, { compact: true });
      document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
        btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, state.selectedUnit, btn.dataset.target));
      });
    } else {
      toast("请选择相邻的己方单位");
    }
    return;
  }

  // Default: click on a unit opens a bubble (action or inspect)
  if (occupant) {
    if (occupant.player.id === state.me.player_id && isMyTurn) {
      if (occupant.unit.has_acted) {
        // Own unit that already acted this turn -> show read-only status bubble
        showActedBubble(occupant.unit, occupant.player);
      } else {
        showUnitActionBubble(occupant.unit);
      }
    } else {
      showInspectBubble(occupant.unit, occupant.player);
    }
    renderBoard(st);
    renderUnitInfo(st);
    return;
  }

  // Click on empty tile with no mode: just deselect / hide bubble
  hideBubble();
  state.selectedUnit = null;
  state.actionMode = null;
  state.pendingMove = null;
  state.pendingAttack = null;
  renderBoard(st);
  renderUnitInfo(st);
}

// Side-panel "view status" card (passive display, not the main interaction)
function renderUnitInfo(st) {
  const info = document.getElementById("unit-info");
  const u = state.selectedUnit;
  if (!u) {
    info.innerHTML = `<p class="muted">点击单位查看详情</p>`;
    return;
  }
  const player = st.players.find(p => p.id === u.player_id);
  info.innerHTML = renderUnitHtml(u, player || { user_name: "?" });
}

// ----- API call helpers -----

// Clear transient visual highlights that were meaningful only for the
// action that just completed. Without this, the previous move-range,
// attack-range, and hover-path overlays stay painted on the board
// because renderBoard re-reads these state vars on every refresh.
function clearVisualState() {
  state.path = null;
  state.reachableTiles = null;
  state.attackTargets = null;
  state.pendingMove = null;
  state.pendingAttack = null;
}

async function doMove(unit, toX, toY) {
  state.actionMode = null;
  clearVisualState();
  try {
    await api("POST", `/games/${state.me.game_id}/move`, {
      player_id: state.me.player_id,
      unit_id: unit.id,
      to_x: toX, to_y: toY,
    });
    toast("移动成功");
    await refreshGame();
    // After move, the unit is at the new position. Show post-move bubble.
    const st = state.game;
    const moved = st.players.find(p => p.id === state.me.player_id)?.units?.find(u2 => u2.id === unit.id);
    if (moved && !moved.has_acted) {
      // Highlight current attack range
      renderBoard(st);
      showPostMoveBubble(moved);
    } else {
      hideBubble();
      state.selectedUnit = null;
    }
  } catch (e) {
    toast("移动失败：" + e.message);
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    clearVisualState();
  }
}

async function doAttack(attacker, targetId) {
  state.actionMode = null;
  clearVisualState();
  try {
    const r = await api("POST", `/games/${state.me.game_id}/attack`, {
      player_id: state.me.player_id,
      attacker_id: attacker.id,
      target_id: targetId,
    });
    const totalDmg = r.hits.reduce((s, h) => s + h.damage, 0);
    const crit = r.hits.some(h => h.is_crit);
    const kill = r.hits.some(h => h.is_kill);
    const moraleGain = kill ? " ⭐士气+1" : "";
    const counterMsg = r.counter_damage > 0
      ? ` · 反击 ${r.counter_damage}（你剩 ${r.attacker_hp_after}HP）`
      : "";
    toast(`造成 ${totalDmg} 伤害${crit ? "（暴击！）" : ""}${moraleGain}${counterMsg}`);
    await refreshGame();
    // After attack: unit has acted. If class can move after AND MP > 0,
    // offer to keep moving; otherwise close.
    const st = state.game;
    const moved = st.players.find(p => p.id === state.me.player_id)?.units?.find(u => u.id === attacker.id);
    if (moved && CAN_MOVE_AFTER[moved.unit_type] && (moved.mp ?? 0) > 0) {
      renderBoard(st);
      showPostAttackBubble(moved);
    } else {
      hideBubble();
      state.selectedUnit = null;
    }
  } catch (e) {
    toast("攻击失败：" + e.message);
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    clearVisualState();
  }
}

async function doSkill(skill, targetId, unit) {
  state.actionMode = null;
  clearVisualState();
  try {
    await api("POST", `/games/${state.me.game_id}/skill`, {
      player_id: state.me.player_id,
      unit_id: unit?.id || state.selectedUnit?.id,
      skill,
      target_id: targetId,
    });
    toast(skill === "heal" ? "治疗成功" : skill === "rally" ? "集结成功" : "技能释放成功");
    await refreshGame();
    hideBubble();
    state.selectedUnit = null;
  } catch (e) {
    toast("技能失败：" + e.message);
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    clearVisualState();
  }
}

async function doWait(unit) {
  state.actionMode = null;
  clearVisualState();
  try {
    await api("POST", `/games/${state.me.game_id}/wait`, {
      player_id: state.me.player_id,
      unit_id: unit?.id || state.selectedUnit?.id,
    });
    await refreshGame();
    hideBubble();
    state.selectedUnit = null;
  } catch (e) {
    toast("待命失败：" + e.message);
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    clearVisualState();
  }
}

async function endTurn() {
  clearVisualState();
  try {
    const r = await api("POST", `/games/${state.me.game_id}/end-turn`, {
      player_id: state.me.player_id,
    });
    toast(r.description);
    state.selectedUnit = null;
    state.actionMode = null;
    await refreshGame();
  } catch (e) {
    toast("结束回合失败：" + e.message);
  }
}

function renderPlayersList(st) {
  const el = document.getElementById("players-list");
  el.innerHTML = "";
  for (const p of st.players) {
    const div = document.createElement("div");
    div.className = "player-card" + (p.id === st.current_player_id ? " active" : "") + (p.is_alive ? "" : " dead") + (p.is_ai ? " ai" : "");
    const aliveUnits = p.units.filter(u => u.hp > 0).length;
    let badge = "";
    if (p.is_ai) badge = `<span class="ai-badge">AI</span>`;
    div.innerHTML = `
      <div class="swatch" style="background: ${playerColorCss(p.color)}"></div>
      <div>${escapeHtml(p.user_name)}${p.is_alive ? "" : " (淘汰)"} · ${aliveUnits}/${p.units.length}${badge}</div>
    `;
    el.appendChild(div);
  }
}

function renderActionLog(st) {
  const el = document.getElementById("action-log");
  const chatEl = document.getElementById("chat-float");
  el.innerHTML = "";
  if (chatEl) chatEl.innerHTML = "";
  const playerMap = new Map();
  for (const p of st.players) playerMap.set(p.id, p);
  const moodEmoji = { joy: "😄", anger: "😠", frustrated: "😤", smug: "😏",
                      disappointed: "😞", relieved: "😅", neutral: "💬" };
  const colorMap = { red: "#e74c3c", blue: "#3498db", green: "#27ae60", yellow: "#f1c40f" };

  for (const log of st.logs.slice(0, 50)) {
    if (log.action_type === "ai_commentary" || log.action_type === "ai_turn") {
      // Route AI speech to the chat box
      if (!chatEl) continue;
      const m = log.description.match(/^\[(\w+)\/(\w+)\]\s*(.*)/);
      if (!m) continue;
      const emoji = moodEmoji[m[2]] || "💬";
      const text = m[3];
      const player = playerMap.get(log.player_id);
      const avatarBg = (player?.color) ? (colorMap[player.color] || "#888") : "#888";
      const name = player?.user_name || "AI";
      const div = document.createElement("div");
      div.className = "chat-msg";
      div.innerHTML = `<span class="chat-avatar" style="background:${avatarBg}">${emoji}</span>`
        + `<span class="chat-name">${escapeHtml(name)}</span>`
        + `<span class="chat-text">${escapeHtml(text)}</span>`;
      chatEl.appendChild(div);
    } else {
      const div = document.createElement("div");
      div.className = "entry " + log.action_type;
      div.textContent = `T${log.turn_number} · ${log.description}`;
      el.appendChild(div);
    }
  }
}

// ----- Reference panel -----

// Unit class metadata — fetched from /units endpoint at startup.
let UNIT_CLASSES = {};  // type_id → { glyph, display_cn, can_move_after_action, attack_range, ... }
let CAN_MOVE_AFTER = {};  // built from UNIT_CLASSES

const TERRAIN_REF = [
  { id: "plain",    name: "平地",   color: "#cfe5b6", move: 1, def: 0, note: "通用地形，无加成" },
  { id: "forest",   name: "森林",   color: "#4f8a47", move: 2, def: 2, note: "防御+2，远程视野受阻" },
  { id: "mountain", name: "山地",   color: "#8c8c8c", move: 3, def: 3, note: "防御+3，移动慢" },
  { id: "river",    name: "河流",   color: "#5fb0e8", move: 3, def: 0, note: "移动慢，但无防御" },
  { id: "castle",   name: "城堡",   color: "#f0c75e", move: 1, def: 5, note: "防御+5，需占 1 回合" },
];

let SKILL_REF = [];  // fetched from /skills endpoint

function renderRefContent() {
  const el = document.getElementById("ref-content");
  if (state.refTab === "terrain") {
    el.innerHTML = TERRAIN_REF.map(t => `
      <div class="ref-terrain">
        <div class="swatch" style="background:${t.color}"></div>
        <div class="info">
          <div class="name">${t.name}</div>
          <div class="stats">移动消耗 ${t.move} · 防御 ${t.def >= 0 ? "+" : ""}${t.def}</div>
          <div class="stats" style="margin-top:2px">${t.note}</div>
        </div>
      </div>
    `).join("");
  } else if (state.refTab === "units") {
    const colors = { swordsman: "var(--p-blue)", archer: "var(--p-green)", knight: "var(--p-red)", healer: "var(--p-yellow)" };
    el.innerHTML = Object.values(UNIT_CLASSES).map(u => {
      const rangeText = u.attack_range === 0 ? "无" : `射程 ${u.attack_range}`;
      const skillNames = (u.default_skills || []).map(skillName).join("、");
      return `
        <div class="ref-unit">
          <div class="glyph" style="background:${colors[u.type_id] || "#888"}">${u.glyph}</div>
          <div class="info">
            <div class="name">${u.display_cn} <span class="muted small">(${rangeText})</span></div>
            <div class="stats">HP ${u.base_hp} · ATK ${u.base_atk} · DEF ${u.base_def} · MOV ${u.base_mov}</div>
            ${skillNames ? `<div class="skills">技能：${skillNames}</div>` : ""}
          </div>
        </div>`;
    }).join("");
  } else if (state.refTab === "skills") {
    el.innerHTML = SKILL_REF.map(s => `
      <div class="ref-skill">
        <div class="name">${s.name}</div>
        <div class="desc">${s.desc}</div>
      </div>
    `).join("");
  }
}

function toggleRefPanel() {
  state.refPanelOpen = !state.refPanelOpen;
  document.getElementById("ref-panel").hidden = !state.refPanelOpen;
  if (state.refPanelOpen) renderRefContent();
}

// ----- Display helpers -----
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[c]);
}

function playerColorCss(c) {
  return ({
    red: "var(--p-red)", blue: "var(--p-blue)",
    green: "var(--p-green)", yellow: "var(--p-yellow)",
  })[c] || "#888";
}

function unitGlyph(type) {
  return (UNIT_CLASSES[type] && UNIT_CLASSES[type].glyph) || "?";
}
function unitTypeName(type) {
  return (UNIT_CLASSES[type] && UNIT_CLASSES[type].display_cn) || type;
}
function unitCanMoveAfter(type) {
  return (UNIT_CLASSES[type] && UNIT_CLASSES[type].can_move_after_action) || false;
}
let SKILL_MAP = {};
function skillName(s) {
  return SKILL_MAP[s] || s;
}

// ============================================================
// Dialog box (S0.1) — 剧情/对话系统
// ============================================================
//
// API:
//   dialog.show(scene) -> Promise       // 单个场景
//   dialog.play(scenes) -> Promise      // 顺序播放多个场景
//   dialog.say(speaker, text, opts?)    // 单行对话
//   dialog.close()                      // 强制关闭
//
// Scene 类型:
//   { type: 'dialogue', speaker, speaker_color?, text }
//   { type: 'narration', text }
//   { type: 'choice', question, choices: [{text, value?}] }
//         -> resolves to choices[i].value ?? choices[i].text
//   { type: 'wait', ms }                // 等待 N 毫秒后继续
//
// 全局交互：
//   - 点击对话框 / 叙述区 / 按 Space / Enter → 推进（typewriter 中则立即完成）
//   - 按 Esc → 强制关闭（resolve 当前 promise）
//   - 选项按钮点击 → 选中并 resolve
// ============================================================

// ── Character asset registry ──
// Maps speaker names to their visual assets.
//   crest:    small circular icon shown in the dialog box avatar slot
//   portrait: full character portrait shown in the standalone portrait panel
// All portraits should be uniform dimensions for consistent display.
const CHARACTER_ASSETS = {
  "云": {
    crest: "/ui/assets/crest_yun.png",
    portrait: "/ui/assets/portrait_yun.png",
  },
};

const Dialog = {
  // 运行状态
  active: false,         // 是否正在播放
  _resolve: null,        // 当前场景的 resolver
  _currentScene: null,   // 当前场景对象
  _typewriterTimer: null,// 打字机 interval
  _typewriterDone: false,// 当前文本是否打完
  _typedText: "",        // 当前已打字的文本（用于取消）

  // ---- 可调参数 ----
  CHARS_PER_SEC: 40,          // 打字速度（默认 40 字/秒，~25ms/字）
  MAX_OPTIONS: 4,             // 最多 4 个选项
  NARRATION_CHARS_PER_SEC: 25,// 叙述模式稍慢（22ms/字），便于阅读

  // ====================== 公共 API ======================

  /**
   * 显示并播放一个场景。返回 Promise，在场景"完成"时 resolve。
   *   dialogue/narration  → resolve undefined
   *   choice             → resolve 选中项的 value（或 text）
   *   wait               → resolve undefined（等待后）
   *   battle_ref         → resolve scene 本身（含 battle_id 字段；主线引擎拿到后启动战斗）
   */
  show(scene) {
    if (!scene || typeof scene !== "object") {
      return Promise.reject(new Error("Dialog.show: scene is required"));
    }
    if (this.active) {
      // 防止递归：若已有 dialog 在播，把当前 promise 链挂到它的下一个位置
      return this._queue(scene);
    }
    return this._run(scene);
  },

  /** 顺序播放多个场景。任一 reject 会立即终止链。 */
  async play(scenes) {
    if (!Array.isArray(scenes)) throw new Error("Dialog.play: scenes must be array");
    for (const sc of scenes) {
      await this.show(sc);
    }
  },

  /** 快速显示一行对话（等价于一个 dialogue 场景）。 */
  say(speaker, text, opts = {}) {
    return this.show({
      type: "dialogue",
      speaker,
      speaker_color: opts.color,
      text,
    });
  },

  /** 强制关闭（resolve 当前 pending 场景，丢弃后续队列）。 */
  close() {
    if (!this.active) return;
    const r = this._resolve;
    this._cleanup();
    if (r) r(undefined);
  },

  /**
   * 内置演示脚本：完整跑一遍 dialogue / narration / choice / wait 四种场景。
   * 用于在没有 S0.2 剧情系统时手动验证对话框功能。
   */
  async demo() {
    await this.play([
      { type: "narration", text: "很久以前，这片大陆被黑暗笼罩……" },
      // "云" 有肖像立绘，会自动显示在对话框左侧
      { type: "dialogue", speaker: "云", speaker_color: "#ffb84d",
        text: "你好，旅者。我是云，这片大陆的守护者。\n\n你的到来让命运之轮再次转动。前方的道路充满艰险，但我会与你同行。" },
      { type: "dialogue", speaker: "云", speaker_color: "#ffb84d",
        text: "看那里——远方的山脉之后，便是黑暗军团的要塞。我们必须集结力量，在下次满月之前发起进攻。" },
      // "红" 没有注册肖像，显示 🎭 占位符
      { type: "dialogue", speaker: "红", speaker_color: "#e85a6a",
        text: "今天，我们将吹响反击的号角。战士们已经准备好了！" },
      { type: "choice",
        question: "你选择相信谁？",
        choices: [
          { text: "相信云的判断", value: "yun" },
          { text: "跟随红的勇气", value: "hong" },
        ],
      },
      { type: "dialogue", speaker: "云", speaker_color: "#ffb84d",
        text: "明智的选择。让我们开始准备吧。" },
      { type: "narration", text: "（云的身影在月光下格外坚定。你感到一股温暖的力量涌入体内。）" },
      { type: "dialogue", speaker: "系统",
        text: "🎉 立绘集成演示完成！\n「云」的肖像现已接入对话框系统。\n\n更多角色的立绘可以添加到 CHARACTER_PORTRAITS 中。" },
    ]);
    toast("🎭 立绘演示结束");
  },

  // ====================== 内部 ======================

  _queue(scene) {
    // 已激活时，新场景排队等当前场景结束后播放
    return new Promise((resolve) => {
      this._pendingQueue = this._pendingQueue || [];
      this._pendingQueue.push({ scene, resolve });
    });
  },

  _drainQueue() {
    const next = (this._pendingQueue || []).shift();
    if (!next) return;
    // 在 microtask 中启动下一个，避免 resolve 后同步递归
    Promise.resolve().then(() => {
      this._run(next.scene).then(next.resolve);
    });
  },

  _run(scene) {
    return new Promise((resolve) => {
      this.active = true;
      this._currentScene = scene;
      this._resolve = resolve;
      this._typewriterDone = false;

      const t = scene.type;
      if (t === "dialogue") this._renderDialogue(scene);
      else if (t === "narration") this._renderNarration(scene);
      else if (t === "choice") this._renderChoice(scene);
      else if (t === "wait") this._renderWait(scene);
      else if (t === "battle_ref") {
        // 主线剧情里的"进入战斗"标记：不渲染 UI，立即 resolve 场景本身，
        // 让调用方 (MainlineView) 通过 await Dialog.show(scene) 拿到 battle_id。
        // 等后端真实接入后，这里可以替换成调用 window.mainlineEngine.startBattle(scene.battle_id)。
        this._cleanup();
        resolve(scene);
      }
      else {
        // 未知类型：直接通过
        this._cleanup();
        resolve(undefined);
      }
    });
  },

  // ---------- DOM 渲染 ----------

  _el() {
    return {
      box: document.getElementById("dialog-box"),
      narration: document.getElementById("dialog-narration"),
    };
  },

  _renderDialogue(scene) {
    const { box, narration } = this._el();
    narration.hidden = true;

    const speakerEl = box.querySelector(".dialog-speaker");
    const textEl = box.querySelector(".dialog-text");
    const choicesEl = box.querySelector(".dialog-choices");
    const avatarEl = box.querySelector(".dialog-avatar");
    const placeholder = avatarEl && avatarEl.querySelector(".dialog-avatar-placeholder");

    speakerEl.textContent = scene.speaker || "";
    speakerEl.classList.toggle("is-narration", !scene.speaker);
    if (scene.speaker_color) {
      speakerEl.style.color = scene.speaker_color;
    } else {
      speakerEl.style.color = "";
    }

    // ── Dialog crest (small circular icon in the dialog box) ──
    const oldCrest = avatarEl && avatarEl.querySelector("img");
    if (oldCrest) oldCrest.remove();

    const assets = scene.speaker ? CHARACTER_ASSETS[scene.speaker] : null;
    if (assets && assets.crest && avatarEl) {
      if (placeholder) placeholder.hidden = true;
      const img = document.createElement("img");
      img.src = assets.crest;
      img.alt = scene.speaker || "";
      img.draggable = false;
      img.onerror = function () {
        this.style.display = "none";
        if (placeholder) placeholder.hidden = false;
      };
      avatarEl.appendChild(img);
    } else {
      if (placeholder) placeholder.hidden = false;
      const stray = avatarEl && avatarEl.querySelector("img");
      if (stray) stray.remove();
    }

    // ── Standalone portrait panel (outside dialog box) ──
    this._setPortraitPanel(scene.speaker, assets ? assets.portrait : null);

    choicesEl.innerHTML = "";
    box.classList.remove("is-text-done");
    box.classList.add("is-typing");
    box.hidden = false;
    this._startTypewriter(textEl, scene.text || "", false);
  },

  /** Show/hide the standalone portrait panel with the given image. */
  _setPortraitPanel(speaker, portraitUrl) {
    const panel = document.getElementById("portrait-panel");
    const img = document.getElementById("portrait-image");
    const tag = document.getElementById("portrait-name-tag");
    if (!panel || !img || !tag) return;

    if (portraitUrl && speaker) {
      img.src = portraitUrl;
      img.alt = speaker;
      tag.textContent = speaker;
      panel.hidden = false;
      // Ensure reflow so the transition fires
      void panel.offsetWidth;
      panel.style.opacity = "1";
    } else {
      panel.style.opacity = "0";
      // Keep hidden after transition
      setTimeout(() => {
        if (panel.style.opacity === "0") panel.hidden = true;
      }, 300);
    }
  },

  _renderNarration(scene) {
    const { box, narration } = this._el();
    box.hidden = true;

    const textEl = narration.querySelector(".dialog-narration-text");
    narration.classList.remove("is-text-done");
    narration.hidden = false;
    this._startTypewriter(textEl, scene.text || "", true);
  },

  _renderChoice(scene) {
    const { box, narration } = this._el();
    narration.hidden = true;

    const speakerEl = box.querySelector(".dialog-speaker");
    const textEl = box.querySelector(".dialog-text");
    const choicesEl = box.querySelector(".dialog-choices");

    speakerEl.textContent = "";
    speakerEl.classList.add("is-narration");
    speakerEl.style.color = "";
    textEl.textContent = scene.question || "请选择：";
    choicesEl.innerHTML = "";

    const choices = (scene.choices || []).slice(0, this.MAX_OPTIONS);
    choices.forEach((c, i) => {
      const btn = document.createElement("button");
      btn.className = "dialog-choice";
      btn.type = "button";
      btn.textContent = `${i + 1}. ${c.text}`;
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._finishChoice(c);
      });
      choicesEl.appendChild(btn);
    });

    // 选项模式：关闭打字机，立刻显示题目
    this._stopTypewriter();
    box.classList.add("is-text-done");
    box.classList.remove("is-typing");
    box.hidden = false;
  },

  _renderWait(scene) {
    // 等待场景不显示任何 UI，仅延时后 resolve
    const ms = Math.max(0, Number(scene.ms) || 0);
    setTimeout(() => {
      if (this._resolve && this._currentScene === scene) {
        const r = this._resolve;
        this._cleanup();
        r(undefined);
      }
    }, ms);
  },

  _finishChoice(c) {
    const value = (c && c.value !== undefined) ? c.value : (c ? c.text : undefined);
    const r = this._resolve;
    this._cleanup();
    if (r) r(value);
  },

  // ---------- 打字机 ----------

  _startTypewriter(targetEl, text, isNarration) {
    this._stopTypewriter();
    this._typedText = text;

    const cps = isNarration ? this.NARRATION_CHARS_PER_SEC : this.CHARS_PER_SEC;
    const intervalMs = Math.max(8, Math.round(1000 / cps));

    targetEl.innerHTML = "";
    const caret = document.createElement("span");
    caret.className = "dialog-caret";
    targetEl.appendChild(caret);

    let i = 0;
    const tick = () => {
      if (!this.active) return;
      if (i >= text.length) {
        this._finishTypewriter();
        return;
      }
      const ch = text[i++];
      caret.insertAdjacentText("beforebegin", ch);
    };
    this._typewriterTimer = setInterval(tick, intervalMs);
  },

  _stopTypewriter() {
    if (this._typewriterTimer) {
      clearInterval(this._typewriterTimer);
      this._typewriterTimer = null;
    }
  },

  /** 立即完成当前打字机（点击/Enter 触发）。 */
  _finishTypewriter() {
    this._stopTypewriter();
    const { box, narration } = this._el();
    // 把当前场景的整段文本写回去（覆盖未打完的部分）
    const textEl = box.querySelector(".dialog-text");
    const narEl = narration.querySelector(".dialog-narration-text");
    const target = narration.hidden === false ? narEl : textEl;
    if (target && this._currentScene) {
      target.textContent = this._currentScene.text || "";
    }
    box.classList.add("is-text-done");
    box.classList.remove("is-typing");
    narration.classList.add("is-text-done");
    this._typewriterDone = true;
  },

  /** 推进到下一个状态（点击/Enter 在打字完成时触发）。 */
  _advance() {
    if (!this.active) return;
    const scene = this._currentScene;
    if (!scene) return;
    if (scene.type === "dialogue" || scene.type === "narration") {
      const r = this._resolve;
      this._cleanup();
      if (r) r(undefined);
    }
    // choice/wait 不响应点击推进
  },

  // ---------- 清理 ----------

  _cleanup() {
    this._stopTypewriter();
    const { box, narration } = this._el();
    box.hidden = true;
    narration.hidden = true;
    box.classList.remove("is-text-done", "is-typing");
    narration.classList.remove("is-text-done");
    box.querySelector(".dialog-choices").innerHTML = "";
    box.querySelector(".dialog-text").innerHTML = "";
    narration.querySelector(".dialog-narration-text").innerHTML = "";
    box.querySelector(".dialog-speaker").textContent = "";
    // Hide the standalone portrait panel
    this._setPortraitPanel(null, null);
    this.active = false;
    this._currentScene = null;
    this._resolve = null;
    this._typewriterDone = false;
    this._drainQueue();
  },

  // ---------- 全局事件绑定 ----------

  _bindGlobalEvents() {
    if (this._bound) return;
    this._bound = true;

    // 点击对话框或叙述区
    const { box, narration } = this._el();
    box.addEventListener("click", (e) => {
      // 选项点击已在 _renderChoice 中 stopPropagation
      if (!this.active) return;
      if (e.target.closest(".dialog-choice")) return;
      if (this._typewriterDone) this._advance();
      else this._finishTypewriter();
    });
    narration.addEventListener("click", () => {
      if (!this.active) return;
      if (this._typewriterDone) this._advance();
      else this._finishTypewriter();
    });

    // 全局键盘：Space / Enter 推进；Esc 关闭
    document.addEventListener("keydown", (e) => {
      if (!this.active) return;
      // 如果焦点在 input/textarea/select，按键交给它们
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape") {
        e.preventDefault();
        this.close();
      } else if (e.key === " " || e.key === "Enter") {
        // choice 模式允许 Enter 选中第 1 个选项（但本期暂不实现数字键）
        if (this._currentScene && this._currentScene.type === "choice") return;
        e.preventDefault();
        if (this._typewriterDone) this._advance();
        else this._finishTypewriter();
      }
    });
  },
};

// 暴露给浏览器控制台与游戏内调用
window.dialog = Dialog;
Dialog._bindGlobalEvents();

// ============================================================
// MainlineView — 主线模式前端模块
//
// 职责：仅做"展示 + 编排"：
//   - 列章节卡片（GET /mainlines）
//   - 看详情（GET /mainlines/{id}）
//   - 开始主线（POST /mainlines/{id}/start）
//   - 拉对话剧本 JSON（GET /mainlines/dialogue?path=...）
//   - 战斗胜利后推进（POST /mainlines/{id}/advance）
//   - 放弃主线（POST /mainlines/{id}/abandon）
//
// 设计原则：所有战斗/AI/回合逻辑一律不重写，
// 直接把 state.me/game_id 喂给现有 enterGame() / refreshGame()。
// ============================================================

const MainlineView = {
  // 当前在 mainline-play 视图里显示的元数据
  _current: null,        // { id, title, total_battles, battle_index }

  // session 级缓存：已确认存在的 user_name。
  // 避免每次点"开始"都 POST /progression/profiles（已被忽略但 server log 噪音）。
  _profileEnsuredFor: null,

  // 并发锁：当前正在跑的 ensureProfile promise。
  // 防止用户在 quick-clicking / 轮询触发时并发跑出多份 GET/POST。
  _profileEnsuringPromise: null,

  // ---------- 网络封装（薄壳，所有端点见 docs/架构.md §八） ----------

  async fetchList() {
    console.debug("[mainline] fetchList");
    const r = await api("GET", "/mainlines");
    console.info(`[mainline] fetchList OK: count=${(r || []).length}`);
    return r;
  },

  async fetchDetail(id) {
    console.debug(`[mainline] fetchDetail: id=${id}`);
    const r = await api("GET", `/mainlines/${encodeURIComponent(id)}`);
    console.info(`[mainline] fetchDetail OK: id=${id} battles=${r && r.battle_count}`);
    return r;
  },

  async fetchDialogue(path) {
    // 服务端 GET /mainlines/dialogue?path=<相对路径>
    // 安全：服务端会校验 path 不能逃出 game/ 根
    console.debug(`[mainline] fetchDialogue: path=${path}`);
    const r = await api("GET", `/mainlines/dialogue?path=${encodeURIComponent(path)}`);
    // r 可能是 {"scenes": [...]} 或直接的 scenes 数组
    let scenes = [];
    if (Array.isArray(r)) scenes = r;
    else if (r && Array.isArray(r.scenes)) scenes = r.scenes;
    console.info(`[mainline] fetchDialogue OK: path=${path} scenes=${scenes.length}`);
    return scenes;
  },

  // ---------- profile 防御 ----------

  /**
   * 确保后端存在一个名为当前 user 的 PlayerProfile。
   * 任何 /mainlines/* 端点都依赖该 row；缺失时后端会 404。
   * 失败原因（昵称为空、POST 报错非 409）会通过 toast 告知用户，
   * 调用方应直接 return，不继续走业务。
   *
   * 并发：已有 ensureProfile 在跑就直接 await 之，避免 N 个 click 触发
   * N 个并行 GET/POST 风暴（这是玩家-828 死循环日志的根因之一）。
   *
   * 返回：trim 后的 userName（保证非空）；或 null（已 toast）。
   */
  async ensureProfile() {
    // 0. 并发锁：已有 ensureProfile 在跑 → 直接等它，不再开新的。
    //    finally 块会在结束后把 _profileEnsuringPromise 置 null。
    if (this._profileEnsuringPromise) {
      console.debug("[mainline] ensureProfile: awaiting in-flight call");
      return this._profileEnsuringPromise;
    }

    this._profileEnsuringPromise = (async () => {
      try {
        // 1. 从 settings 拿 user_name（trim 后）
        let userName = (state.settings.playerName || "").trim();

        // 2. 空名 → 弹 prompt 让用户输入（不可空）
        if (!userName) {
          userName = (prompt("请输入你的玩家昵称（1-32 字符）：", "玩家") || "").trim();
          if (!userName) {
            toast("昵称不能为空", 2000);
            return null;
          }
          // 写回 settings 并持久化
          state.settings.playerName = userName;
          try { saveSettings(state.settings); } catch (e) {
            console.warn("[mainline] saveSettings failed:", e);
          }
        }

        // 3. Session 缓存命中：直接返回，不再发任何请求（避免 server log 噪音）
        if (this._profileEnsuredFor === userName) {
          console.debug(`[mainline] profile ensured (cached): user=${userName}`);
          if (state.me) state.me.user_name = userName;
          return userName;
        }

        // 4. GET 探活：profile 已存在就直接走业务，不发 POST
        try {
          await api("GET", `/profile/${encodeURIComponent(userName)}`);
          console.debug(`[mainline] profile exists (GET ok): user=${userName}`);
        } catch (getErr) {
          // 404 = 不存在 → POST 创建
          if (getErr.status === 404) {
            // 用户可见反馈：让用户知道正在做什么（避免狂点）
            toast(`正在创建玩家档案「${userName}」…`, 1500);
            try {
              await api("POST", "/progression/profiles", { user_name: userName });
              console.info(`[mainline] profile created: user=${userName}`);
            } catch (postErr) {
              // POST 也 409 说明别的 session 刚创建好 → 当作已存在处理
              if (postErr.status === 409) {
                console.debug(`[mainline] profile created concurrently: user=${userName}`);
              } else {
                console.error(`[mainline] profile create failed: user=${userName}`, postErr);
                toast(`创建玩家档案失败：${postErr.message}`, 3000);
                return null;
              }
            }
          } else {
            // 其他 GET 错误（500、网络断）→ 失败
            console.error(`[mainline] profile lookup failed: user=${userName}`, getErr);
            toast(`查询玩家档案失败：${getErr.message}`, 3000);
            return null;
          }
        }

        // 5. 标记 session 缓存 + 同步 state.me.user_name
        this._profileEnsuredFor = userName;
        if (state.me) state.me.user_name = userName;
        return userName;
      } finally {
        // 释放锁：无论成功 / 失败 / throw，都让下一次 ensureProfile
        // 能正常重试（避免锁死）。对调用方语义不变：await 返回值。
        this._profileEnsuringPromise = null;
      }
    })();

    return this._profileEnsuringPromise;
  },

  /**
   * 清掉 session 缓存。给"切换昵称"场景用：下次 ensureProfile 会重新 GET 探活。
   * abandon 不需要调这个 —— profile 还在，缓存有效。
   */
  resetProfileCache() {
    this._profileEnsuredFor = null;
    console.debug("[mainline] profile cache reset");
  },

  async start(id, userName, opts = {}) {
    console.debug(`[mainline] start entry: id=${id} user_name=${userName} opts=${JSON.stringify(opts)}`);
    // 后端契约：POST /mainlines/{id}/start body = {user_name, skip_intro?}
    const callStart = () => api("POST", `/mainlines/${encodeURIComponent(id)}/start`, {
      user_name: userName,
      skip_intro: !!opts.skipIntro,
    });
    try {
      const r = await callStart();
      console.info(
        `[mainline] start OK: id=${id} game_id=${r && r.game_id} ` +
        `player_id=${r && r.player_id} state=${r && r.state}`
      );
      return r;
    } catch (e) {
      // 409 "already active" → 自动重置并重试一次（带 _retried 防无限递归）。
      // 用户点"开始"就是想玩，撞上旧的 active mainline 时最直觉的体验就是
      // 自动 abandon 旧进度并立刻重开 — 而不是让用户再点一次 abandon 再点 start。
      if (e.status === 409 && !opts._retried) {
        const detail = e && e.body && e.body.detail;
        const isActiveMainline = detail && detail.error === "mainline_already_active";
        if (isActiveMainline) {
          console.warn(
            `[mainline] start 409 active, auto-reset: id=${id} user=${userName} ` +
            `active_mainline=${detail.active_mainline}`
          );
          toast("检测到进行中的主线，正在重置并重新开始…", 1500);
          try {
            await api("POST", `/mainlines/${encodeURIComponent(id)}/abandon`, {
              user_name: userName,
            });
            console.info(`[mainline] auto-abandon OK, retrying start: id=${id} user=${userName}`);
          } catch (abandonErr) {
            console.error(
              `[mainline] auto-abandon failed: id=${id} user=${userName}`,
              abandonErr
            );
            toast("放弃旧进度失败：" + (abandonErr.message || ""), 3000);
            throw abandonErr;
          }
          // 重试一次（_retried=true 防止再 409 时再次进入 auto-retry 流程）
          const r2 = await this.start(id, userName, { ...opts, _retried: true });
          return r2;
        }
      }
      console.error(
        `[mainline] start failed: id=${id} err=${e && e.message} status=${e && e.status}`,
        e && e.body
      );
      throw e;
    }
  },

  async advance(id, userName, gameId) {
    console.debug(`[mainline] advance entry: id=${id} user_name=${userName} game_id=${gameId}`);
    try {
      const r = await api("POST", `/mainlines/${encodeURIComponent(id)}/advance`, {
        user_name: userName,
        game_id: gameId,
      });
      console.info(`[mainline] advance OK: id=${id} state=${r && r.state} battle_index=${r && r.battle_index}`);
      return r;
    } catch (e) {
      console.error(`[mainline] advance failed: id=${id} err=${e && e.message} status=${e && e.status}`);
      throw e;
    }
  },

  async startNextBattle(id, userName) {
    console.debug(`[mainline] startNextBattle entry: id=${id} user_name=${userName}`);
    try {
      const r = await api("POST", `/mainlines/${encodeURIComponent(id)}/next-battle`, {
        user_name: userName,
      });
      console.info(`[mainline] startNextBattle OK: id=${id} game_id=${r && r.game_id} battle_index=${r && r.battle_index}`);
      return r;
    } catch (e) {
      console.error(`[mainline] startNextBattle failed: id=${id} err=${e && e.message} status=${e && e.status}`);
      throw e;
    }
  },

  async abandon(id, userName) {
    console.debug(`[mainline] abandon entry: id=${id} user_name=${userName}`);
    try {
      const r = await api("POST", `/mainlines/${encodeURIComponent(id)}/abandon`, {
        user_name: userName,
      });
      console.info(`[mainline] abandon OK: id=${id}`);
      return r;
    } catch (e) {
      console.error(`[mainline] abandon failed: id=${id} err=${e && e.message}`);
      throw e;
    }
  },

  // ---------- 章节列表视图 ----------

  async renderList() {
    const container = document.getElementById("mainline-list");
    container.innerHTML = `<p class="muted">加载中…</p>`;
    try {
      const items = await this.fetchList();
      if (!items || !items.length) {
        container.innerHTML = `<p class="muted">暂无主线章节。</p>`;
        return;
      }
      container.innerHTML = "";
      for (const m of items) {
        const card = document.createElement("div");
        card.className = "mainline-card";
        card.dataset.mainlineId = m.id;
        card.innerHTML = `
          <h3>${escapeHtml(m.title)}</h3>
          <p class="muted">${escapeHtml(m.synopsis || "")}</p>
          <div class="meta">
            <span>战斗数: ${m.battle_count}</span>
            <span>所需职业: ${(m.required_classes || []).join(", ") || "无"}</span>
          </div>
          <button class="btn btn-primary btn-sm" data-action="mainline-card-click" data-mainline-id="${escapeHtml(m.id)}">开始 →</button>
        `;
        container.appendChild(card);
      }
    } catch (e) {
      container.innerHTML = `<p class="error-text">加载失败：${escapeHtml(e.message)}</p>`;
    }
  },

  // ---------- 主线 3 个存档格 ----------
  // 每个用户拥有 3 个独立的主线进度槽位（slot 1/2/3）。
  // 槽位和具体章节解绑 — 同一槽位可以反复开始不同的章节；
  // 槽位被新存档占用时，旧存档会被覆盖（防止同一槽位累积多个 active 存档）。

  MAINLINE_SLOT_COUNT: 3,

  async renderSlots() {
    const container = document.getElementById("mainline-slots");
    if (!container) return;
    container.innerHTML = `<p class="muted">加载中…</p>`;
    let userName = (state.settings && state.settings.playerName) || "";
    // 没设昵称时给个临时占位（不写入 settings）
    const probeName = userName || "__mainline_slot_probe__";
    let profile = null;
    try {
      profile = await api("GET", `/profile/${encodeURIComponent(probeName)}`);
    } catch (_) {
      // 没创建过 profile — 3 个槽位全空
      profile = null;
    }
    // 列出所有 mainline 存档并按 chapter+battle 归到槽位
    let saves = [];
    try {
      const allGames = await api("GET", `/games?user_name=${encodeURIComponent(probeName)}`);
      saves = (allGames || []).filter(g => (g.name || "").startsWith("mainline:"));
    } catch (_) {}
    // 当前用户的 active 主线存档
    const myActiveSaves = profile ? saves.filter(g => g.status === "playing") : [];
    // 简单分配策略：每个 active 存档占一个槽位（按 id 升序），其余为空。
    // 复杂度：3 个存档格 = 最多 3 个 active 存档。
    const sortedActives = myActiveSaves.slice(0, this.MAINLINE_SLOT_COUNT).sort((a, b) => a.id - b.id);
    container.innerHTML = "";
    for (let i = 0; i < this.MAINLINE_SLOT_COUNT; i++) {
      const slot = document.createElement("div");
      const g = sortedActives[i];
      if (g) {
        const slotLabel = `存档 ${i + 1}`;
        const chapterName = (g.name || "").split(":")[1] || g.name;
        slot.className = "save-slot occupied";
        slot.innerHTML = `
          <div class="slot-title">${slotLabel} · 进行中</div>
          <div class="slot-content">
            <div><strong>${escapeHtml(chapterName)}</strong></div>
            <div class="muted small">回合 ${g.turn_number ?? "?"} · #${g.id}</div>
          </div>
          <div class="slot-actions">
            <button class="btn btn-primary btn-sm" data-action="mainline-slot-resume" data-game-id="${g.id}" data-slot-idx="${i}">▶ 从记录开始</button>
            <button class="btn btn-danger btn-sm" data-action="mainline-slot-delete" data-game-id="${g.id}">🗑️</button>
          </div>
        `;
      } else {
        slot.className = "save-slot empty";
        slot.innerHTML = `
          <div class="slot-title">存档 ${i + 1} · 空</div>
          <div class="slot-content">空存档 — 在下方选章节开始</div>
        `;
      }
      container.appendChild(slot);
    }
  },

  // ---------- 入口：点击"开始"后走这个流程 ----------

  async startAndEnter(id, triggerBtn) {
    // 防线 1：先确保后端有 profile，再走 /start。
    // 这样能避免"前端用临时 user_name → 后端 404 → 用户狂点"的死循环。
    //
    // 按钮 loading 状态：用户狂点是死循环的另一根稻草。
    // 拿到按钮引用后立刻 disable + 改文字，避免重复点击。
    // 成功：进入 play 视图，列表 DOM 销毁，按钮自然消失。
    // 失败：try/finally 恢复按钮。
    let restored = false;
    const restoreBtn = () => {
      if (restored) return;
      restored = true;
      if (triggerBtn && triggerBtn.isConnected) {
        triggerBtn.disabled = false;
        triggerBtn.textContent = "开始 →";
      }
    };
    if (triggerBtn && triggerBtn.isConnected) {
      triggerBtn.disabled = true;
      triggerBtn.textContent = "准备中…";
    }

    const userName = await this.ensureProfile();
    if (!userName) {
      console.info(`[mainline] startAndEnter aborted: ensureProfile failed (mainline=${id})`);
      restoreBtn();
      return;
    }
    console.info(`[mainline] USER_ACTION | user=${userName} | action=MAINLINE_START | mainline=${id}`);
    try {
      const r = await this.start(id, userName);
      // 记录到 state（其他模块/refreshGame 据此判断主线模式）
      state.mainline = {
        id,
        title: r.title || id,
        total_battles: r.total_battles,
        battle_index: r.battle_index,
        state: r.state,
      };
      state.mainlineGameId = r.game_id;
      state.mainlinePlayerId = r.player_id;
      state.me.game_id = r.game_id;
      state.me.player_id = r.player_id;
      // userName 在 ensureProfile + _resolveUserName 已保证非空；
      // 不要用 `玩家-${id}` 这种 fallback 把脏数据写进 state.me，
      // 否则后续 advance / next-battle 会带着脏 user_name 反复 404。
      state.me.user_name = userName;
      // 持久化以便刷新恢复
      const sess = loadSession() || {};
      saveSession({
        ...sess,
        mainline_id: id,
        mainline_game_id: r.game_id,
        mainline_player_id: r.player_id,
        game_id: r.game_id,
        player_id: r.player_id,
        user_name: state.me.user_name,
      });
      await this._enterPlayView(r);
      // 成功路径不恢复按钮：list 视图已销毁，按钮 isConnected=false。
      // 但 restoreBtn 内的 isConnected 守卫会跳过，逻辑正确。
    } catch (e) {
      toast("开始主线失败：" + e.message, 3000);
      restoreBtn();
    }
  },

  // ---------- 主线游玩视图：先放 pre 对话，再切战斗 ----------

  async _enterPlayView(startResp) {
    showView("mainline-play");
    this._updateHeader(startResp);

    // 1. 播放 pre_battle 对话（如果有 url）
    if (startResp.pre_battle_dialogue_url) {
      const scenes = await this._playDialogueSafely(
        startResp.pre_battle_dialogue_url,
        startResp.pre_battle_dialogue_key || "intro"
      );
      if (scenes === null) return;  // 用户中途关闭，暂停在 play 视图
    }

    // 2. 进入战斗视图（复用 view-game 全部代码）
    await this._enterBattlePhase(startResp);
  },

  _updateHeader(r) {
    document.getElementById("mainline-title").textContent =
      state.mainline?.title || r.mainline_id || "主线";
    const idx = (r.battle_index ?? 0) + 1;
    const total = r.total_battles ?? "?";
    document.getElementById("mainline-progress").textContent =
      `第 ${idx} / ${total} 场 · 状态: ${r.state}`;
  },

  async _enterBattlePhase(r) {
    // 把 game id 写进 state.me，让 enterGame() 能跑现有 refreshGame 逻辑
    state.me.game_id = r.game_id;
    // 进入棋盘视图（不要清 mainline 标志位，renderGame 据此跳过原生 modal）
    await enterGame();
  },

  // 拉对话并播放。任何一步失败都会 toast 但不阻塞战斗（fallback 到战斗）。
  async _playDialogueSafely(path, key) {
    console.info(`[mainline] playing dialogue: path=${path} key=${key}`);
    try {
      const scenes = await this.fetchDialogue(path);
      if (!scenes.length) {
        console.info(`[mainline] dialogue empty: path=${path}`);
        return [];
      }
      console.info(`[mainline] dialogue loaded: path=${path} scenes=${scenes.length}`);
      await Dialog.play(scenes);
      console.info(`[mainline] dialogue done: path=${path}`);
      return scenes;
    } catch (e) {
      console.warn(`[mainline] dialogue play failed: path=${path}`, e);
      toast(`剧情加载失败（${key}）：${e.message}`, 3000);
      return null;
    }
  },

  // ---------- 战斗胜利后的推进回调（由 renderGame finished 分支触发） ----------

  async onBattleFinished(st) {
    if (!state.mainline) return;
    // 防御：advance / next-battle 也依赖 profile；万一 state 因刷新丢
    // 了，重建一次。失败就让原生 modal 提示用户重试。
    const userName = await this.ensureProfile();
    if (!userName) {
      toast("玩家档案丢失，无法推进主线。请返回大厅重试。", 4000);
      return;
    }

    const isWin = this._didHumanWin(st);
    if (!isWin) {
      console.info(`[mainline] USER_ACTION | user=${userName} | action=MAINLINE_BATTLE_LOST | mainline=${state.mainline.id}`);
      // 人类玩家没赢：暂停在 mainline-play，让原生 modal 提示用户
      toast("战斗失败。返回章节列表或放弃当前主线。", 4000);
      document.getElementById("game-over-modal").hidden = false;
      document.getElementById("game-over-title").textContent = "⚔️ 主线战败";
      document.getElementById("game-over-body").textContent =
        "回到章节列表可重试，或点放弃主线。";
      // 改 modal 的返回按钮为"返回章节列表"
      const backBtn = document.querySelector("#game-over-modal [data-action='goto-menu']");
      if (backBtn) backBtn.dataset.action = "goto-mainline-list";
      state.mainlineAdvancePending = false;
      return;
    }

    // 推进
    const r = await this.advance(state.mainline.id, userName, state.mainlineGameId);
    if (r.state === "victory") {
      console.info(`[mainline] USER_ACTION | user=${userName} | action=MAINLINE_CLEAR | mainline=${state.mainline.id}`);
      // 通关：播 victory 对话 + choice
      await this._handleVictory(r);
    } else if (r.state === "dialogue") {
      // 战后对话 → 然后请求下一场 battle
      this._updateHeader({ ...r, battle_index: r.battle_index });
      if (r.post_battle_dialogue_url) {
        await this._playDialogueSafely(
          r.post_battle_dialogue_url,
          r.post_battle_dialogue_key || "post"
        );
      }
      // 自动请求下一场 battle
      await this._requestNextBattle();
    } else {
      toast(`主线推进返回未知状态: ${r.state}`, 3000);
      showView("mainline-list");
    }
    state.mainlineAdvancePending = false;
  },

  _didHumanWin(st) {
    const me = st.players.find(p => p.id === state.mainlinePlayerId);
    return !!(me && me.is_alive);
  },

  async _handleVictory(r) {
    showView("mainline-play");
    this._updateHeader({ ...r, battle_index: (r.battle_index ?? 0) });

    // 播放 victory 对话
    try {
      const scenes = await this.fetchDialogue("stories/chapter_01/victory.json");
      // 让用户点 choice：把每个 option.value 作为推进动作
      await Dialog.play(scenes);
    } catch (e) {
      console.warn("victory 对话播放失败", e);
    }

    // 弹奖励提示
    if (r.rewards) {
      const rew = r.rewards;
      const parts = [];
      if (rew.gold) parts.push(`+${rew.gold} 金币`);
      if (rew.unlock_class) parts.push(`解锁 ${rew.unlock_class}`);
      if (rew.exp_per_unit) parts.push(`+${rew.exp_per_unit} 经验/单位`);
      toast("🎉 通关！" + (parts.length ? " " + parts.join("，") : ""), 5000);
    } else {
      toast("🎉 通关！", 4000);
    }

    // 清空主线状态
    this._clearMainlineState();
    showView("mainline-list");
  },

  async _requestNextBattle() {
    const userName = await this.ensureProfile();
    if (!userName) return;  // ensureProfile 已 toast
    try {
      const r = await this.startNextBattle(state.mainline.id, userName);
      state.mainlineGameId = r.game_id;
      state.mainlinePlayerId = r.player_id;
      state.mainline.battle_index = r.battle_index;
      const sess = loadSession() || {};
      saveSession({
        ...sess,
        mainline_game_id: r.game_id,
        mainline_player_id: r.player_id,
        game_id: r.game_id,
        player_id: r.player_id,
      });
      // 没有 pre 对话就直接进战斗
      if (r.pre_battle_dialogue_url) {
        await this._playDialogueSafely(
          r.pre_battle_dialogue_url,
          r.pre_battle_dialogue_key || "intro"
        );
      }
      await this._enterBattlePhase(r);
    } catch (e) {
      toast("加载下一场战斗失败：" + e.message, 3000);
    }
  },

  async abandon() {
    if (!state.mainline) return;
    if (!confirm("确定放弃当前主线？")) return;
    const userName = await this.ensureProfile();
    if (!userName) return;  // ensureProfile 已 toast
    console.info(`[mainline] USER_ACTION | user=${userName} | action=MAINLINE_ABANDON | mainline=${state.mainline.id}`);
    try {
      await this.abandon(state.mainline.id, userName);
    } catch (e) {
      toast("放弃失败：" + e.message, 3000);
      return;
    }
    this._clearMainlineState();
    Dialog.close();
    showView("menu");
    toast("已放弃当前主线");
  },

  _clearMainlineState() {
    state.mainline = null;
    state.mainlineGameId = null;
    state.mainlinePlayerId = null;
    state.mainlineAdvancePending = false;
    // 同步清掉 session 里 mainline 字段
    const sess = loadSession();
    if (sess && sess.mainline_id) {
      delete sess.mainline_id;
      delete sess.mainline_game_id;
      delete sess.mainline_player_id;
      saveSession(sess);
    }
  },

  // ---------- 工具 ----------

  /** 把当前 settings 解析成 user_name。
   *  后端 mainline 端点需要 user_name（不是数字 profile_id）。
   *  优先级：state.me.user_name > state.settings.playerName。
   *  由于服务端没有 /profiles/me 端点，本期先尝试 settings，
   *  后续 step 5 实装登录后再改为正式登录态。
   */
  async _resolveUserName() {
    if (state.me && state.me.user_name) return state.me.user_name;
    if (state.settings && state.settings.playerName) {
      const n = (state.settings.playerName || "").trim();
      if (n) return n;
    }
    // 退化：返回 null，调用方据此 toast 提示
    return null;
  },
};

// 暴露给浏览器控制台
window.mainlineView = MainlineView;

// ============================================================
// Wiring
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  // Preset select change -> update description
  document.getElementById("new-map-preset").addEventListener("change", (e) => {
    updatePresetDescription(e.target, document.getElementById("new-map-desc"));
  });
  document.getElementById("new-unit-composition").addEventListener("change", (e) => {
    updatePresetDescription(e.target, document.getElementById("new-units-desc"));
  });

  // Ref-panel tab switching
  document.querySelectorAll(".ref-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".ref-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.refTab = tab.dataset.refTab;
      renderRefContent();
    });
  });
  // Settings first + fetch unit metadata
  renderSettings();
  fetchUnitClasses();

  // Delegate click handlers via data-action
  document.body.addEventListener("click", async (e) => {
    const target = e.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    switch (action) {
      case "goto-menu":
        clearInterval(state.refreshTimer);
        clearInterval(state.lobbyTimer);
        // NOTE: do NOT clearSession() here — the user may want to come back
        // and resume their lobby/game. We only clear the session when the
        // game ends or the player can no longer rejoin.
        state.selectedUnit = null;
        state.actionMode = null;
        updateResumeButton(loadSession());
        showView("menu");
        break;
      case "resume-game":
        await tryResumeSession();
        break;
      case "goto-free-mode":
        showView("free-mode");
        break;
      case "goto-settings":
        renderSettings();
        showView("settings");
        break;
      case "goto-saves":
        showView("saves");
        await renderSavesView();
        break;
      case "save-delete": {
        const gid = parseInt(target.dataset.gameId);
        const gname = target.dataset.gameName || `#${gid}`;
        if (!gid) { toast("无效存档 id"); break; }
        if (!confirm(`确定要删除存档「${gname}」吗？此操作不可恢复。`)) break;
        try {
          await api("DELETE", `/games/${gid}`);
          toast(`已删除存档 ${gname}`);
          await renderSavesView();
        } catch (e) {
          toast(`删除失败：${e.message}`, 3000);
        }
        break;
      }
      case "goto-new-game":
        document.getElementById("new-name").value = state.settings.playerName ? `${state.settings.playerName}的房间` : "";
        document.getElementById("new-error").hidden = true;
        populatePresetSelects().catch(() => {});
        showView("new-game");
        break;
      case "goto-join-game":
        showView("join-game");
        await renderJoinList();
        break;
      case "goto-help":
        showView("help");
        break;
      case "goto-editor":
        showView("editor");
        initEditor();
        break;
      case "toggle-ref-panel":
        toggleRefPanel();
        break;
      case "toggle-game-menu":
        const menu = document.getElementById("game-menu");
        const overlay = document.getElementById("menu-overlay");
        const visible = menu.hidden;
        menu.hidden = !visible;
        overlay.hidden = !visible;
        break;
      case "show-status":
        // Scroll the side panel's player-list into view
        document.getElementById("players-list")?.scrollIntoView({ behavior: "smooth" });
        break;
      case "add-ai":
        await addAIPlayer();
        break;
      case "remove-ai": {
        const pid = parseInt(target.dataset.playerId);
        await removeAIPlayer(pid);
        break;
      }
      case "start-game":
        await startGame();
        break;
      case "refresh-state":
        await refreshGame();
        toast("已刷新");
        break;
      case "end-turn":
        await endTurn();
        break;
      case "save-settings":
        state.settings.playerName = document.getElementById("setting-name").value.trim();
        state.settings.preferredColor = document.getElementById("setting-color").value;
        state.settings.theme = document.getElementById("setting-theme").value;
        state.settings.refreshSeconds = parseInt(document.getElementById("setting-refresh").value) || 3;
        state.settings.soundOn = document.getElementById("setting-sound").checked;
        saveSettings(state.settings);
        applyTheme(state.settings.theme);
        toast("设置已保存");
        break;
      case "create-game":
        await createGame();
        break;
      case "dialog-demo":
        // S0.1 对话框演示：play 一段内嵌剧情样例
        await Dialog.demo();
        break;
      // ---------- 主线模式 ----------
      case "goto-mainline-list":
        showView("mainline-list");
        await Promise.all([
          MainlineView.renderList(),
          MainlineView.renderSlots(),
        ]);
        break;
      case "mainline-slot-resume": {
        const gid = parseInt(target.dataset.gameId);
        if (!gid) break;
        const userName = (state.settings && state.settings.playerName) || "";
        if (!userName) {
          toast("请先在【游戏设置】里设置你的玩家昵称", 3000);
          break;
        }
        try {
          const r = await api("POST", `/games/${gid}/rejoin_by_name`, { user_name: userName });
          state.me = {
            player_id: r.player.id,
            user_name: r.player.user_name,
            color: r.player.color,
            game_id: r.game_id,
            seat: r.player.seat,
          };
          saveSession(state.me);
          // 标记为当前主线模式
          state.mainline = state.mainline || {};
          showView("game");
          await refreshGame();
          toast("已从存档继续");
        } catch (e) {
          toast(`继续存档失败：${e.message}`, 3000);
        }
        break;
      }
      case "mainline-slot-delete": {
        const gid = parseInt(target.dataset.gameId);
        if (!gid) break;
        if (!confirm(`确定要删除主线存档 #${gid} 吗？此操作不可恢复。`)) break;
        try {
          await api("DELETE", `/games/${gid}`);
          toast(`已删除存档 #${gid}`);
          await MainlineView.renderSlots();
        } catch (e) {
          toast(`删除失败：${e.message}`, 3000);
        }
        break;
      }
      case "mainline-card-click": {
        const mid = target.dataset.mainlineId;
        if (!mid) {
          toast("无效的章节 id", 2000);
          break;
        }
        // 把按钮引用传过去，让 startAndEnter 加 loading 状态防狂点
        await MainlineView.startAndEnter(mid, target);
        break;
      }
      case "mainline-abandon":
        await MainlineView.abandon();
        break;
    }
  });

  showView("menu");

  // Show resume button if a session is saved (regardless of whether rejoin works)
  updateResumeButton(loadSession());

  // AI type selector: show personality only for LLM
  const aiKindSel = document.getElementById("lobby-ai-kind");
  const aiPersSel = document.getElementById("lobby-ai-personality");
  if (aiKindSel && aiPersSel) {
    aiKindSel.addEventListener("change", () => {
      aiPersSel.style.visibility = aiKindSel.value === "llm" ? "visible" : "hidden";
    });
    aiPersSel.style.visibility = aiKindSel.value === "llm" ? "visible" : "hidden";
  }

  // ============================================================
  // Map editor (custom map designer)
  // ============================================================
  const editorState = {
    width: 15,
    height: 15,
    layout: null,         // 2D array of terrain chars
    initialUnits: [],     // [{x, y, type, color, level}]
    biome: "grass",
    tool: "P",            // current tool ("select" / "P" / "F" / "M" / "R" / "C" / "unit-..." / "erase")
    color: "red",         // current unit color (also used for new units + recolor selected)
    mapId: null,
    mapName: "",
    selectedIdx: -1,      // index into initialUnits for edit ops; -1 = none
    // Undo/redo: snapshots of the mutable state (deep copies).
    undoStack: [],
    redoStack: [],
  };

  // Deep-snapshot the editable part of editorState for undo/redo.
  function snapshotEditor() {
    return {
      width: editorState.width,
      height: editorState.height,
      layout: editorState.layout.map(row => row.slice()),
      initialUnits: editorState.initialUnits.map(u => ({ ...u })),
      biome: editorState.biome,
      mapName: editorState.mapName,
      mapId: editorState.mapId,
      selectedIdx: editorState.selectedIdx,
    };
  }

  function pushUndo() {
    editorState.undoStack.push(snapshotEditor());
    if (editorState.undoStack.length > 50) editorState.undoStack.shift();
    editorState.redoStack = [];   // any new action invalidates redo
    updateUndoButtons();
  }

  function applySnapshot(snap) {
    editorState.width = snap.width;
    editorState.height = snap.height;
    editorState.layout = snap.layout.map(row => row.slice());
    editorState.initialUnits = snap.initialUnits.map(u => ({ ...u }));
    editorState.biome = snap.biome;
    editorState.mapName = snap.mapName;
    editorState.mapId = snap.mapId;
    editorState.selectedIdx = snap.selectedIdx;
    // Reflect into form inputs
    document.getElementById("editor-name").value = editorState.mapName || "";
    document.getElementById("editor-width").value = editorState.width;
    document.getElementById("editor-height").value = editorState.height;
    document.getElementById("editor-biome").value = editorState.biome;
    updateEditorBiomeBadge();
    renderEditorBoard();
    updateUndoButtons();
  }

  function undoEditor() {
    if (editorState.undoStack.length === 0) return;
    editorState.redoStack.push(snapshotEditor());
    applySnapshot(editorState.undoStack.pop());
  }

  function redoEditor() {
    if (editorState.redoStack.length === 0) return;
    editorState.undoStack.push(snapshotEditor());
    applySnapshot(editorState.redoStack.pop());
  }

  function updateUndoButtons() {
    const u = document.getElementById("editor-undo-btn");
    const r = document.getElementById("editor-redo-btn");
    if (u) u.disabled = editorState.undoStack.length === 0;
    if (r) r.disabled = editorState.redoStack.length === 0;
  }

  // Remember the last terrain brush the user used, so fill / line tools
  // know which terrain to paint. Defaults to plain.
  let lastTerrainBrush = "P";
  function lastTerrainTool() { return lastTerrainBrush; }

  function makeEmptyLayout(w, h, fill = "P") {
    return Array.from({ length: h }, () => fill.repeat(w));
  }

  // editorState.layout is a string[] (one string per row) so it can be sent
  // straight to the JSON API. Strings are immutable, so layout[y][x] = ch
  // silently no-ops. Use this helper instead.
  function setLayoutCell(layout, x, y, ch) {
    const row = layout[y];
    layout[y] = row.slice(0, x) + ch + row.slice(x + 1);
  }

  function renderEditorBoard() {
    const board = document.getElementById("editor-board");
    if (!board) return;
    board.innerHTML = "";
    const W = editorState.width, H = editorState.height;
    // CSS grid uses these vars to size the template. Without them, the grid
    // stays 15×15 and the extra cells wrap into implicit overflow rows.
    board.style.setProperty("--w", String(W));
    board.style.setProperty("--h", String(H));
    // Build unit index + reverse map unitIdx → unit
    const unitMap = new Map();
    const idxAt = new Map();
    editorState.initialUnits.forEach((u, i) => {
      unitMap.set(`${u.x},${u.y}`, u);
      idxAt.set(`${u.x},${u.y}`, i);
    });
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const terrainChar = editorState.layout[y][x] || "P";
        const terrain = terrainNameFromChar(terrainChar);
        const cell = document.createElement("div");
        cell.className = "editor-cell t-" + terrain;
        cell.dataset.x = x;
        cell.dataset.y = y;
        // background tile image
        cell.style.backgroundImage = `url(${tileImageUrl(terrain, editorState.biome, x, y)})`;
        // unit overlay
        const u = unitMap.get(`${x},${y}`);
        if (u) {
          const uEl = document.createElement("div");
          uEl.className = `unit u-${u.color}`;
          uEl.textContent = unitGlyph(u.type);
          uEl.title = `${u.type} (Lv.${u.level})`;
          cell.appendChild(uEl);
          // Highlight selected unit
          if (idxAt.get(`${x},${y}`) === editorState.selectedIdx) {
            cell.classList.add("unit-selected");
            uEl.classList.add("selected");
          }
        }
        cell.addEventListener("click", () => onEditorCellClick(x, y));
        cell.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          eraseEditorCell(x, y);
        });
        // Line tool: drag to draw a line from start to end
        cell.addEventListener("mousedown", () => onEditorCellMouseDown(x, y));
        cell.addEventListener("mouseup", () => onEditorCellMouseUp(x, y));
        board.appendChild(cell);
      }
    }
    updateSelectedInfo();
  }

  function updateSelectedInfo() {
    const info = document.getElementById("editor-selected-info");
    if (!info) return;
    const u = editorState.selectedIdx >= 0
      ? editorState.initialUnits[editorState.selectedIdx]
      : null;
    if (!u) {
      info.textContent = "未选中单位（用「选择」工具点击单位即可选中）";
      return;
    }
    info.innerHTML = `
      选中：<b>${u.type}</b> @ (${u.x},${u.y}) · Lv.${u.level} · <span style="color:${playerColorCss(u.color)}">●</span> ${u.color}
      <button class="btn btn-tiny" id="editor-unit-lvl-up">Lv+</button>
      <button class="btn btn-tiny" id="editor-unit-lvl-down">Lv-</button>
      <button class="btn btn-tiny btn-danger" id="editor-unit-delete">删除</button>
    `;
    // Wire up the inner buttons (re-query each time)
    const lvlUp = document.getElementById("editor-unit-lvl-up");
    const lvlDn = document.getElementById("editor-unit-lvl-down");
    const delBtn = document.getElementById("editor-unit-delete");
    if (lvlUp) lvlUp.onclick = () => {
      if (u.level < 10) { pushUndo(); u.level++; renderEditorBoard(); }
    };
    if (lvlDn) lvlDn.onclick = () => {
      if (u.level > 1) { pushUndo(); u.level--; renderEditorBoard(); }
    };
    if (delBtn) delBtn.onclick = () => {
      pushUndo();
      editorState.initialUnits = editorState.initialUnits.filter(x => x !== u);
      editorState.selectedIdx = -1;
      renderEditorBoard();
    };
  }

  function onEditorCellClick(x, y) {
    const tool = editorState.tool;

    // SELECT tool: pick up / move existing units
    if (tool === "select") {
      const existingIdx = editorState.initialUnits.findIndex(
        u => u.x === x && u.y === y
      );
      if (existingIdx >= 0) {
        // Click on existing unit → select it
        editorState.selectedIdx = existingIdx;
        renderEditorBoard();
        return;
      }
      if (editorState.selectedIdx >= 0) {
        // Click empty cell → move selected unit here
        if (editorState.layout[y][x] === "C") {
          toast("城堡格不能放单位");
          return;
        }
        const u = editorState.initialUnits[editorState.selectedIdx];
        if (u.x === x && u.y === y) return;  // no-op
        pushUndo();
        u.x = x; u.y = y;
        editorState.selectedIdx = editorState.initialUnits.indexOf(u);
        renderEditorBoard();
        return;
      }
      return; // no selection, click empty → nothing
    }

    if (tool === "erase") {
      eraseEditorCell(x, y);
      return;
    }
    if (tool.startsWith("unit-")) {
      const unitType = tool.slice(5);
      // Castle cells can't hold units (server validates)
      if (editorState.layout[y][x] === "C") {
        toast("城堡格不能放单位");
        return;
      }
      pushUndo();
      // Remove any existing unit at this cell
      editorState.initialUnits = editorState.initialUnits.filter(
        u => !(u.x === x && u.y === y)
      );
      editorState.initialUnits.push({
        x, y, type: unitType, color: editorState.color, level: 1,
      });
      editorState.selectedIdx = editorState.initialUnits.length - 1;
      renderEditorBoard();
      return;
    }
    // Fill tool: BFS flood fill of connected same-terrain region
    if (tool === "fill") {
      const targetTerrain = editorState.layout[y][x];
      const replacement = lastTerrainTool();  // use most recent terrain brush
      if (!replacement || targetTerrain === replacement) return;
      pushUndo();
      const stack = [[x, y]];
      const visited = new Set([`${x},${y}`]);
      while (stack.length) {
        const [cx, cy] = stack.pop();
        setLayoutCell(editorState.layout, cx, cy, replacement);
        const neighbors = [[cx+1,cy],[cx-1,cy],[cx,cy+1],[cx,cy-1]];
        for (const [nx, ny] of neighbors) {
          const key = `${nx},${ny}`;
          if (visited.has(key)) continue;
          if (nx < 0 || nx >= editorState.width) continue;
          if (ny < 0 || ny >= editorState.height) continue;
          if (editorState.layout[ny][nx] !== targetTerrain) continue;
          visited.add(key);
          stack.push([nx, ny]);
        }
      }
      renderEditorBoard();
      return;
    }
    // Line tool: handled via mousedown/mouseup (lineStart state), not click
    if (tool === "line") return;
    // Terrain tool: P / F / M / R / C
    const row = editorState.layout[y];
    if (row[x] !== tool) {
      pushUndo();
      setLayoutCell(editorState.layout, x, y, tool);
      lastTerrainBrush = tool;
      renderEditorBoard();
    }
  }

  // Line tool: mousedown records start, mouseup draws line from start to end.
  let lineStart = null;  // [x, y] | null
  function onEditorCellMouseDown(x, y) {
    if (editorState.tool !== "line") return;
    lineStart = [x, y];
  }
  function onEditorCellMouseUp(x, y) {
    if (editorState.tool !== "line" || !lineStart) return;
    const [x0, y0] = lineStart;
    lineStart = null;
    const brush = lastTerrainBrush;
    if (!brush) return;
    pushUndo();
    // Bresenham's line
    let cx = x0, cy = y0;
    const dx = Math.abs(x - x0), dy = Math.abs(y - y0);
    const sx = x0 < x ? 1 : -1;
    const sy = y0 < y ? 1 : -1;
    let err = dx - dy;
    while (true) {
      if (cx >= 0 && cx < editorState.width && cy >= 0 && cy < editorState.height) {
        setLayoutCell(editorState.layout, cx, cy, brush);
      }
      if (cx === x && cy === y) break;
      const e2 = 2 * err;
      if (e2 > -dy) { err -= dy; cx += sx; }
      if (e2 <  dx) { err += dx; cy += sy; }
    }
    renderEditorBoard();
  }

  function eraseEditorCell(x, y) {
    pushUndo();
    // Remove any unit at this cell
    editorState.initialUnits = editorState.initialUnits.filter(
      u => !(u.x === x && u.y === y)
    );
    // Reset terrain to plain
    setLayoutCell(editorState.layout, x, y, "P");
    editorState.selectedIdx = -1;
    renderEditorBoard();
  }

  function initEditor() {
    if (editorState.layout === null) {
      editorState.width = 15;
      editorState.height = 15;
      editorState.layout = makeEmptyLayout(15, 15);
      editorState.initialUnits = [];
      editorState.biome = "grass";
      editorState.mapId = null;
      editorState.mapName = "";
    }
    // Wire up toolbar controls (idempotent: only once)
    if (!window.__editorWired) {
      window.__editorWired = true;
      document.getElementById("editor-resize-btn").addEventListener("click", onEditorResize);
      document.getElementById("editor-new-btn").addEventListener("click", onEditorNew);
      document.getElementById("editor-load-btn").addEventListener("click", onEditorLoadClick);
      document.getElementById("editor-save-btn").addEventListener("click", onEditorSave);
      document.getElementById("editor-undo-btn").addEventListener("click", undoEditor);
      document.getElementById("editor-redo-btn").addEventListener("click", redoEditor);
      // Biome change → update badge + re-render
      document.getElementById("editor-biome").addEventListener("change", (ev) => {
        editorState.biome = ev.target.value;
        updateEditorBiomeBadge();
        refreshEditorToolTerrainSwatches();
        renderEditorBoard();
      });
      // Keyboard shortcuts (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z) — only when editor view is active
      document.addEventListener("keydown", (ev) => {
        const editorView = document.getElementById("view-editor");
        if (!editorView || editorView.hidden) return;
        const ctrl = ev.ctrlKey || ev.metaKey;
        if (!ctrl) return;
        if (ev.key === "z" && !ev.shiftKey) {
          ev.preventDefault();
          undoEditor();
        } else if ((ev.key === "y") || (ev.key === "z" && ev.shiftKey)) {
          ev.preventDefault();
          redoEditor();
        }
      });
      // Tool buttons
      document.querySelectorAll(".tool-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".tool-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          editorState.tool = btn.dataset.tool;
          // Clear selection when switching away from select tool
          if (btn.dataset.tool !== "select") {
            editorState.selectedIdx = -1;
            updateSelectedInfo();
          }
        });
      });
      // Color buttons — also recolor selected unit if any
      document.querySelectorAll(".color-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".color-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          editorState.color = btn.dataset.color;
          // Update unit-tool swatches so the user sees the new player color
          refreshEditorToolUnitSwatches();
          // Apply color to selected unit
          if (editorState.selectedIdx >= 0) {
            const u = editorState.initialUnits[editorState.selectedIdx];
            if (u.color !== btn.dataset.color) {
              pushUndo();
              u.color = btn.dataset.color;
              renderEditorBoard();
            }
          }
        });
      });
    }
    // Reflect current state into form inputs
    document.getElementById("editor-name").value = editorState.mapName || "";
    // Clear any stale validation state (e.g. from a previous failed save)
    const _nameInput = document.getElementById("editor-name");
    if (_nameInput) _nameInput.classList.remove("is-invalid");
    const _nameErr = document.getElementById("editor-name-error");
    if (_nameErr) _nameErr.hidden = true;
    document.getElementById("editor-width").value = editorState.width;
    document.getElementById("editor-height").value = editorState.height;
    document.getElementById("editor-biome").value = editorState.biome;
    updateEditorBiomeBadge();
    // Paint tool button previews (tile PNGs + unit glyphs + unit color).
    refreshEditorToolTerrainSwatches();
    refreshEditorToolUnitSwatches();
    refreshEditorToolGlyphs();
    renderEditorBoard();
    updateUndoButtons();
  }

  // Reflect the current biome into the visible badge.
  const BIOME_LABEL = { grass: "草原", snow: "雪地", desert: "沙漠" };
  function updateEditorBiomeBadge() {
    const el = document.getElementById("editor-biome-badge");
    if (!el) return;
    const biome = editorState.biome || "grass";
    el.textContent = BIOME_LABEL[biome] || biome;
    el.className = `biome-badge biome-${biome}`;
  }

  // Populate the unit glyphs inside the tool buttons (剑/弓/骑/疗).
  // Called once UNIT_CLASSES has loaded.
  function refreshEditorToolGlyphs() {
    document.querySelectorAll(".tool-swatch[data-glyph]").forEach((el) => {
      const type = el.dataset.glyph;
      const cls = UNIT_CLASSES[type];
      el.textContent = (cls && cls.glyph) || "?";
    });
  }

  // Player color → CSS hex (used for unit swatch background).
  const EDITOR_COLOR_HEX = {
    red:    "#e85a6a",
    blue:   "#5a8ae8",
    green:  "#5ae87a",
    yellow: "#e8d65a",
  };
  // Refresh the unit swatches: paint them with the current editor player color
  // so the user can tell at a glance what color the next unit will be.
  function refreshEditorToolUnitSwatches() {
    const hex = EDITOR_COLOR_HEX[editorState.color] || "#888";
    document.querySelectorAll(".tool-swatch.tool-unit-swatch").forEach((el) => {
      el.style.background = hex;
    });
  }
  // Refresh the terrain swatches with the actual tile PNGs.
  // Re-runs when biome changes since some tiles are biome-aware.
  function refreshEditorToolTerrainSwatches() {
    const biome = editorState.biome || "grass";
    document.querySelectorAll(".tool-btn[data-tile]").forEach((btn) => {
      const ch = btn.dataset.tile;
      const name = TERRAIN_CHAR_TO_NAME[ch] || "plain";
      const sw = btn.querySelector(".tool-swatch");
      if (sw) sw.style.backgroundImage = `url(${tileImageUrl(name, biome, 0, 0)})`;
    });
  }

  function onEditorResize() {
    const newW = parseInt(document.getElementById("editor-width").value, 10);
    const newH = parseInt(document.getElementById("editor-height").value, 10);
    if (!Number.isFinite(newW) || !Number.isFinite(newH) ||
        newW < 15 || newW > 35 || newH < 15 || newH > 40) {
      toast("尺寸超出范围（宽 15-35, 高 15-40）");
      return;
    }
    if (newW === editorState.width && newH === editorState.height) return;
    pushUndo();
    // Grow / shrink layout preserving existing cells
    const newLayout = makeEmptyLayout(newW, newH);
    for (let y = 0; y < Math.min(editorState.height, newH); y++) {
      for (let x = 0; x < Math.min(editorState.width, newW); x++) {
        setLayoutCell(newLayout, x, y, editorState.layout[y][x] || "P");
      }
    }
    editorState.width = newW;
    editorState.height = newH;
    editorState.layout = newLayout;
    // Drop out-of-bounds units
    editorState.initialUnits = editorState.initialUnits.filter(
      u => u.x < newW && u.y < newH
    );
    renderEditorBoard();
  }

  async function onEditorNew() {
    if (editorState.mapId || (editorState.layout && editorState.layout.join("").replace(/P/g, "").length > 0)) {
      const ok = await showConfirm("新建空白地图？当前未保存的改动会丢失。", {
        title: "新建地图",
        confirmLabel: "新建",
        danger: true,
      });
      if (!ok) return;
    }
    editorState.layout = makeEmptyLayout(15, 15);
    editorState.initialUnits = [];
    editorState.width = 15;
    editorState.height = 15;
    editorState.biome = "grass";
    editorState.mapId = null;
    editorState.mapName = "";
    editorState.selectedIdx = -1;
    editorState.undoStack = [];
    editorState.redoStack = [];
    initEditor();
  }

  async function onEditorLoadClick() {
    let maps;
    try {
      maps = await api("GET", "/editor/maps");
    } catch (e) {
      toast("读取列表失败：" + e.message);
      return;
    }
    if (!maps || maps.length === 0) {
      await showAlert("暂无已保存的地图", { title: "读取地图" });
      return;
    }
    // Build an in-game list modal: each map is a clickable row.
    const list = document.createElement("div");
    list.className = "choice-list";
    const BIOME_LABEL_ZH = { grass: "草原", snow: "雪地", desert: "沙漠" };
    maps.forEach((m) => {
      const item = document.createElement("button");
      item.className = "choice-item";
      item.type = "button";
      const left = document.createElement("span");
      left.textContent = m.name;
      const right = document.createElement("span");
      right.className = "meta";
      right.textContent = `${m.width}×${m.height} · ${BIOME_LABEL_ZH[m.biome] || m.biome}`;
      item.appendChild(left);
      item.appendChild(right);
      item.addEventListener("click", () => {
        // resolve the pending modal promise with this map id, then close.
        const r = _modalResolve;
        _modalResolve = null;
        document.getElementById("generic-modal").hidden = true;
        if (r) r(m.id);
      });
      list.appendChild(item);
    });
    const result = await showModal({
      title: `读取地图（${maps.length} 张）`,
      body: list,
      buttons: [{ label: "取消", value: null, kind: "secondary" }],
    });
    if (result) await loadEditorMap(result);
  }

  async function loadEditorMap(mapId) {
    try {
      const m = await api("GET", `/editor/maps/${mapId}`);
      editorState.mapId = m.id;
      editorState.mapName = m.name;
      editorState.width = m.size.width;
      editorState.height = m.size.height;
      editorState.biome = m.biome;
      editorState.layout = m.layout.map(row => row.slice());
      editorState.initialUnits = m.initial_units.map(u => ({ ...u }));
      editorState.selectedIdx = -1;
      editorState.undoStack = [];
      editorState.redoStack = [];
      initEditor();
      toast(`已读取：${m.name}`);
    } catch (e) {
      toast("读取失败：" + e.message);
    }
  }

  async function onEditorSave() {
    const nameInput = document.getElementById("editor-name");
    const name = nameInput.value.trim();
    if (!name) {
      // Mark the field invalid + show inline error + blocking modal so the
      // user can't miss it. Clear the error as soon as they start typing.
      nameInput.classList.add("is-invalid");
      nameInput.focus();
      const err = document.getElementById("editor-name-error");
      if (err) err.hidden = false;
      const onInput = () => {
        nameInput.classList.remove("is-invalid");
        if (err) err.hidden = true;
        nameInput.removeEventListener("input", onInput);
      };
      nameInput.addEventListener("input", onInput);
      await showAlert("请先填写地图名（地图名用于在地图列表里识别）", { title: "保存失败" });
      return;
    }
    const biome = document.getElementById("editor-biome").value;
    editorState.biome = biome;
    const body = {
      id: editorState.mapId || undefined,
      name,
      size: { width: editorState.width, height: editorState.height },
      biome,
      layout: editorState.layout,
      initial_units: editorState.initialUnits,
    };
    try {
      const m = await api("POST", "/editor/maps", body);
      editorState.mapId = m.id;
      editorState.mapName = m.name;
      // Clear any prior invalid state
      nameInput.classList.remove("is-invalid");
      const err = document.getElementById("editor-name-error");
      if (err) err.hidden = true;
      toast(`保存成功！id=${m.id}（${m.size.width}x${m.size.height}）`);
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  }

});