# Combobox Fill-Commit + Honest Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the extension's autofill writer actually commit react-select combobox selections on Greenhouse, and return an honest per-field report instead of silently claiming every field "filled."

**Architecture:** `fillForm` in `browser-extension/content/form_fill.js` becomes async. Combobox fields route to a new `_commitCombobox` that focuses, types, polls for a matching `[role="option"]`, commits on `mousedown`, and verifies the rendered `singleValue`; on failure `_clearCombobox` wipes the field. `fillForm` returns `{ filled, results[] }`; `injector.js` awaits it and logs a truthful summary. Tests use the existing Playwright extension harness with a hand-rolled minimal react-select fixture (ARIA-contract faithful, no real react-select, no backend).

**Tech Stack:** MV3 content scripts (no module system — page-context function globals), Playwright (`@playwright/test`) extension harness in `e2e/extension/`.

## Global Constraints

- No module system: new functions are plain page-context `function` declarations in `form_fill.js`, same convention as `form_enumerate.js`. No `import`/`export`.
- **EEO/demographic fields are never typed into a combobox.** They arrive with a non-`filled`/`drafted` plan status (or empty value) and MUST land in `status: "skipped"`. This invariant is locked by a test.
- Anchor on the stable ARIA contract, never emotion hash classes: `[role="option"]`, `[role="listbox"]`, committed value read from `[class*="singleValue"]` (fallback `[class*="single-value"]`).
- react-select commits a choice on an option's **`mousedown`** (not `click`).
- Text / `<select>` / checkbox / radio fill behavior stays byte-for-byte equivalent (regression-guarded).
- Verify commit by **equality** of normalized text (trim → collapse whitespace → case-fold), never "non-empty", so a pre-existing selection can't be misread as our commit.
- `status` enum is exactly: `filled` | `uncommitted` | `failed` | `skipped` | `not_found`. `filled` (the number) = count of `status === "filled"`.
- Scope: Greenhouse react-select single-select only. Lever/Ashby commit, option harvesting, and multi-select are out of scope; `multiselect` inputs route to `skipped`.
- Commit messages: `[type] Imperative subject`; no Claude/Anthropic attribution.

---

### Task 1: Combobox commit + clear helpers

**Files:**
- Modify: `browser-extension/content/form_fill.js` (add two functions; do not yet change `fillForm`)
- Create: `e2e/extension/fixtures/combobox.html`
- Create: `e2e/extension/tests/fill.spec.ts`

**Interfaces:**
- Consumes: existing `_setNativeValue(el, value)` in `form_fill.js`.
- Produces:
  - `async _commitCombobox(el, value) -> Promise<boolean>` — focuses `el`, types `value`, polls for a matching option, commits on `mousedown`, verifies the rendered single-value equals the option; returns `true` only on verified commit, else calls `_clearCombobox(el)` and returns `false`.
  - `_clearCombobox(el) -> void` — Escape keydown/keyup, reset value to `""` via native setter + `input`, blur.
  - `_normText(s) -> string` — trim → collapse internal whitespace → lowercase (shared normalizer).

- [ ] **Step 1: Write the combobox test fixture**

