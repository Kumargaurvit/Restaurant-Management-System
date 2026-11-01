// Real-browser click-through of the whole app (see e2e/README.md).
// It registers a restaurant, so it needs a FRESH database: use docker-compose.e2e.yml.
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const WEB = process.env.E2E_WEB || "http://localhost:5174";
const API = process.env.E2E_API || "http://localhost:8013";
const WEBHOOK_SECRET = process.env.E2E_WEBHOOK_SECRET || "check-secret";
const OWNER_CONTACT = process.env.E2E_OWNER_CONTACT || "98100 11111";
const ASSETS = __dirname;
const OUT = path.join(__dirname, "output"); // screenshots of failed steps
fs.mkdirSync(OUT, { recursive: true });

function findBrowser() {
  const candidates = [
    process.env.E2E_BROWSER,
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ].filter(Boolean);
  const found = candidates.find((file) => fs.existsSync(file));
  if (!found) throw new Error("No Chrome or Edge found. Set E2E_BROWSER to its path.");
  return found;
}
const results = [];
const problems = [];

const browserErrors = [];

async function step(name, page, fn) {
  try {
    await fn();
    results.push(["PASS", name]);
  } catch (error) {
    const file = path.join(OUT, `fail-${results.length}.png`);
    await page.screenshot({ path: file, fullPage: true }).catch(() => {});
    results.push(["FAIL", name, String(error.message).split("\n")[0], file]);
  }
}

const tomorrow = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toLocaleDateString("en-CA");
};

