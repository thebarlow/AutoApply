// e2e/extension/playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { trace: 'retain-on-failure' },
  // Boot (or reuse) the backend only — the extension talks to the API directly;
  // no Vite needed. Fixtures are served via route interception in the specs.
  webServer: [
    {
      command: '.venv/Scripts/python.exe -m uvicorn web.main:app --port 8080',
      cwd: '../..',
      url: 'http://localhost:8080/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
