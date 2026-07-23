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

const MIXED = `
  <form>
    <label for="email">Email</label>
    <input id="email" name="email" type="text" value="" />
    <label for="src">Source</label>
    <select id="src" name="src"><option value="">--</option><option>Referral</option></select>
    <div class="select__control">
      <div class="select__value"></div>
      <input id="country" role="combobox" aria-autocomplete="list" type="text" value="" />
      <div class="select__menu" hidden></div>
    </div>
    <script>
      (function () {
        var input = document.getElementById('country');
        var box = document.querySelector('.select__value');
        var menu = document.querySelector('.select__menu');
        input.addEventListener('input', function () {
          var q = input.value.trim().toLowerCase();
          menu.innerHTML = ''; menu.hidden = !q;
          if (!q) return;
          ['Canada','Germany'].filter(function (o) { return o.toLowerCase().indexOf(q) === 0; })
            .forEach(function (o) {
              var d = document.createElement('div');
              d.setAttribute('role','option'); d.textContent = o;
              d.addEventListener('mousedown', function (e) {
                e.preventDefault();
                var sv = document.createElement('div');
                sv.className = 'select__singleValue'; sv.textContent = o;
                box.innerHTML = ''; box.appendChild(sv);
                input.value = ''; menu.hidden = true;
              });
              menu.appendChild(d);
            });
        });
      })();
    </script>
  </form>`;

async function loadMixed(context: any) {
  const page = await context.newPage();
  await page.setContent(`<!doctype html><html><body>${MIXED}</body></html>`);
  await page.addScriptTag({ path: FILL_JS });
  return page;
}

test('fillForm fills text + select + combobox and reports per-field status', async ({ context }) => {
  const page = await loadMixed(context);
  const report = await page.evaluate(async () => {
    return await (globalThis as any).fillForm([
      { field_id: 'email', input_type: 'text', status: 'filled', value: 'a@b.com' },
      { field_id: 'src', input_type: 'select', status: 'filled', value: 'Referral' },
      { field_id: 'country', input_type: 'combobox', status: 'filled', value: 'Canada' },
    ]);
  });
  expect(report.filled).toBe(3);
  const byId = Object.fromEntries(report.results.map((r: any) => [r.field_id, r.status]));
  expect(byId).toEqual({ email: 'filled', src: 'filled', country: 'filled' });
  await page.close();
});

test('fillForm reports uncommitted for an unmatched combobox and never leaves stray text', async ({ context }) => {
  const page = await loadMixed(context);
  const report = await page.evaluate(async () => {
    return await (globalThis as any).fillForm([
      { field_id: 'country', input_type: 'combobox', status: 'filled', value: 'Atlantis' },
    ]);
  });
  expect(report.results[0].status).toBe('uncommitted');
  expect(report.filled).toBe(0);
  expect(await page.locator('#country').inputValue()).toBe('');
  await page.close();
});

test('fillForm skips non-filled/empty statuses (EEO invariant) and reports not_found', async ({ context }) => {
  const page = await loadMixed(context);
  const report = await page.evaluate(async () => {
    return await (globalThis as any).fillForm([
      { field_id: 'ethnicity', input_type: 'multiselect', status: 'unknown', value: '' },
      { field_id: 'email', input_type: 'text', status: 'filled', value: '' },
      { field_id: 'nope', input_type: 'text', status: 'filled', value: 'x' },
    ]);
  });
  const byId = Object.fromEntries(report.results.map((r: any) => [r.field_id, r.status]));
  expect(byId.ethnicity).toBe('skipped');
  expect(byId.email).toBe('skipped');   // empty value → never typed
  expect(byId.nope).toBe('not_found');
  await expect(page.locator('#country')).toHaveValue('');  // EEO/absent fields never touched it
  await page.close();
});
