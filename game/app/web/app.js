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
  actionMode: null,      // "move" | "attack" | null (driven by bubble)
  pendingMove: null,     // { toX, toY } - awaiting move confirmation
  refreshTimer: null,
  presets: null,         // { maps: [], unit_compositions: [] }
  refPanelOpen: false,
  refTab: "terrain",
  lastTurnKey: null,     // for detecting turn changes (banner trigger)
  actionsTaken: 0,
  actionsRequired: 2,
  bannerTimeout: null,
};

// ----- API helpers -----
async function api(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    const msg = (data && data.detail) || r.statusText || `HTTP ${r.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
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
    if (p.is_ai) html += `<span class="ai-badge">AI</span>`;
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
  try {
    await api("POST", `/games/${gid}/add-ai`, { difficulty: "normal" });
    toast("已加入 AI 电脑");
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
  document.getElementById("game-current-player").textContent = `轮到：${cur ? cur.user_name : "—"}${curIsAI ? " 🤖" : ""}`;
  document.getElementById("game-map-seed").textContent = `种子：${st.game.map_seed}`;

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
    clearInterval(state.refreshTimer);
  } else {
    document.getElementById("game-over-modal").hidden = true;
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
  const el = document.getElementById("action-counter");
  if (!el) return;
  el.textContent = `${state.actionsTaken}/${state.actionsRequired}`;
  el.classList.toggle("ready", state.actionsTaken >= state.actionsRequired);
  el.classList.toggle("short", state.actionsTaken < state.actionsRequired);
  // Disable end-turn button when not enough actions
  const endBtn = document.querySelector('[data-action="end-turn"]');
  if (endBtn) {
    const isMyTurn = state.game?.current_player_id === state.me.player_id;
    const enough = state.actionsTaken >= state.actionsRequired;
    endBtn.disabled = !(isMyTurn && enough);
    endBtn.title = isMyTurn && !enough
      ? `需要操作至少 ${state.actionsRequired} 个单位`
      : "";
  }
}

function renderBoard(st) {
  const board = document.getElementById("board");
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
  for (let y = 0; y < 15; y++) {
    for (let x = 0; x < 15; x++) {
      const tile = tileMap.get(`${x},${y}`);
      const cell = document.createElement("div");
      cell.className = "cell t-" + (tile?.terrain || "plain");
      cell.dataset.x = x;
      cell.dataset.y = y;

      const occupant = unitMap.get(`${x},${y}`);
      if (occupant) {
        const u = occupant.unit;
        const uEl = document.createElement("div");
        uEl.className = `unit u-${occupant.player.color}` + (u.has_acted ? " acted" : "");
        uEl.dataset.unitId = u.id;
        uEl.textContent = unitGlyph(u.unit_type);
        uEl.title = `${u.name} (Lv.${u.level}) HP ${u.hp}/${u.max_hp}`;
        const hp = document.createElement("div");
        hp.className = "hpbar";
        const fill = document.createElement("div");
        const pct = u.max_hp ? (u.hp / u.max_hp) * 100 : 0;
        fill.style.width = pct + "%";
        if (pct < 35) fill.classList.add("low");
        hp.appendChild(fill);
        uEl.appendChild(hp);
        cell.appendChild(uEl);
      }

      // Highlights
      if (state.selectedUnit && state.selectedUnit.x === x && state.selectedUnit.y === y) {
        cell.classList.add("selected");
      }
      if (state.actionMode === "move" && state.reachableTiles?.has(`${x},${y}`)) {
        cell.classList.add("move-hint");
      }
      if (state.actionMode === "attack" && state.attackTargets?.has(`${x},${y}`)) {
        cell.classList.add("target");
      }

      cell.addEventListener("click", () => onCellClick(x, y, st));
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
  const st = state.game;
  const tileMap = new Map();
  for (const t of st.tiles) tileMap.set(`${t.x},${t.y}`, t);
  const occupied = new Set();
  for (const p of st.players) for (const u of p.units) {
    if (u.id !== unit.id && u.hp > 0) occupied.add(`${u.x},${u.y}`);
  }
  const reachable = new Set();
  const queue = [{ x: unit.x, y: unit.y, cost: 0 }];
  const visited = new Map([[`${unit.x},${unit.y}`, 0]]);
  const dirs = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
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
      if (newCost > unit.mov) continue;
      if ((visited.get(key) ?? Infinity) <= newCost) continue;
      visited.set(key, newCost);
      reachable.add(key);
      queue.push({ x: nx, y: ny, cost: newCost });
    }
  }
  return reachable;
}

function computeAttackTargets(unit) {
  const st = state.game;
  const targets = new Set();
  let atkRange = 1;
  if (unit.unit_type === "archer") atkRange = 2;
  if ((unit.skills || []).includes("snipe")) atkRange += 1;
  for (const p of st.players) {
    if (p.id === state.me.player_id) continue;
    for (const u of p.units) {
      if (u.hp <= 0) continue;
      const d = Math.max(Math.abs(u.x - unit.x), Math.abs(u.y - unit.y));
      if (d > 0 && d <= atkRange) targets.add(`${u.x},${u.y}`);
    }
  }
  return targets;
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

  const st = state.game;
  const myPlayer = st.players.find(p => p.id === state.me.player_id);
  const acted = myPlayer?.units.filter(u => u.hp > 0 && u.has_acted).length || 0;
  const maxActions = (myPlayer?.seat === 0 && st.game.turn_number === 1) ? 1 : 2;
  const atMax = acted >= maxActions;

  const canMove = !atMax && reachable.size > 0;
  const canAttack = !atMax && targets.size > 0;
  const canHeal = !atMax && (unit.skills || []).includes("heal");
  const canRally = !atMax && (unit.skills || []).includes("rally");
  const canWait = !atMax;

  let html = `<div class="ab-title">${escapeHtml(unit.name)}${atMax ? " 🚫" : ""}</div>`;
  if (atMax) {
    html += `<div class="ab-row" style="font-size:12px;color:var(--text-dim);text-align:center;padding:4px 6px;">本回合已操作 ${acted}/${maxActions}，无法再行动</div>`;
  }
  html += `<div class="ab-row">`;
  html += `<button class="ab-btn primary" data-ab="move" ${canMove ? "" : "disabled"}>🚶 移动</button>`;
  html += `<button class="ab-btn danger" data-ab="attack" ${canAttack ? "" : "disabled"}>⚔️ 攻击</button>`;
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
  const html = `
    <div class="ab-title">移动到 (${toX}, ${toY})</div>
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
  const html = `
    <div class="ab-title">攻击 ${escapeHtml(target.name)}</div>
    <div class="ab-row">
      <button class="ab-btn danger" data-ab="confirm-attack">⚔️ 确认攻击</button>
      <button class="ab-btn cancel" data-ab="cancel-attack">❌ 取消</button>
    </div>
  `;
  showBubbleAt(target.x, target.y, html, { compact: true });
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, attacker));
  });
}

