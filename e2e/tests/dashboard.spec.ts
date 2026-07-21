import { test, expect } from '@playwright/test';

/**
 * Main dashboard smoke. Requires a local profile so `me` is non-null; otherwise
 * the SPA redirects to /about. Assertions stay at presence/visibility level and
 * avoid destructive controls (no delete / mark-applied / generate).
 */
test('dashboard loads with working nav', async ({ page }) => {
  await page.goto('/');

  // Brand and top-nav links from Navbar.jsx.
  await expect(page.getByText('Auto Apply').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Find Jobs' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'About' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Help' })).toBeVisible();

  await page.screenshot({ path: 'screenshots/dashboard.png', fullPage: true });
});

test('nav: Find Jobs link routes to /find-jobs', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Find Jobs' }).click();
  await expect(page).toHaveURL(/\/find-jobs$/);
});
