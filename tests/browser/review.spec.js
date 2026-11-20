const {test, expect} = require("@playwright/test");
const {AxeBuilder} = require("@axe-core/playwright");
const fs = require("node:fs");

const csvRows = fs.readFileSync("reports/metrics.csv", "utf8").trim().split(/\r?\n/);
const columns = csvRows.shift().split(",");
const metrics = csvRows.map(line => Object.fromEntries(line.split(",").map((value, i) => [columns[i], value])));

test("all-market totals come from the SQL export and scope is visible", async ({page}) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What is driving yield?"})).toBeVisible();
  await expect(page.getByText("Synthetic data", {exact: true})).toBeVisible();
  const current = metrics.find(row => row.period === "current" && row.market === "*" && row.device === "*" && row.ad_unit === "*");
  await expect(page.locator("#cards .value").first()).toHaveText(Number(current.requests).toLocaleString("en-US"));
  await expect(page.locator("#market-rows tr")).toHaveCount(4);
  expect(errors).toEqual([]);
});

test("market and device selection use the correct SQL rollup, including percentile", async ({page}) => {
  await page.goto("/");
  await page.getByLabel("Market", {exact: true}).selectOption("IN");
  await page.getByLabel("Device", {exact: true}).selectOption("mobile");
  const row = metrics.find(row => row.period === "current" && row.market === "IN" && row.device === "mobile" && row.ad_unit === "*");
  await expect(page.locator("#cards .value").first()).toHaveText(Number(row.requests).toLocaleString("en-US"));
  await expect(page.locator("#cards .value").last()).toHaveText(`${Math.round(row.p95_render_ms).toLocaleString("en-US")} ms`);
  await expect(page.locator("#market-rows tr")).toHaveCount(1);
  await expect(page).toHaveURL(/market=IN&device=mobile/);
});

test("selection is shareable and reset restores the full review", async ({page}) => {
  await page.goto("/?market=BR&device=desktop&ad_unit=footer");
  await expect(page.getByLabel("Market", {exact: true})).toHaveValue("BR");
  await expect(page.getByLabel("Ad unit", {exact: true})).toHaveValue("footer");
  await page.getByRole("button", {name: "Reset", exact: true}).click();
  await expect(page.getByLabel("Market", {exact: true})).toHaveValue("*");
  await expect(page.locator("#market-rows tr")).toHaveCount(4);
  await expect(page).toHaveURL("http://127.0.0.1:8587/");
});

test("CSV export contains exactly the selected baseline/current rows", async ({page}) => {
  await page.goto("/?market=GB&device=mobile");
  const pending = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export selection"}).click();
  const download = await pending;
  const text = fs.readFileSync(await download.path(), "utf8");
  const rows = text.split(/\r?\n/).filter(Boolean);
  expect(rows).toHaveLength(3);
  expect(rows[1]).toContain(",GB,mobile,*,");
  expect(rows[2]).toContain(",GB,mobile,*,");
});

test("mix reading identifies the reversal without a causal claim", async ({page}) => {
  await page.goto("/");
  await expect(page.locator("#mix-reading")).toContainText("headline increase masks");
  await page.getByText("How to read this", {exact: true}).click();
  await expect(page.getByText(/No causal effect is inferred/)).toBeVisible();
});

test("filters are keyboard accessible and the review has no serious accessibility findings", async ({page}) => {
  await page.goto("/");
  await page.getByLabel("Market", {exact: true}).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Device", {exact: true})).toBeFocused();
  const report = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(report.violations.filter(v => ["critical", "serious"].includes(v.impact))).toEqual([]);
});

test("mobile layout keeps the document in the viewport", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");
  await page.getByLabel("Market", {exact: true}).selectOption("IN");
  await expect(page.getByRole("button", {name: "Export selection"})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
