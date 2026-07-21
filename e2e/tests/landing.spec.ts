import { test, expect } from '@playwright/test';

/** Public marketing/landing page at /about — renders without any auth. */
test('landing page renders', async ({ page }) => {
  // NB: don't wait for 'networkidle' — Vite's HMR websocket keeps the network
  // busy in dev, so it never fires. Wait on the actual content instead.
  await page.goto('/about');
  await expect(page.getByText('Auto Apply').first()).toBeVisible();

  // The landing hero and sections fade/slide in on load and on scroll. Capturing
  // immediately catches them mid-transition (faded text, unrendered art), so:
  //  1. scroll the whole page to trigger any scroll-linked / lazy animations,
  //  2. return to top,
  //  3. wait for CSS animations+transitions to actually finish (not a blind sleep).
  await page.evaluate(async () => {
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const step = window.innerHeight;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await sleep(150);
    }
    window.scrollTo(0, 0);
  });
  // Resolve once every running animation/transition has settled.
  await page.evaluate(() =>
    Promise.all(
      document.getAnimations().map((a) => a.finished.catch(() => {})),
    ),
  );
  await page.waitForTimeout(400); // final paint settle

  await page.screenshot({ path: 'screenshots/landing.png', fullPage: true });
});
