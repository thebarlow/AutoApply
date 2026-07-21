import { test, expect } from '@playwright/test';

/** Find Jobs page — search UI presence only; does not run a real scrape. */
test('find jobs page renders search controls', async ({ page }) => {
  await page.goto('/find-jobs');

  await expect(page.getByPlaceholder('Search remote jobs…')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Search' })).toBeEnabled();

  await page.screenshot({ path: 'screenshots/find-jobs.png', fullPage: true });
});