Create `e2e/extension/fixtures/combobox.html`. A minimal, deterministic reproduction of the react-select *contract* the commit depends on — NOT real react-select. On `input`, it renders a `[role="listbox"]` of matching `[role="option"]`s; on an option's `mousedown` it sets the committed value and renders a `singleValue` node; Escape / blur closes the menu.

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>combobox fixture</title></head>
<body>
  <form>
    <!--
      Faithful to the Greenhouse react-select ARIA contract (see
      docs/superpowers/specs/2026-07-22-combobox-fill-commit-design.md §2):
      a role=combobox input whose menu commits on an option's MOUSEDOWN and
      renders the choice as a *__singleValue node in the control. Deliberately
      NOT real react-select (version-coupled + slow); the interaction contract
      is what the commit logic verifies.
    -->
    <div class="select__control" data-field="country">
      <div class="select__value"><!-- singleValue injected here on commit --></div>
      <input id="country" role="combobox" aria-autocomplete="list" aria-expanded="false" type="text" value="" autocomplete="off" />
      <div class="select__menu" hidden></div>
    </div>
  </form>
  <script>
    (function () {
      const OPTIONS = ['United States', 'United Kingdom', 'Canada', 'Germany'];
      const control = document.querySelector('.select__control');
      const input = document.getElementById('country');
      const valueBox = control.querySelector('.select__value');
      const menu = control.querySelector('.select__menu');

      function renderMenu() {
        const q = input.value.trim().toLowerCase();
        menu.innerHTML = '';
        if (!q) { menu.hidden = true; input.setAttribute('aria-expanded', 'false'); return; }
        const matches = OPTIONS.filter((o) => o.toLowerCase().includes(q));
        const list = document.createElement('div');
        list.setAttribute('role', 'listbox');
        for (const o of matches) {
          const opt = document.createElement('div');
          opt.setAttribute('role', 'option');
          opt.textContent = o;
          // react-select commits on mousedown, not click.
          opt.addEventListener('mousedown', function (e) {
            e.preventDefault();
            const sv = document.createElement('div');
            sv.className = 'select__single-value select__singleValue';
            sv.textContent = o;
            valueBox.innerHTML = '';
            valueBox.appendChild(sv);
            input.value = '';
            menu.hidden = true;
            input.setAttribute('aria-expanded', 'false');
          });
          list.appendChild(opt);
        }
        menu.innerHTML = '';
        menu.appendChild(list);
        menu.hidden = matches.length === 0;
        input.setAttribute('aria-expanded', matches.length ? 'true' : 'false');
      }

      input.addEventListener('input', renderMenu);
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { menu.hidden = true; input.setAttribute('aria-expanded', 'false'); }
      });
    })();
  </script>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests for `_commitCombobox`**

Create `e2e/extension/tests/fill.spec.ts`. This task adds only the two commit/clear cases; Task 2 appends the `fillForm`-level cases.

```ts
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd e2e/extension && npx playwright test tests/fill.spec.ts`
Expected: FAIL — `_commitCombobox is not a function`.

- [ ] **Step 4: Implement `_normText`, `_commitCombobox`, `_clearCombobox`**

Append to `browser-extension/content/form_fill.js` (after `_fire`):

```js
// Normalize option/value text for matching + commit verification: trim,
// collapse internal whitespace, case-fold. Equality on this (not "non-empty")
// keeps a pre-existing selection from being misread as our commit.
function _normText(s) {
  return (s || "").replace(/\s+/g, " ").trim().toLowerCase();
}

// Commit a plan value into a react-select-style combobox (Greenhouse). Types
// the value to open/filter the menu, polls for a matching [role="option"],
// commits on mousedown, and verifies the rendered single-value equals the
// option. Resolves true only on a verified commit; otherwise clears the field
// and resolves false. Anchors on the stable ARIA contract, not emotion hashes.
async function _commitCombobox(el, value) {
  const want = _normText(value);
  if (!want) return false;
  el.focus();
  _setNativeValue(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));

  const deadline = Date.now() + 1500;
  let target = null;
  while (Date.now() < deadline) {
    const opts = [...document.querySelectorAll('[role="option"]')];
    const exact = opts.find((o) => _normText(o.textContent) === want);
    if (exact) { target = exact; break; }
    const starts = opts.filter((o) => _normText(o.textContent).startsWith(want));
    if (starts.length === 1) { target = starts[0]; break; }
    await new Promise((r) => setTimeout(r, 60));
  }
  if (!target) { _clearCombobox(el); return false; }

  const committed = _normText(target.textContent);
  for (const type of ["mousedown", "mouseup", "click"]) {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true }));
  }

  const container = el.closest('[class*="control"], [class*="select"]') || el.parentElement;
  const sv =
    (container && container.querySelector('[class*="singleValue"], [class*="single-value"]')) || null;
  if (sv && _normText(sv.textContent) === committed) return true;
  _clearCombobox(el);
  return false;
}

// Reset a combobox to empty so nothing looks half-filled: Escape (close menu),
// wipe the input via the native setter + input, blur. react-select discards
// unselected text on blur; the explicit reset guarantees it across variants.
function _clearCombobox(el) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
  _setNativeValue(el, "");
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.blur();
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd e2e/extension && npx playwright test tests/fill.spec.ts`
Expected: PASS (2 passed). Requires a headed run (MV3 persistent context); no backend needed.

