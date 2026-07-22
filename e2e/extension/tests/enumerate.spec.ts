import { test, expect } from '../fixtures';
import path from 'path';

const ENUM_JS = path.resolve(__dirname, '../../../browser-extension/content/form_enumerate.js');

async function enumerate(context: any, html: string) {
  const page = await context.newPage();
  await page.setContent(`<!doctype html><html><body><form>${html}</form></body></html>`);
  await page.addScriptTag({ path: ENUM_JS });
  const fields = await page.evaluate(() => (globalThis as any).enumerateForm());
  await page.close();
  return fields as Array<any>;
}

test('types a role=combobox control as combobox, not text', async ({ context }) => {
  const fields = await enumerate(context, `
    <label for="country">Country*</label>
    <input id="country" type="text" role="combobox" aria-autocomplete="list" aria-required="true" />
  `);
  const country = fields.find((f) => f.field_id === 'country');
  expect(country.input_type).toBe('combobox');
  expect(country.required).toBe(true);      // from aria-required, not el.required
  expect(country.label).toBe('Country');     // trailing '*' stripped
});

test('derives required from a trailing asterisk when no aria-required', async ({ context }) => {
  const fields = await enumerate(context, `
    <label for="fn">First Name*</label>
    <input id="fn" type="text" />
  `);
  expect(fields[0].required).toBe(true);
  expect(fields[0].label).toBe('First Name');
});

test('passes native selects through as select with options', async ({ context }) => {
  const fields = await enumerate(context, `
    <label for="src">How did you hear about us?</label>
    <select id="src"><option>LinkedIn</option><option>Referral</option></select>
  `);
  expect(fields[0].input_type).toBe('select');
  expect(fields[0].options).toEqual(['LinkedIn', 'Referral']);
});

test('drops the anonymous partner input a combobox pairs with', async ({ context }) => {
  // Greenhouse renders a visible role=combobox input plus a second nameless/idless
  // input in the same container. Only the combobox should be enumerated.
  // The partner carries a stray whitespace aria-label so it defeats the plain
  // `!id` guard (a truly bare <input> would already be dropped by that guard,
  // which would make this test pass for the wrong reason).
  const fields = await enumerate(context, `
    <div>
      <label for="country">Country*</label>
      <input id="country" type="text" role="combobox" aria-autocomplete="list" />
      <input type="text" aria-label=" " />
    </div>
  `);
  expect(fields).toHaveLength(1);
  expect(fields[0].field_id).toBe('country');
});
