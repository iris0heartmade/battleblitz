const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const repoRoot = path.resolve(__dirname, "..");
const baseUrl = process.env.BB_BASE_URL || "http://127.0.0.1:8765/ui/";
const outDir = path.join(repoRoot, "playwright-commander-ui");

function chromiumExecPath() {
  const candidates = [
    "C:/Users/15353/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    "C:/Users/15353/AppData/Local/ms-playwright/chromium-1097/chrome-win/chrome.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
  ];
  return candidates.find((p) => fs.existsSync(p));
}

async function inspectVisible(page, name, rootSelector) {
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true });
  return page.evaluate((rootSelector) => {
    const root = document.querySelector(rootSelector);
    const scoped = `${rootSelector} [id*=commander], ${rootSelector} [class*=commander], ${rootSelector} [data-action*=commander], ${rootSelector} [id*=co-], ${rootSelector} [class*=co-], ${rootSelector} [data-action*=co-]`;
    const commanderNodes = Array.from(document.querySelectorAll(scoped))
      .map((el) => ({
        tag: el.tagName,
        id: el.id || "",
        className: String(el.className || ""),
        action: el.dataset?.action || "",
        text: (el.innerText || el.textContent || "").trim().slice(0, 160),
      }));
    return {
      text: (root?.innerText || "").trim().slice(0, 2000),
      commanderNodes,
    };
  }, rootSelector);
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const exe = chromiumExecPath();
  const browser = await chromium.launch({
    headless: true,
    executablePath: exe || undefined,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const consoleMessages = [];
  page.on("console", (msg) => consoleMessages.push(`${msg.type()}: ${msg.text()}`));
  page.on("pageerror", (err) => consoleMessages.push(`pageerror: ${err.message}`));

  if (process.env.BB_USER_NAME) {
    await page.addInitScript((userName) => {
      localStorage.setItem("battleblitz.settings.v1", JSON.stringify({
        playerName: userName,
        preferredColor: "",
        theme: "classic",
        refreshSeconds: 3,
        soundOn: false,
      }));
    }, process.env.BB_USER_NAME);
  }

  const result = {};
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#view-menu:not([hidden])");
  result.menu = await inspectVisible(page, "01-menu", "#view-menu");

  await page.click('[data-action="goto-free-mode"]');
  await page.waitForSelector("#view-free-mode:not([hidden])");
  result.freeMode = await inspectVisible(page, "02-free-mode", "#view-free-mode");

  await page.click('[data-action="goto-new-game"]');
  await page.waitForSelector("#view-new-game:not([hidden])");
  await page.waitForTimeout(800);
  result.newGame = await inspectVisible(page, "03-new-game", "#view-new-game");

  await page.click("#view-new-game [data-action='goto-menu']");
  await page.waitForSelector("#view-menu:not([hidden])");
  await page.click('[data-action="goto-mainline-list"]');
  await page.waitForSelector("#view-mainline-list:not([hidden])");
  await page.waitForTimeout(1500);
  result.mainline = await inspectVisible(page, "04-mainline-list", "#view-mainline-list");

  result.consoleMessages = consoleMessages;
  result.screenshots = fs.readdirSync(outDir).map((f) => path.join(outDir, f));
  await browser.close();

  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