- [ ] **Step 6: Commit**

```bash
git add browser-extension/content/form_fill.js e2e/extension/fixtures/combobox.html e2e/extension/tests/fill.spec.ts
git commit -m "[feat] Commit react-select combobox selections in form_fill"
```

---

### Task 2: Async `fillForm` with per-field report + routing

**Files:**
- Modify: `browser-extension/content/form_fill.js:5-20` (rewrite `fillForm`; add a routing branch in the write path)
- Modify: `e2e/extension/tests/fill.spec.ts` (append `fillForm`-level cases)

**Interfaces:**
- Consumes: `_commitCombobox` / `_clearCombobox` (Task 1), existing `_findControl`, `_writeValue`.
- Produces: `async fillForm(plannedFields) -> Promise<{ filled: number, results: Array<{ field_id, input_type, status }> }>`. Sole caller is `injector.js` (Task 3), which awaits it.

- [ ] **Step 1: Write the failing `fillForm` tests**

Append to `e2e/extension/tests/fill.spec.ts`. These load a combined fixture inline (text + select + combobox) so one page exercises every route.

```ts
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
```

- [ ] **Step 2: Run to verify the new cases fail**

Run: `cd e2e/extension && npx playwright test tests/fill.spec.ts`
Expected: FAIL — `report.results` is undefined (current `fillForm` returns only `{ filled }`) and it is not async-aware for the combobox.

- [ ] **Step 3: Rewrite `fillForm` and add the combobox route**

Replace `fillForm` (`form_fill.js:5-20`) with:

```js
async function fillForm(plannedFields) {
  if (!Array.isArray(plannedFields)) return { filled: 0, results: [] };
  const results = [];
  let filled = 0;
  for (const f of plannedFields) {
    if (!f) continue;
    const entry = { field_id: (f && f.field_id) || "", input_type: (f && f.input_type) || "", status: "skipped" };
    results.push(entry);
    if ((f.status !== "filled" && f.status !== "drafted") || f.value == null || f.value === "") {
      continue; // skipped — includes every EEO field (non-filled status / empty value)
    }
    const el = _findControl(f.field_id);
    if (!el) { entry.status = "not_found"; continue; }
    try {
      const status = await _writeField(el, f);
      entry.status = status;
      if (status === "filled") filled++;
    } catch (_) {
      // One bad control (e.g. a file input throwing on programmatic .value
      // assignment) shouldn't strand every remaining field.
      entry.status = "failed";
    }
  }
  return { filled, results };
}

// Route a single field to the right writer and return its status. Comboboxes
// are genuinely async (poll + commit); everything else resolves synchronously.
async function _writeField(el, f) {
  const role = (el.getAttribute("role") || "").toLowerCase();
  const isCombo = role === "combobox" || el.hasAttribute("aria-autocomplete");
  const multi = el.getAttribute("aria-multiselectable") === "true" || f.input_type === "multiselect";
  if (isCombo || f.input_type === "combobox") {
    if (multi) return "skipped"; // multi-select combobox (EEO) is never partially committed
    return (await _commitCombobox(el, f.value)) ? "filled" : "uncommitted";
  }
  return _writeValue(el, f.value) ? "filled" : "failed";
}
```

Leave `_writeValue`, `_findControl`, `_setNativeValue`, `_fire` unchanged.

- [ ] **Step 4: Run the full fill spec to verify it passes**

