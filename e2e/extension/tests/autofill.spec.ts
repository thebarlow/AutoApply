import { test, expect } from '../fixtures';
import { request } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const APPLY_URL = 'https://boards.greenhouse.io/acme/jobs/123';
const JOB_KEY = 'e2e-ats-fixture-greenhouse';

test('extension autofills the greenhouse fixture from the plan', async ({ context, serviceWorker }) => {
  // 1. Seed backend: log in (dev) + create the staged job on that profile.
  const api = await request.newContext({ baseURL: 'http://localhost:8080' });
  const login = await api.post('/api/dev/login');
  const { profile_id } = await login.json();

  // The dev-login profile's User row may have no first/last/email seeded yet
  // (fresh local DB) — the plan resolver reads these deterministically off the
  // profile, so the form has nothing to fill without them.
  await api.put(`/api/config/profiles/${profile_id}`, {
    data: {
      name: 'E2E Fixture',
      data: {
        first_name: 'E2E',
        last_name: 'Fixture',
        email: 'e2e-fixture@example.com',
      },
    },
  });

  const seed = await api.post('/api/dev/seed-ats-job', {
    data: { job_key: JOB_KEY, apply_url: APPLY_URL, ats_type: 'greenhouse' },
  });
  expect(seed.ok()).toBeTruthy();

  // 2. Seed extension storage so the SW targets localhost + matches the job by URL.
  await serviceWorker.evaluate(({ jobKey, url }) => {
    return chrome.storage.local.set({
      serverMode: 'local',
      stagedJobMeta: { [jobKey]: { apply_url_raw: url, apply_url_resolved: url } },
    });
  }, { jobKey: JOB_KEY, url: APPLY_URL });

  // 3. Route the real ATS URL to the local fixture so content scripts inject.
  const page = await context.newPage();
  const fixture = fs.readFileSync(path.resolve(__dirname, '../fixtures/greenhouse.html'), 'utf-8');
  await context.route('https://boards.greenhouse.io/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: fixture }));

  await page.goto(APPLY_URL);
  await fs.promises.mkdir(path.resolve(__dirname, '../screenshots'), { recursive: true });
  await page.screenshot({ path: path.resolve(__dirname, '../screenshots/greenhouse-before.png') });

  // 4. Wait for the extension to enumerate → fetch plan → fill.
  const email = page.locator('#email');
  await expect(email).not.toHaveValue('', { timeout: 15_000 });

  await page.screenshot({ path: path.resolve(__dirname, '../screenshots/greenhouse-after.png') });

  // The seeded local profile's real email should land in the field.
  expect((await email.inputValue()).length).toBeGreaterThan(0);
});
