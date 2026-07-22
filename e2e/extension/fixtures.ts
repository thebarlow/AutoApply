// e2e/extension/fixtures.ts
import { test as base, chromium, type BrowserContext, type Worker } from '@playwright/test';
import path from 'path';

const pathToExtension = path.resolve(__dirname, '../../browser-extension');

export const test = base.extend<{ context: BrowserContext; serviceWorker: Worker }>({
  context: async ({}, use) => {
    const context = await chromium.launchPersistentContext('', {
      headless: false, // MV3 extensions require a headed/persistent context
      args: [
        `--disable-extensions-except=${pathToExtension}`,
        `--load-extension=${pathToExtension}`,
      ],
    });
    await use(context);
    await context.close();
  },
  serviceWorker: async ({ context }, use) => {
    let [sw] = context.serviceWorkers();
    if (!sw) sw = await context.waitForEvent('serviceworker');
    await use(sw);
  },
});

export const expect = test.expect;
