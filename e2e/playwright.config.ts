import { defineConfig, devices } from '@playwright/test';

/**
 * Smoke + live-drive harness for the auto-apply dashboard.
 *
 * Boots the full local stack (uvicorn :8080 + Vite :5173) and drives the SPA at
 * the Vite origin, which proxies /api and /auth to the backend. The app runs
 * open locally — the auth gate only activates when APP_ENV=production — so no
 * OAuth is needed. Both webServers reuse an already-running dev stack, so
 * `start.bat dev` in another window is picked up instead of double-booting.
 */
export default defineConfig({
  testDir: './tests',
  // Smoke checks hit shared local dev state; run serially to keep them readable.
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  // Log in once via the gated dev-login endpoint; specs reuse the session.
  globalSetup: './global-setup.ts',
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'storageState.json',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      // Run from repo root; use the project's venv interpreter.
      command: '.venv/Scripts/python.exe -m uvicorn web.main:app --port 8080',
      cwd: '..',
      url: 'http://localhost:8080/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      cwd: '../react-dashboard',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