function showPostMoveBubble(unit) {
  // Called after a successful move. Show attack options for any enemy in range,
  // plus a wait button. Unit has NOT yet acted.
  const targets = computeAttackTargets(unit);
  const enemyList = [];
  for (const p of state.game.players) {
    if (p.id === state.me.player_id) continue;
    for (const u of p.units) {
      if (u.hp <= 0) continue;
      if (targets.has(`${u.x},${u.y}`)) enemyList.push(u);
    }
  }
  if (enemyList.length === 0) {
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
    state.pendingMove = null;
    return;
  }
  // Sort by priority: lowest HP first (likely kill)
  enemyList.sort((a, b) => a.hp - b.hp);

  const parts = [`<div class="ab-title">📍 ${escapeHtml(unit.name)} 已就位</div>`];
  parts.push(`<div class="ab-row">`);
  for (const e of enemyList) {
    parts.push(`<button class="ab-btn danger" data-target="${e.id}" data-ab="pick-attack">⚔️ ${escapeHtml(e.name)} (${e.hp}HP)</button>`);
  }
  parts.push(`</div><div class="ab-row">`);
  parts.push(`<button class="ab-btn cancel" data-ab="wait">⏭ 待机</button>`);
  parts.push(`</div>`);
  showBubbleAt(unit.x, unit.y, parts.join(""));
  document.getElementById("action-bubble").querySelectorAll("[data-ab]").forEach(btn => {
    btn.addEventListener("click", () => onBubbleClick(btn.dataset.ab, unit, btn.dataset.target));
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
      // Just keep bubble open; visual range already shown via highlights
      toast("射程范围以红色高亮显示");
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
      showUnitActionBubble(unit);
      renderBoard(state.game);
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
  // Small hint bubble
  const html = `
    <div class="ab-title">选择目的地</div>
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
  const html = `
    <div class="ab-title">选择攻击目标</div>
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

// ----- Cell click handler -----

function onCellClick(x, y, st) {
  const occupant = findUnitAt(st, x, y);
  const isMyTurn = st.current_player_id === state.me.player_id;

  // Mode: awaiting move confirmation
  if (state.actionMode === "move" && state.selectedUnit) {
    if (state.reachableTiles?.has(`${x},${y}`) && (!occupant || occupant.unit.id === state.selectedUnit.id)) {
      showMoveConfirmBubble(state.selectedUnit, x, y);
    } else {
      toast("该格不可达或被占用");
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

async function doMove(unit, toX, toY) {
  state.actionMode = null;
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
  }
}

async function doAttack(attacker, targetId) {
  state.actionMode = null;
  try {
    const r = await api("POST", `/games/${state.me.game_id}/attack`, {
      player_id: state.me.player_id,
      attacker_id: attacker.id,
      target_id: targetId,
    });
    const totalDmg = r.hits.reduce((s, h) => s + h.damage, 0);
    toast(`造成 ${totalDmg} 伤害${r.hits.some(h => h.is_crit) ? "（暴击！）" : ""}`);
    await refreshGame();
    // After attack, unit has acted. Hide bubble.
    hideBubble();
    state.selectedUnit = null;
  } catch (e) {
    toast("攻击失败：" + e.message);
    hideBubble();
    state.selectedUnit = null;
    state.actionMode = null;
  }
}

async function doSkill(skill, targetId, unit) {
  state.actionMode = null;
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
  }
}

async function doWait(unit) {
  state.actionMode = null;
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
  }
}

async function endTurn() {
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
  el.innerHTML = "";
  for (const log of st.logs.slice(0, 50)) {
    const div = document.createElement("div");
    div.className = "entry " + log.action_type;
    div.textContent = `T${log.turn_number} · ${log.description}`;
    el.appendChild(div);
  }
}

// ----- Reference panel -----

const TERRAIN_REF = [
  { id: "plain",    name: "平地",   color: "#cfe5b6", move: 1, def: 0, note: "通用地形，无加成" },
  { id: "forest",   name: "森林",   color: "#4f8a47", move: 2, def: 2, note: "防御+2，远程视野受阻" },
  { id: "mountain", name: "山地",   color: "#8c8c8c", move: 3, def: 3, note: "防御+3，移动慢" },
  { id: "river",    name: "河流",   color: "#5fb0e8", move: 3, def: 0, note: "移动慢，但无防御" },
  { id: "castle",   name: "城堡",   color: "#f0c75e", move: 1, def: 5, note: "防御+5，需占 1 回合" },
];

const UNIT_REF = [
  { glyph: "剑", color: "var(--p-blue)",  name: "剑士",  hp: 80, atk: 18, def: 15, mov: 3, range: "近战 1",
    skills: [], desc: "均衡的近战单位" },
  { glyph: "弓", color: "var(--p-green)", name: "弓箭手", hp: 60, atk: 20, def:  8, mov: 3, range: "远程 2",
    skills: ["狙击（+1射程）"], desc: "远程输出，怕近身" },
  { glyph: "骑", color: "var(--p-red)",   name: "骑士",  hp: 90, atk: 22, def: 10, mov: 5, range: "近战 1",
    skills: ["连击（两次50%伤害）"], desc: "高移速高攻，但防御低" },
  { glyph: "疗", color: "var(--p-yellow)", name: "治疗师", hp: 70, atk: 5,  def: 10, mov: 3, range: "无",
    skills: ["治愈（+20HP）", "集结（+10%ATK）"], desc: "辅助型，无攻击力" },
];

const SKILL_REF = [
  { name: "连击 (double_strike)", desc: "攻击两次，每次 50% 伤害。骑士默认拥有。" },
  { name: "狙击 (snipe)", desc: "攻击射程 +1。弓箭手默认拥有。" },
  { name: "治愈 (heal)", desc: "对相邻友军恢复 20 HP（消耗本回合行动）。治疗师默认拥有。" },
  { name: "集结 (rally)", desc: "相邻友军本回合攻击 +10%（消耗本回合行动）。治疗师默认拥有。" },
];

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
    el.innerHTML = UNIT_REF.map(u => `
      <div class="ref-unit">
        <div class="glyph" style="background:${u.color}">${u.glyph}</div>
        <div class="info">
          <div class="name">${u.name} <span class="muted small">(${u.range})</span></div>
          <div class="stats">HP ${u.hp} · ATK ${u.atk} · DEF ${u.def} · MOV ${u.mov}</div>
          <div class="stats" style="margin-top:2px">${u.desc}</div>
          ${u.skills.length ? `<div class="skills">技能：${u.skills.join("、")}</div>` : ""}
        </div>
      </div>
    `).join("");
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
  return ({ swordsman: "剑", archer: "弓", knight: "骑", healer: "疗" })[type] || "?";
}
function unitTypeName(type) {
  return ({ swordsman: "剑士", archer: "弓箭手", knight: "骑士", healer: "治疗师" })[type] || type;
}
function skillName(s) {
  return ({
    double_strike: "连击",
    snipe: "狙击",
    heal: "治愈",
    rally: "集结",
  })[s] || s;
}

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
  // Settings first
  renderSettings();

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
      case "goto-settings":
        renderSettings();
        showView("settings");
        break;
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
      case "toggle-ref-panel":
        toggleRefPanel();
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
    }
  });

  showView("menu");

  // Show resume button if a session is saved (regardless of whether rejoin works)
  updateResumeButton(loadSession());

  // Auto-resume: if a session is in localStorage, try to rejoin before showing the menu
  tryResumeSession().then((resumed) => {
    if (!resumed) {
      showView("menu");
      updateResumeButton(loadSession());
    }
  });
});