Run: `cd e2e/extension && npx playwright test tests/fill.spec.ts`
Expected: PASS (5 passed — 2 from Task 1, 3 here).

- [ ] **Step 5: Commit**

```bash
git add browser-extension/content/form_fill.js e2e/extension/tests/fill.spec.ts
git commit -m "[feat] Return honest per-field fill report from fillForm"
```

---

### Task 3: Await `fillForm` in the injector + honest summary log

**Files:**
- Modify: `browser-extension/content/injector.js:282-284`

**Interfaces:**
- Consumes: `async fillForm(...) -> { filled, results }` (Task 2).
- Produces: no new interface; the injector now awaits the report and logs a truthful committed/total summary within the existing try/catch.

- [ ] **Step 1: Replace the fire-and-forget fill call**

At `injector.js:282-284`, replace:

```js
    if (Array.isArray(result.fields) && typeof fillForm === "function") {
      fillForm(result.fields);
    }
```

with:

```js
    if (Array.isArray(result.fields) && typeof fillForm === "function") {
      const report = await fillForm(result.fields);
      const notFilled = report.results.filter((r) => r.status !== "filled");
      console.info(
        `${_AP_LOG} fill: ${report.filled}/${report.results.length} committed`,
        notFilled.length ? notFilled : "(all filled)"
      );
    }
```

The enclosing function is already `async` (it `await`s `_msg` above), and all of this remains inside the existing try/catch so a writer error never blocks page interaction.

- [ ] **Step 2: Verify no other caller of `fillForm` exists**

Run: `cd browser-extension && grep -rn "fillForm" content/ background* *.js 2>/dev/null`
Expected: only the definition in `content/form_fill.js` and the single awaited call in `content/injector.js`. If another call appears, it must be awaited too (report the finding rather than silently leaving a sync call).

- [ ] **Step 3: Run the full extension suite (regression)**

Requires the local stack on `:8080` (the autofill spec seeds via `/api/dev/*`). Boot it if needed (`start.bat`), then:

Run: `cd e2e/extension && npm test`
Expected: PASS — `fill.spec.ts` (5), `autofill.spec.ts` (3), `enumerate.spec.ts`, `extension-loads.spec.ts`. The autofill spec's Greenhouse fixture is text-only, so awaiting `fillForm` must not regress it (email still fills).

- [ ] **Step 4: Commit**

```bash
git add browser-extension/content/injector.js
git commit -m "[feat] Await fillForm and log an honest fill summary in injector"
```

---

## Self-Review

**Spec coverage** (spec §4 → tasks):
- §4.1 async writer → Task 2 Step 3.
- §4.2 routing (combobox / multiselect-skip / else) → Task 2 `_writeField`.
- §4.3 `_commitCombobox` (focus→type→poll exact/unique-startsWith→mousedown/up/click→verify equals→clear on fail) → Task 1 Step 4.
- §4.4 `_clearCombobox` (Escape + reset "" + blur) → Task 1 Step 4.
- §4.5 report `{ filled, results:[{field_id,input_type,status}] }`, all 5 statuses, EEO→skipped → Task 2 Step 3 + tests.
- §4.6 injector `await fillForm` + summary log → Task 3.
- §4.7 resilience (equality verify, ARIA anchors) → enforced in `_commitCombobox`; Global Constraints.
- §6 testing (hand-rolled fixture + 5 fill cases + full-suite regression) → Tasks 1–3 tests.

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `_commitCombobox`/`_clearCombobox`/`_normText`/`_writeField`/`fillForm` signatures match across Tasks 1–3 and the spec §5. Status strings match the enum verbatim.

**Note on scope discipline (for the executor):** a doc-sync PostToolUse hook may fire on these commits and try to pull `browser-extension/CONTEXT.md` / `.claude/TODO.md` into scope. Decline it — CONTEXT/TODO were already updated deliberately in the enumeration sub-project; a dedicated doc pass (not these code commits) owns any further doc sync.
