// Smoke test for game/app/web/app.js populatePresetSelects().
//
// USAGE:
//   1. One-time setup: cd tools && npm install jsdom
//   2. Run: node tools/test_web_dropdown.js
//
// EXIT CODES:
//   0 = dropdown populated and filter works
//   1 = bug reproduced (ReferenceError or empty dropdown)
//
// Reproduces the user-reported bug "webui can't select map" —
// if any line in the function throws a ReferenceError (e.g. a
// stale reference to a removed DOM element), the dropdown never
// gets populated and the user only sees the hardcoded "classic"
// option in the HTML.

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APP_JS = 'D:/Python/BattleBlitz/battleblitz/game/app/web/app.js';
const INDEX_HTML = 'D:/Python/BattleBlitz/battleblitz/game/app/web/index.html';

if (!fs.existsSync(APP_JS)) {
  console.error(`app.js not found at ${APP_JS}`);
  process.exit(2);
}
if (!fs.existsSync(INDEX_HTML)) {
  console.error(`index.html not found at ${INDEX_HTML}`);
  process.exit(2);
}

const html = fs.readFileSync(INDEX_HTML, 'utf-8');
const js = fs.readFileSync(APP_JS, 'utf-8');

const fakePresets = {
  maps: [
    { id: 'map_2p_a', name: 'Two-player A', description: '2p A',
      biome: 'grass', size: 15, recommended_players: 2, notes: '' },
    { id: 'map_2p_b', name: 'Two-player B', description: '2p B',
      biome: 'grass', size: 18, recommended_players: 2, notes: '' },
    { id: 'map_3p_a', name: 'Three-player A', description: '3p A',
      biome: 'grass', size: 20, recommended_players: 3, notes: '' },
    { id: 'map_4p_a', name: 'Four-player A', description: '4p A',
      biome: 'grass', size: 25, recommended_players: 4, notes: '' },
    { id: 'map_4p_b', name: 'Four-player B', description: '4p B',
      biome: 'grass', size: 30, recommended_players: 4, notes: '' },
    { id: 'map_4p_c', name: 'Four-player C', description: '4p C',
      biome: 'grass', size: 40, recommended_players: 4, notes: '' },
  ],
};

const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://localhost/' });
const { window } = dom;

// Stub fetch (api() in app.js uses both json() and text())
window.fetch = (url) => {
  const isPresets = String(url).includes('/games/presets');
  const body = isPresets ? fakePresets : {};
  return Promise.resolve({
    ok: true, status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
};

// Hook the function we want to test so we can inspect errors.
const wrapScript = `
${js}
window.__lastError = null;
window.addEventListener('error', (ev) => { window.__lastError = ev.error || ev.message; });
window.__populateResult = null;
window.__populateDetail = '';
(async () => {
  try {
    const cs = document.getElementById('new-player-count');
    window.__populateDetail = 'countSel.value=' + JSON.stringify(cs && cs.value);
    await populatePresetSelects();
    const ms = document.getElementById('new-map-preset');
    window.__populateDetail += ' | mapSel.options=' + (ms ? ms.options.length : 'no-sel');
    window.__populateResult = 'ok';
  } catch (e) {
    window.__populateResult = 'threw: ' + (e && e.stack ? e.stack : e);
  }
})();
`;

// Load app.js — wrap eval to catch sync ReferenceErrors, and
// intercept unhandled async errors so we can pinpoint them.
let loadError = null;
try {
  window.eval(wrapScript);
} catch (e) {
  loadError = e;
}

if (loadError) {
  console.error('app.js threw on load:', loadError.message);
  process.exit(1);
}

// Capture unhandled rejections from app.js's async chains
const asyncErrors = [];
window.addEventListener('unhandledrejection', (ev) => {
  asyncErrors.push(ev.reason);
});
process.on('unhandledRejection', (r) => asyncErrors.push(r));

(async () => {
  await new Promise((r) => setTimeout(r, 800));

  if (asyncErrors.length) {
    console.error('Async errors caught:');
    for (const err of asyncErrors) {
      console.error('  ', err && err.stack ? err.stack : err);
    }
  }
  if (window.__populateResult) {
    console.log('populatePresetSelects result:', window.__populateResult);
    console.log('  detail:', window.__populateDetail);
  } else {
    console.log('populatePresetSelects NEVER ran');
  }

  const mapSel = window.document.getElementById('new-map-preset');
  if (!mapSel) {
    console.error('FAIL: #new-map-preset element not found');
    process.exit(1);
  }
  const optionCount = mapSel.options.length;
  console.log(`map <select> option count: ${optionCount}`);
  if (optionCount <= 1) {
    console.error(
      `FAIL: only ${optionCount} option(s) in dropdown — ` +
      `populatePresetSelects likely threw (stale DOM ref). ` +
      `Reproduces "webui can't select map".`
    );
    process.exit(1);
  }

  const values = Array.from(mapSel.options).map((o) => o.value);
  console.log(`option values (count=4): ${JSON.stringify(values)}`);
  // With default countSel.value="4", only 4-player maps should appear
  const expected4p = ['map_4p_a', 'map_4p_b', 'map_4p_c'];
  for (const id of expected4p) {
    if (!values.includes(id)) {
      console.error(`FAIL: missing 4p map option ${id}`);
      process.exit(1);
    }
  }
  for (const id of ['map_2p_a', 'map_2p_b', 'map_3p_a']) {
    if (values.includes(id)) {
      console.error(`FAIL: 2p/3p map ${id} should NOT appear with count=4`);
      process.exit(1);
    }
  }

  // Now switch countSel to 2 and re-populate
  const cs = window.document.getElementById('new-player-count');
  cs.value = '2';
  await window.eval('populatePresetSelects()');
  await new Promise((r) => setTimeout(r, 100));
  const values2 = Array.from(mapSel.options).map((o) => o.value);
  console.log(`option values (count=2): ${JSON.stringify(values2)}`);
  if (!values2.includes('map_2p_a') || !values2.includes('map_2p_b')) {
    console.error('FAIL: 2p maps missing when count=2');
    process.exit(1);
  }
  if (values2.includes('map_4p_a')) {
    console.error('FAIL: 4p map should not appear with count=2');
    process.exit(1);
  }

  console.log('OK: populatePresetSelects populated and filters by player count');
  process.exit(0);
})();