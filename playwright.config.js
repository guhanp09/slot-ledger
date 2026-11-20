const {defineConfig} = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/browser",
  timeout: 15000,
  use: {baseURL: "http://127.0.0.1:8587", headless: true, browserName: "chromium",
    actionTimeout: 5000, channel: process.env.SLOT_LEDGER_BROWSER || undefined},
  webServer: {
    command: "python3 -m http.server 8587 --bind 127.0.0.1 --directory reports",
    url: "http://127.0.0.1:8587", reuseExistingServer: false,
  },
  reporter: "list",
});
