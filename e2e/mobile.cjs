// Layout check at phone, tablet and desktop widths. Run after run.cjs (it signs in as the owner it created).
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const WEB = process.env.E2E_WEB || "http://localhost:5174";
const OUT = path.join(__dirname, "output");
fs.mkdirSync(OUT, { recursive: true });
const browserPath = [process.env.E2E_BROWSER, "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].filter(Boolean).find((f) => fs.existsSync(f));
(async () => {
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  const out = [];
  for (const [label, width] of [["phone 390px", 390], ["tablet 820px", 820], ["desktop 1280px", 1280]]) {
    const page = await (await browser.newContext({ viewport: { width, height: 900 } })).newPage();
    await page.goto(WEB);
    await page.getByLabel("Email").fill("owner@dilli.test");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("heading", { name: "Dashboard" }).waitFor();
    const menuBtn = page.getByRole("button", { name: "Toggle navigation" });
    const menuVisible = await menuBtn.isVisible();
    let navOpens = "n/a";
    if (menuVisible) {
      await menuBtn.click();
      navOpens = await page.getByRole("navigation").getByRole("link", { name: "Billing" }).isVisible();
      await page.getByRole("navigation").getByRole("link", { name: "Billing" }).click();
    } else {
      await page.getByRole("navigation").getByRole("link", { name: "Billing" }).click();
    }
    await page.getByRole("heading", { name: "Billing" }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    out.push(`${label}: menu button ${menuVisible ? "visible" : "hidden"}, nav ${navOpens === "n/a" ? "always shown" : navOpens ? "opens" : "DOES NOT OPEN"}, sideways scroll: ${overflow ? "YES (bad)" : "no"}`);
    await page.screenshot({ path: path.join(OUT, `layout-${width}.png`) });
  }
  await browser.close();
  console.log(out.join("\n"));
})();
