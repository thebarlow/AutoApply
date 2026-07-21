import { test, expect } from '@playwright/test';

/** Public marketing/landing page at /about — renders without any auth. */
test('landing page renders', async ({ page }) => {
  await page.goto('/about');
  await expect(page.getByText('Auto Apply').first()).toBeVisible();
  await page.screenshot({ path: 'screenshots/landing.png', fullPage: true });
});
