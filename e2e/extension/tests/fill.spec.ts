import { test, expect } from '../fixtures';
import path from 'path';
import fs from 'fs';

const FILL_JS = path.resolve(__dirname, '../../../browser-extension/content/form_fill.js');
const COMBOBOX_FIXTURE = fs.readFileSync(
  path.resolve(__dirname, '../fixtures/combobox.html'), 'utf-8');

async function loadCombobox(context: any) {
  const page = await context.newPage();
  await page.setContent(COMBOBOX_FIXTURE);
  await page.addScriptTag({ path: FILL_JS });
  return page;
}

test('_commitCombobox commits a matching option via mousedown and verifies it', async ({ context }) => {
  const page = await loadCombobox(context);
  const ok = await page.evaluate(async () => {
    const el = document.getElementById('country');
    return await (globalThis as any)._commitCombobox(el, 'Canada');
  });
  expect(ok).toBe(true);
  await expect(page.locator('.select__value [class*="singleValue"]')).toHaveText('Canada');
  await page.close();
});

test('_commitCombobox clears the field and returns false when no option matches', async ({ context }) => {
  const page = await loadCombobox(context);
  const ok = await page.evaluate(async () => {
    const el = document.getElementById('country');
    return await (globalThis as any)._commitCombobox(el, 'Atlantis');
  });
  expect(ok).toBe(false);
  // No committed single-value node, and the typed text is wiped.
  await expect(page.locator('.select__value [class*="singleValue"]')).toHaveCount(0);
  expect(await page.locator('#country').inputValue()).toBe('');
  await page.close();
});