(async () => {
  const browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
  });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", (e) => browserErrors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && browserErrors.push(`console: ${m.text()}`));
  page.on("response", (r) => {
    if (r.status() >= 400 && r.url().startsWith(API)) {
      browserErrors.push(`http ${r.status()} ${r.request().method()} ${r.url().replace(API, "")}`);
    }
  });
  page.on("dialog", (d) => d.dismiss());

  const nav = (name) => page.getByRole("navigation").getByRole("link", { name, exact: true });
  const tab = (name) => page.getByRole("tab", { name, exact: true });

  // ------------------------------------------------------------------ setup
  await step("first visit shows the owner set-up form", page, async () => {
    await page.goto(WEB);
    await page.getByRole("heading", { name: "Set up your restaurant" }).waitFor();
  });

  await step("register the owner with a restaurant name", page, async () => {
    await page.getByLabel("Restaurant name").fill("Dilli Test Kitchen");
    await page.getByLabel("Your name").fill("Asha Owner");
    await page.getByLabel("Email").fill("owner@dilli.test");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Create owner account" }).click();
    await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  });

  await step("header shows the restaurant name", page, async () => {
    await page.getByText("Restaurant Manager - Dilli Test Kitchen").waitFor();
  });

  await step("dashboard shows the backend online and all four modules live", page, async () => {
    await page.getByText("Online").first().waitFor();
    const live = await page.getByRole("main").getByText("Live", { exact: true }).count();
    if (live !== 4) throw new Error(`expected 4 live modules, saw ${live}`);
  });

  // --------------------------------------------------------------- settings
  await step("save receipt details in Settings", page, async () => {
    await nav("Settings").click();
    const form = page.getByRole("form", { name: "Receipt details" });
    await form.getByLabel("Address").fill("12 Connaught Place, New Delhi");
    await form.getByLabel("Phone").fill("011 4000 1234");
    await form.getByLabel("GSTIN").fill("07AAAAA0000A1Z5");
    await form.getByLabel("FSSAI licence number").fill("12345678901234");
    await form.getByRole("button", { name: "Save receipt details" }).click();
    await page.getByText(/Saved\. New receipts will use these details/).waitFor();
  });

  await step("an invalid GSTIN is refused with a clear message", page, async () => {
    const form = page.getByRole("form", { name: "Receipt details" });
    await form.getByLabel("GSTIN").fill("BAD");
    await form.getByRole("button", { name: "Save receipt details" }).click();
    await page.getByRole("alert").filter({ hasText: "GSTIN" }).waitFor();
    await form.getByLabel("GSTIN").fill("07AAAAA0000A1Z5");
    await form.getByRole("button", { name: "Save receipt details" }).click();
    await page.getByText(/Saved\./).waitFor();
  });

  await step("upload a logo: it appears in the header straight away", page, async () => {
    const form = page.getByRole("form", { name: "Receipt details" });
    await form.getByLabel(/Logo \(PNG/).setInputFiles(path.join(ASSETS, "logo.png"));
    await form.getByAltText("Logo preview").waitFor();
    await form.getByRole("button", { name: "Save receipt details" }).click();
    await page.getByText(/Saved\./).waitFor();
    await page.getByRole("banner").getByAltText("Restaurant logo").waitFor();
  });

  await step("a non-image file is refused with a friendly message", page, async () => {
    const form = page.getByRole("form", { name: "Receipt details" });
    await form.getByLabel(/Logo \(PNG/).setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
    await form.getByRole("alert").filter({ hasText: "PNG, JPEG or WebP" }).waitFor();
  });

  await step("add a waiter in Settings → Staff", page, async () => {
    const form = page.getByRole("form", { name: "Add staff" });
    await form.getByLabel("Name").fill("Ravi Waiter");
    await form.getByLabel("Email").fill("waiter@dilli.test");
    await form.getByLabel(/Password/).fill("password123");
    await form.getByLabel("Role").selectOption("waiter");
    await form.getByRole("button", { name: "Add staff member" }).click();
    await page.getByText("Staff member added.").waitFor();
  });

  // ---------------------------------------------------------------- billing
  await nav("Billing").click();
  await step("build the menu and a table", page, async () => {
    await tab("Menu & tables").click();
    await page.getByLabel("New category").fill("Mains");
    await page.getByRole("button", { name: "Add category" }).click();
    await page.getByRole("list", { name: "Categories" }).getByText("Mains", { exact: true }).waitFor();

    await page.locator("label", { hasText: "Category" }).locator("select").selectOption({ label: "Mains" });
    await page.getByLabel("Item name").fill("Paneer Tikka");
    await page.getByLabel("Price (₹, excluding GST)").fill("200");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("list", { name: "Menu items" }).locator(".line-name", { hasText: "Paneer Tikka" }).waitFor();

    await page.locator("label", { hasText: "Category" }).locator("select").selectOption({ label: "Mains" });
    await page.getByLabel("Item name").fill("Cola");
    await page.getByLabel("Price (₹, excluding GST)").fill("50");
    await page.getByLabel("GST rate").selectOption("18");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("list", { name: "Menu items" }).locator(".line-name", { hasText: "Cola" }).waitFor();

    await page.getByLabel("Table name").fill("T1");
    await page.getByLabel("Seats").fill("4");
    await page.getByRole("button", { name: "Add table" }).click();
    await page.getByRole("list", { name: "Tables" }).locator(".line-name", { hasText: "T1" }).waitFor();
  });

  await step("add a counted item (stock 2) and give it two sizes", page, async () => {
    await page.locator("label", { hasText: "Category" }).locator("select").selectOption({ label: "Mains" });
    await page.getByLabel("Item name").fill("Lassi");
    await page.getByLabel("Price (₹, excluding GST)").fill("80");
    await page.getByLabel(/^Stock \(leave empty/).fill("2");
    await page.getByRole("button", { name: "Add item" }).click();
    const lassi = page.getByRole("list", { name: "Menu items" }).locator(".line-name", { hasText: "Lassi" });
    await lassi.getByText("2 left").waitFor();

    await page.getByRole("button", { name: "Sizes of Lassi" }).click();
    for (const [name, price] of [["Small", "60"], ["Large", "80"]]) {
      await page.getByLabel("New size name for Lassi").fill(name);
      await page.getByLabel("New size price for Lassi").fill(price);
      await page.getByRole("button", { name: "Add size to Lassi" }).click();
      await page.getByLabel("Sizes of Lassi").getByText(`${name} · ₹${price}.00`).waitFor();
    }
    await lassi.getByText("Small ₹60.00 · Large ₹80.00").waitFor();
  });

  await step("start a dine-in order for a guest (number and name)", page, async () => {
    await tab("Orders").click();
    await page.getByRole("button", { name: "T1 free" }).click();
    await page.getByLabel("Contact number").fill("9810000001");
    await page.getByLabel("Customer name").fill("Asha");
    await page.getByRole("button", { name: "Start order" }).click();
    await page.getByRole("heading", { name: /Table order #1/ }).waitFor();
  });

  await step("add items, send the kitchen ticket", page, async () => {
    await page.getByRole("button", { name: "Add Paneer Tikka" }).click();
    await page.getByRole("button", { name: "Add Paneer Tikka" }).click();
    await page.getByRole("button", { name: "Add Cola" }).click();
    await page.getByLabel("Paneer Tikka quantity").filter({ hasText: "2" }).waitFor();
    await page.getByRole("button", { name: "Send to kitchen" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByText("KITCHEN ORDER").waitFor();
    await dialog.getByText(/2 x Paneer Tikka/).waitFor();
    await dialog.getByRole("button", { name: "Close" }).click();
  });

  await step("generate the bill with correct GST total (₹479.00)", page, async () => {
    await page.getByRole("button", { name: "Generate bill" }).click();
    const bill = page.getByLabel("Bill");
    await bill.getByText("₹479.00").first().waitFor();
    await bill.getByText("CGST").waitFor();
  });

  await step("take payment and the bill is paid", page, async () => {
    await page.getByRole("button", { name: "Take payment" }).click();
    await page.getByLabel("Bill").locator(".badge", { hasText: "Paid" }).waitFor();
  });

  await step("receipt shows restaurant name, address, GSTIN and totals", page, async () => {
    await page.getByRole("button", { name: "Print receipt" }).click();
    const text = await page.getByRole("dialog").locator("pre").innerText();
    for (const expected of ["DILLI TEST KITCHEN", "12 Connaught Place", "GSTIN: 07AAAAA0000A1Z5", "FSSAI: 12345678901234", "479.00", "PAID"]) {
      if (!text.includes(expected)) throw new Error(`receipt is missing "${expected}"`);
    }
    await page.getByRole("dialog").getByAltText("Restaurant logo").waitFor();
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  });

  await step("send the bill to the guest on WhatsApp", page, async () => {
    await page.getByRole("button", { name: "Send on WhatsApp" }).click();
    const form = page.getByRole("form", { name: "Send bill" });
    if ((await form.getByLabel("WhatsApp number").inputValue()) !== "9810000001") throw new Error("number was not prefilled");
    await form.getByRole("button", { name: "Send bill" }).click();
    await page.getByText("Bill sent to 9810000001.").waitFor();
  });

  await step("Customers tab shows the guest and their history", page, async () => {
    await tab("Customers").click();
    await page.getByRole("list", { name: "Customers" }).getByRole("button", { name: /Asha/ }).click();
    const details = page.getByLabel("Customer details");
    await details.getByText("9810000001").waitFor();
    await details.getByRole("list", { name: "Order history" }).getByText(/Paneer Tikka/).waitFor();
  });

  await step("Insights tab ranks Paneer Tikka as the top dish", page, async () => {
    await tab("Insights").click();
    const dishes = page.getByRole("table", { name: "Most ordered dishes" });
    await dishes.getByText("Paneer Tikka").waitFor();
    await page.getByRole("table", { name: "Most frequent customers" }).getByText("Asha").waitFor();
  });

  await step("Reports tab shows today's sales", page, async () => {
    await tab("Reports").click();
    await page.getByText("₹479.00").first().waitFor();
  });

  await step("sizes show in the order screen and stock runs out", page, async () => {
    await tab("Orders").click();
    await page.getByRole("button", { name: "T1 free" }).click();
    await page.getByLabel("Contact number").fill("9810000004");
    await page.getByLabel("Customer name").fill("Ravi");
    await page.getByRole("button", { name: "Start order" }).click();
    await page.getByRole("button", { name: "Add Lassi (Small)" }).waitFor();
    await page.getByRole("button", { name: "Add Lassi (Large)" }).waitFor();
    if (await page.getByRole("button", { name: "Add Lassi", exact: true }).count()) throw new Error("plain Lassi button should not exist");
    await page.getByRole("button", { name: "Add Lassi (Small)" }).click();
    await page.getByRole("button", { name: "Add Lassi (Large)" }).click();
    await page.getByText("Lassi (Small)").first().waitFor();
    // Both portions are taken: both size buttons are now disabled and say sold out.
    await page.getByRole("button", { name: "Add Lassi (Small)" }).getByText("Sold out").waitFor();
    if (!(await page.getByRole("button", { name: "Add Lassi (Large)" }).isDisabled())) throw new Error("Large should be disabled");
  });

  await step("cancelling that order puts the stock back", page, async () => {
    await page.getByRole("button", { name: "Decrease Lassi (Small)" }).click();
    await page.getByRole("button", { name: "Decrease Lassi (Large)" }).click();
    await page.getByRole("button", { name: "Add Lassi (Small)" }).getByText("2 left").waitFor();
    await page.getByRole("button", { name: "Cancel order" }).click();
  });

  // --------------------------------------------------------------- bookings
  await step("make a booking for tomorrow and confirm it", page, async () => {
    await nav("Bookings").click();
    const form = page.getByLabel("New booking");
    await form.getByLabel("Guest name").fill("Neha");
    await form.getByLabel("Mobile number").fill("9810000002");
    await form.getByLabel("Guests").fill("2");
    await form.getByLabel("Date").fill(tomorrow());
    await page.waitForFunction(() => document.querySelectorAll("select option").length > 1);
    await form.getByLabel("Time").selectOption({ index: 1 });
    await form.getByRole("button", { name: "Book table" }).click();
    await page.getByRole("list", { name: "Bookings" }).getByText(/Neha/).first().waitFor();
    await page.getByRole("button", { name: "Confirm Neha" }).click();
    await page.getByRole("list", { name: "Bookings" }).getByText("confirmed", { exact: true }).waitFor();
  });

  await step("Bookings → Hours & slots opens", page, async () => {
    await tab("Hours & slots").click();
    await page.getByRole("heading", { level: 2 }).first().waitFor();
  });

  // -------------------------------------------------------------- retention
  await step("every Retention tab opens without an error", page, async () => {
    await nav("Retention").click();
    for (const name of ["Segments", "Campaign rules", "Approval queue", "Results"]) {
      await tab(name).click();
      await page.waitForTimeout(300);
      if (await page.getByRole("alert").count()) throw new Error(`${name} shows an error alert`);
    }
  });

  // ------------------------------------------------------------ the chatbot
  await nav("WhatsApp Bot").click();
  await step("create an offer", page, async () => {
    const form = page.getByRole("form", { name: "Offer form" });
    await form.getByLabel("Title").fill("Happy hour");
    await form.getByLabel("Discount (%)").fill("15");
    await form.getByRole("button", { name: "Add offer" }).click();
    await page.getByRole("list", { name: "Offers" }).getByText("Happy hour", { exact: true }).waitFor();
    await page.getByRole("list", { name: "Offers" }).getByText("active", { exact: true }).waitFor();
  });

  await step("test chat answers (no OpenAI key, so the polite fallback with owner contact)", page, async () => {
    await tab("Test chat").click();
    const chat = page.getByLabel("Test chat");
    await chat.getByLabel("Message").fill("Is there space for 2?");
    await chat.getByRole("button", { name: "Send" }).click();
    await chat.getByText(/Sorry, I can't answer that right now/).waitFor();
    await chat.getByText(OWNER_CONTACT).waitFor();
    await chat.getByText(/asked for a person/).waitFor();
  });

  await step("the conversation appears flagged as needing a person", page, async () => {
    await tab("Conversations").click();
    await page.getByRole("list", { name: "Conversations" }).getByText("Needs a person").waitFor();
  });

  // ---------------------------------------------------------------- webhook
  const token = await page.evaluate(() => localStorage.getItem("rms_token"));
  const post = (body, secret = WEBHOOK_SECRET) =>
    fetch(`${API}/api/messaging/inbound`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(secret ? { "X-Webhook-Secret": secret } : {}) },
      body: JSON.stringify(body),
    });
  await step("webhook: wrong secret refused, STOP opts the guest out", page, async () => {
    if ((await post({ phone: "9810000001", text: "hi" }, "wrong")).status !== 401) throw new Error("wrong secret was accepted");
    const stop = await (await post({ phone: "9810000001", text: "STOP" })).json();
    if (stop.action !== "opted_out") throw new Error(`STOP gave ${JSON.stringify(stop)}`);
    const list = await (await fetch(`${API}/api/customers`, { headers: { Authorization: `Bearer ${token}` } })).json();
    if (!list.find((c) => c.phone === "9810000001")?.marketing_opt_out) throw new Error("customer was not opted out");
  });
  await step("webhook: a normal message gets a bot reply", page, async () => {
    const reply = await (await post({ phone: "9810000003", text: "hello" })).json();
    if (reply.action !== "replied") throw new Error(`got ${JSON.stringify(reply)}`);
  });

  // ------------------------------------------------------------ permissions
  await step("sign out and sign in as the waiter", page, async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("heading", { name: "Sign in" }).waitFor();
    await page.getByLabel("Email").fill("waiter@dilli.test");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByText("Ravi Waiter · waiter").waitFor();
  });
  await step("waiter sees only Orders in Billing", page, async () => {
    await nav("Billing").click();
    await tab("Orders").waitFor();
    for (const hidden of ["Menu & tables", "Customers", "Insights", "Reports"]) {
      if (await tab(hidden).count()) throw new Error(`waiter can see the "${hidden}" tab`);
    }
  });
  await step("waiter is blocked from the bot page and from staff settings", page, async () => {
    await nav("WhatsApp Bot").click();
    await page.getByText(/Only owners and managers/).waitFor();
    await nav("Settings").click();
    await page.getByRole("heading", { name: "Settings" }).waitFor();
    if (await page.getByRole("region", { name: "Staff" }).count()) throw new Error("waiter can see Staff");
    if (await page.getByRole("form", { name: "Receipt details" }).count()) throw new Error("waiter can edit receipt details");
  });

  await browser.close();

  const failed = results.filter((r) => r[0] === "FAIL");
  for (const r of results) console.log(`${r[0]}  ${r[1]}${r[2] ? `\n        -> ${r[2]}` : ""}`);
  console.log(`\n${results.length - failed.length}/${results.length} steps passed`);
  const unexpected = browserErrors.filter((e) => !/http 40[14] /.test(e) && !/status of 40[14]/.test(e));
  console.log(`browser errors (excluding expected 401/404): ${unexpected.length}`);
  unexpected.slice(0, 15).forEach((e) => console.log("   ", e));
  process.exit(failed.length ? 1 : 0);
})();
