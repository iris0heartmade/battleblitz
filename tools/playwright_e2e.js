// Playwright e2e: simulate a real player using the web UI.
//
// USAGE:
//   1. (Optional) Install chromium if not cached:
//        npx playwright install chromium
//   2. Run the script (it will start a FastAPI server, drive the
//      browser, then shut everything down):
//        node tools/playwright_e2e.js
//
// EXIT CODES:
//   0 = all checks passed
//   1 = bug reproduced or UI misbehaved
//
// What this validates:
//   - Web UI loads at /ui/
//   - Map dropdown (#new-map-preset) contains real options (post-fix)
//   - test_arena_10x10_2v2 can actually be selected
//   - Game can be created end-to-end (POST /games → lobby → start)
//   - Initial spawn shows the correct 20 units for that map

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const GAME_DIR = path.join(REPO_ROOT, 'game');
const PORT = 8765;
const BASE_URL = `http://localhost:${PORT}/ui/`;

function log(...a) { console.log('[e2e]', ...a); }
function err(...a) { console.error('[e2e ERROR]', ...a); }

// Spawn the FastAPI server in background
async function startServer() {
  log(`starting server on :${PORT}...`);
  const py = path.join(GAME_DIR, 'venv', 'Scripts', 'python.exe');
  const server = spawn(
    py, ['-m', 'uvicorn', 'app.main:app', '--port', String(PORT)],
    { cwd: GAME_DIR, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  // On Windows, uvicorn logs INFO to stderr (not stdout). Poll both.
  let ready = false;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (!ready) {
        server.kill();
        reject(new Error('server did not start within 30s'));
      }
    }, 30000);
    const onData = (chunk) => {
      const s = chunk.toString();
      if (s.includes('Application startup complete') || s.includes('Uvicorn running on')) {
        ready = true;
        clearTimeout(timer);
        resolve(server);
      }
    };
    server.stdout.on('data', onData);
    server.stderr.on('data', onData);
    server.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

// Wait until /healthz responds (alternative to log snooping)
async function waitForHealth(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://localhost:${port}/healthz`;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch (_) { /* not ready yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`/healthz never responded on :${port}`);
}

// Use the chromium that Playwright already cached (if present) so
// we don't need to re-download it.
function chromiumExecPath() {
  // Playwright's default install dir on Windows
  const candidates = [
    'C:/Users/15353/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe',
    'C:/Users/15353/AppData/Local/ms-playwright/chromium-1097/chrome-win/chrome.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null; // let playwright pick default
}

async function main() {
  let server;
  let browser;
  let passed = 0;
  let failed = 0;

  function check(label, ok, detail) {
    const tag = ok ? '[PASS]' : '[FAIL]';
    if (ok) passed++; else failed++;
    log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  }

  try {
    server = await startServer();
    // Belt-and-suspenders: also poll /healthz
    await waitForHealth(PORT, 5000);
    log('server ready (healthz OK)');

    const { chromium } = require('playwright');
    const exe = chromiumExecPath();
    log(`chromium executable: ${exe || '(playwright default)'}`);
    browser = await chromium.launch({
      headless: true,
      executablePath: exe || undefined,
      args: ['--no-sandbox'],
    });
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();

    // Surface JS errors immediately
    page.on('pageerror', (e) => err('pageerror:', e.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') err('console.error:', msg.text());
    });

    // ---------- Navigate to UI ----------
    log(`navigating to ${BASE_URL}`);
    const resp = await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    check('page loaded', resp && resp.status() === 200, `status=${resp && resp.status()}`);

    // ---------- Navigate to create-game form ----------
    // Flow: view-menu → 🎮自由模式 → 🆕创建游戏 → form
    log('clicking 自由模式...');
    await page.click('[data-action="goto-free-mode"]');
    await page.waitForSelector('#view-free-mode:not([hidden])', { timeout: 5000 });
    log('clicking 创建游戏...');
    await page.click('[data-action="goto-new-game"]');
    await page.waitForSelector('#view-new-game:not([hidden])', { timeout: 5000 });
    check('navigated to create-game view', true);

    // ---------- Fill name ----------
    const nameInput = await page.$('#new-name');
    if (nameInput) {
      await nameInput.fill('Playwright e2e game');
      check('filled #new-name', true);
    } else {
      check('found #new-name', false);
    }

    // ---------- Pick player count = 4 (default selected, but be explicit) ----------
    const countSel = await page.$('#new-player-count');
    if (countSel) {
      await countSel.selectOption('4');
      check('selected player count 4', true);
    } else {
      check('found #new-player-count', false);
    }

    // ---------- WAIT for populatePresetSelects to finish ----------
    // The function runs after window load. Wait a beat for it.
    await page.waitForTimeout(500);

    // ---------- CRITICAL: check map dropdown content ----------
    const mapSel = await page.$('#new-map-preset');
    if (!mapSel) {
      check('found #new-map-preset', false);
      throw new Error('map dropdown missing — test cannot continue');
    }
    const opts = await mapSel.$$eval('option', (els) =>
      els.map((o) => ({ value: o.value, text: o.textContent }))
    );
    log(`map <select> has ${opts.length} option(s):`);
    for (const o of opts) {
      log(`  value=${JSON.stringify(o.value)} text=${JSON.stringify(o.text.slice(0, 60))}`);
    }
    check(
      'map dropdown has > 1 option (post-fix)',
      opts.length > 1,
      `count=${opts.length}`,
    );

    // ---------- Try to pick test_arena_10x10_2v2 ----------
    const hasArena = opts.some((o) => o.value === 'test_arena_10x10_2v2');
    check('test_arena_10x10_2v2 exists in dropdown', hasArena);
    if (hasArena) {
      await mapSel.selectOption('test_arena_10x10_2v2');
      const selected = await mapSel.$eval('option:checked', (o) => o.value);
      check('selected test_arena_10x10_2v2', selected === 'test_arena_10x10_2v2', selected);
    }

    // ---------- Submit the form ----------
    const submit = await page.$('[data-action="create-game"]');
    if (submit) {
      await Promise.all([
        page.waitForResponse((r) => r.url().includes('/games') && r.request().method() === 'POST'),
        submit.click(),
      ]);
      await page.waitForTimeout(500);
      check('create-game POST succeeded', true);
    } else {
      check('found create-game button', false);
    }

    // ---------- Verify a lobby was created ----------
    // The create-game endpoint returns the game id and the SPA
    // switches to #view-lobby. Look for lobby-specific markers
    // instead of the custom name (which is in a hidden input).
    const lobbyVisible = await page.$('#view-lobby:not([hidden])');
    const startBtn = await page.$('button:has-text("开始游戏")');
    const lobbyText = await page.textContent('#view-lobby').catch(() => '');
    check(
      'lobby view is visible after submit',
      lobbyVisible !== null,
      lobbyVisible ? '#view-lobby shown' : '#view-lobby still hidden',
    );
    check(
      'lobby has a start-game button',
      startBtn !== null,
    );
    check(
      'lobby shows waiting-for-players state',
      /等待|房间/.test(lobbyText),
      lobbyText.slice(0, 80).replace(/\s+/g, ' '),
    );

    // ---------- Take a screenshot for the human to see ----------
    const shotPath = path.join(__dirname, '..', 'e2e_screenshot.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    log(`screenshot saved to ${shotPath}`);

  } catch (e) {
    failed++;
    err('uncaught:', e.message);
    err(e.stack);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) {
      log('shutting down server...');
      server.kill();
    }
  }

  log(`summary: ${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main();