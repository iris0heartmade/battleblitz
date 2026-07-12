const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { chromium } = require("playwright");

const repoRoot = path.resolve(__dirname, "..");
const gameDir = path.join(repoRoot, "game");
const base = process.env.BB_BASE || "http://127.0.0.1:8765";
const userName = process.env.BB_USER_NAME;
const mainlineId = "chapter_01_steel_rebellion";
const outDir = path.join(repoRoot, "playwright-commander-ui");

if (!userName) {
  console.error("BB_USER_NAME is required");
  process.exit(1);
}

function chromiumExecPath() {
  const candidates = [
    "C:/Users/15353/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    "C:/Users/15353/AppData/Local/ms-playwright/chromium-1097/chrome-win/chrome.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
  ];
  return candidates.find((p) => fs.existsSync(p));
}

async function api(method, pathName, body) {
  const res = await fetch(`${base}${pathName}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    throw new Error(`${method} ${pathName} -> ${res.status}: ${text}`);
  }
  return data;
}

function fillMeter(playerId) {
  const code = `
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Player
async def main():
    async with AsyncSessionLocal() as s:
        p = await s.get(Player, ${Number(playerId)})
        p.co_state = {**(p.co_state or {}), "meter": 22, "threshold": 22}
        await s.commit()
asyncio.run(main())
`;
  const python = path.join(gameDir, "venv", "Scripts", "python.exe");
  const result = spawnSync(python, { cwd: gameDir, input: code, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "meter update failed");
  }
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  await api("POST", `/mainlines/${mainlineId}/select-commander`, {
    user_name: userName,
    commander_id: "yun",
  });
  const started = await api("POST", `/mainlines/${mainlineId}/start`, {
    user_name: userName,
    skip_intro: true,
  });
  fillMeter(started.player_id);

  const browser = await chromium.launch({
    headless: true,
    executablePath: chromiumExecPath() || undefined,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await page.addInitScript(({ userName, started, mainlineId }) => {
    localStorage.setItem("battleblitz.settings.v1", JSON.stringify({
      playerName: userName,
      preferredColor: "",
      theme: "classic",
      refreshSeconds: 3,
      soundOn: false,
    }));
    localStorage.setItem("battleblitz.session.v1", JSON.stringify({
      user_name: userName,
      game_id: started.game_id,
      player_id: started.player_id,
      mainline_id: mainlineId,
      mainline_game_id: started.game_id,
      mainline_player_id: started.player_id,
    }));
  }, { userName, started, mainlineId });
  await page.goto(`${base}/ui/`, { waitUntil: "domcontentloaded" });
  await page.click('[data-action="resume-game"]');
  await page.waitForSelector("#view-game:not([hidden])", { timeout: 10000 });
  await page.waitForSelector("#co-meters:not([hidden])", { timeout: 10000 });
  await page.screenshot({ path: path.join(outDir, "05-battle-co-ready.png"), fullPage: true });
  const result = await page.evaluate(() => ({
    coText: document.querySelector("#co-meters")?.innerText || "",
    fireButtons: Array.from(document.querySelectorAll(".co-meter-fire-btn")).map((el) => el.textContent.trim()),
    headerText: document.querySelector(".game-header")?.innerText || "",
  }));
  result.started = started;
  result.screenshot = path.join(outDir, "05-battle-co-ready.png");
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
