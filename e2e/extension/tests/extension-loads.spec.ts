// e2e/extension/tests/extension-loads.spec.ts
import { test, expect } from '../fixtures';

test('unpacked extension loads and registers a service worker', async ({ serviceWorker }) => {
  expect(serviceWorker.url()).toMatch(/^chrome-extension:\/\/[a-p]{32}\//);
});
