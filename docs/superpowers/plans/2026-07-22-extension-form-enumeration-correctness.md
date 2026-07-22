# Extension Form-Enumeration Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser extension read live application forms correctly — logical field types (comboboxes, groups), ARIA-aware requiredness, de-noised labels — and close the EEO-guard gap that let a demographic question reach the LLM.

**Architecture:** Two independent surfaces. (1) `core/application_classify.py` — widen the EEO label regex (pure Python, TDD via pytest). (2) `browser-extension/content/form_enumerate.js` — a logical type resolver, ARIA/`*` requiredness, label cleanup, radio/checkbox grouping, and intentional combobox-partner skipping, tested by a new Playwright spec that injects the enumerator against synthetic HTML fixtures. Enumeration stays read-only (no writes, no network, no focus/mutation).

**Tech Stack:** Python 3 + pytest; MV3 content script (plain ES, no modules); Playwright (`e2e/extension/`), TypeScript.

## Global Constraints

- Enumeration is **read-only**: no `.value` writes, no network, no focusing/clicking controls, no page mutation. (Combobox option harvesting is deliberately out of scope — comboboxes ship `options: []`.)
- `form_enumerate.js` has **no module system** — functions are page-context globals (function declarations), same convention as `linkedin.js`/`indeed.js`. Do not add `import`/`export`.
- `EnumeratedField` shape (`core/schemas.py`) is **unchanged**: `{ field_id, label, input_type, options, required }`. `input_type` stays a free-form `str`; it now carries logical values.
- EEO guard is deliberately over-broad: a false positive merely leaves a field blank for manual entry; a false negative (a demographic question reaching the LLM) is the failure to prevent.
- Logical `input_type` vocabulary: `combobox`, `multiselect`, `select`, `radio_group`, `checkbox_group`, `checkbox`, plus passthrough DOM types (`text`, `tel`, `email`, `url`, `number`, `date`, `file`, `textarea`).
- Commit after each task with the `[type] Imperative subject` convention (`feat`/`fix`/`test`/`docs`).

---

### Task 1: Harden the EEO guard (Python)

**Files:**
- Modify: `core/application_classify.py:17-21` (the `_EEO_RE` pattern)
- Test: `tests/core/test_application_classify.py` (extend existing)

**Interfaces:**
- Consumes: nothing new.
- Produces: `is_eeo_label(label: str) -> bool` and `classify_custom(label: str) -> "eeo"|"eligibility"|"essay"` — unchanged signatures, widened EEO branch.

- [ ] **Step 1: Add the failing regression test.** Append to `tests/core/test_application_classify.py` the six verbatim real Reddit EEO labels captured in the audit (the transgender one is the current gap):

```python
# Real labels captured from live Greenhouse (Reddit board, 2026-07-22).
# "transgender experience" is the known false-negative this task fixes.
REAL_EEO_LABELS = [
    "What gender identity do you most closely identify with?",
    "Are you a person of transgender experience?",
    "What sexual orientation do you most closely identify with?",
    "Do you live with a disability (as outlined by the ADA)?",
    "Are you a veteran/have you served in the military?",
    "Please select up to 2 ethnicities that you most closely identify with.",
]


@pytest.mark.parametrize("label", REAL_EEO_LABELS)
def test_eeo_guard_catches_real_greenhouse_labels(label):
    assert is_eeo_label(label) is True
    assert classify_custom(label) == "eeo"
```

- [ ] **Step 2: Run it and confirm the transgender case fails.**

Run: `python -m pytest tests/core/test_application_classify.py::test_eeo_guard_catches_real_greenhouse_labels -v`
Expected: FAIL on the `"Are you a person of transgender experience?"` parametrization (asserts `is_eeo_label` is True but it returns False); the other five PASS.

- [ ] **Step 3: Widen `_EEO_RE`.** Replace the pattern at `core/application_classify.py:17-21` with:

```python
_EEO_RE = re.compile(
    r"\b(race|ethnicit|gender|transgender|sex\b|male\b|female\b|veteran|disab|"
    r"hispanic|latino|sexual orientation|national origin|protected class|"
    r"self[- ]?identif)\w*",
    re.IGNORECASE,
)
```

The only change is adding `transgender|` to the alternation (the bare `gender` term cannot match inside "transgender" because of the leading `\b`, so the explicit term is required). Everything else is preserved.

- [ ] **Step 4: Run the full classify test file.**

Run: `python -m pytest tests/core/test_application_classify.py -v`
Expected: PASS — all six real labels, the original `EEO_LABELS`, eligibility, and essay-fallback cases green.

- [ ] **Step 5: Commit.**

```bash
git add core/application_classify.py tests/core/test_application_classify.py
git commit -m "[fix] Harden EEO guard against 'transgender experience' label"
```

---

### Task 2: Logical type resolver + ARIA requiredness + label de-noising (JS)

**Files:**
- Modify: `browser-extension/content/form_enumerate.js` (full rewrite of the field loop; `labelFor` retained)
- Create: `e2e/extension/tests/enumerate.spec.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (page-context globals): `enumerateForm() -> Array<{field_id, label, input_type, options, required}>`; helper globals `_logicalType(el, domType)`, `_isRequired(el, rawLabel)`, `_cleanLabel(raw)` (Tasks 3–4 add more helpers to this file).

- [ ] **Step 1: Write the failing Playwright test.** Create `e2e/extension/tests/enumerate.spec.ts`. It injects the real enumerator against synthetic HTML (no backend, no staged job) and asserts logical typing, requiredness, and label cleanup:

```typescript
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
```

- [ ] **Step 2: Run it and confirm failure.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts`
Expected: FAIL — the combobox test reports `input_type: "text"` and `required: false`; the asterisk test reports `required: false`.

- [ ] **Step 3: Rewrite `form_enumerate.js`.** Replace the entire file with (grouping helpers `_isGroup`/`_describeGroup`/`_isComboPartner` are added in Tasks 3–4 — this version has no grouping/partner logic yet):

```javascript
// browser-extension/content/form_enumerate.js
// Read-only enumeration of a live application form. No writing, no network, no
// focus/mutation. enumerateForm()/labelFor() join the shared page-context global
// scope (no module system in MV3 content scripts), same convention as
// linkedin.js/indeed.js.
function enumerateForm() {
  const form = document.querySelector("form") || document.body;
  const controls = [...form.querySelectorAll("input, select, textarea")];
  const out = [];
  for (const el of controls) {
    const domType = (el.type || el.tagName).toLowerCase();
    if (["hidden", "submit", "button", "search"].includes(domType)) continue;

    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
    if (!id) continue;

    const rawLabel = labelFor(el);
    out.push({
      field_id: id,
      label: _cleanLabel(rawLabel),
      input_type: _logicalType(el, domType),
      options: el.tagName === "SELECT" ? [...el.options].map((o) => o.textContent.trim()) : [],
      required: _isRequired(el, rawLabel),
    });
  }
  return out;
}

// Logical (not raw-DOM) field type. Greenhouse/Ashby render single- and
// multi-selects as role="combobox" text inputs, so el.type alone reports "text".
function _logicalType(el, domType) {
  const role = (el.getAttribute("role") || "").toLowerCase();
  const isCombo = role === "combobox" || el.hasAttribute("aria-autocomplete");
  const multi =
    el.getAttribute("aria-multiselectable") === "true" || (el.tagName === "SELECT" && el.multiple);
  if (isCombo) return multi ? "multiselect" : "combobox";
  if (el.tagName === "SELECT") return multi ? "multiselect" : "select";
  return domType;
}

// Requiredness lives in ARIA or the label '*' on modern ATS DOM, not el.required.
function _isRequired(el, rawLabel) {
  return (
    el.required ||
    el.getAttribute("aria-required") === "true" ||
    /\*\s*$/.test(rawLabel || "")
  );
}

// Strip a single trailing required-marker '*' and collapse whitespace so the
// marker drives `required` instead of polluting the question text.
function _cleanLabel(raw) {
  return (raw || "").replace(/\s*\*\s*$/, "").replace(/\s+/g, " ").trim();
}

function labelFor(el) {
  if (el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab) return lab.textContent.trim();
  }
  const wrap = el.closest("label");
  if (wrap) return wrap.textContent.trim();
  return el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "";
}
```

- [ ] **Step 4: Run the enumerate spec.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts`
Expected: PASS — all three tests green.

- [ ] **Step 5: Run the existing extension specs to confirm no regression.**

Run: `cd e2e/extension && npx playwright test`
Expected: PASS — `extension-loads.spec.ts`, `autofill.spec.ts` (all three ATS cases), and `enumerate.spec.ts`. (Requires the local stack on `:8080` per `e2e/extension/CONTEXT.md`.)

- [ ] **Step 6: Commit.**

```bash
git add browser-extension/content/form_enumerate.js e2e/extension/tests/enumerate.spec.ts
git commit -m "[feat] Enumerate logical field types + ARIA-aware required in extension"
```

---

### Task 3: Skip anonymous combobox partner inputs (JS)

**Files:**
- Modify: `browser-extension/content/form_enumerate.js` (add `_isComboPartner`, call it in the loop)
- Modify: `e2e/extension/tests/enumerate.spec.ts` (add a case)

**Interfaces:**
- Consumes: `enumerateForm`, `labelFor` from Task 2.
- Produces: helper global `_isComboPartner(el) -> boolean`.

- [ ] **Step 1: Add the failing test.** Append to `enumerate.spec.ts`:

```typescript
test('drops the anonymous partner input a combobox pairs with', async ({ context }) => {
  // Greenhouse renders a visible role=combobox input plus a second nameless/idless
  // input in the same container. Only the combobox should be enumerated.
  const fields = await enumerate(context, `
    <div>
      <label for="country">Country*</label>
      <input id="country" type="text" role="combobox" aria-autocomplete="list" />
      <input type="text" />
    </div>
  `);
  const countryFields = fields.filter((f) => f.input_type === 'combobox' || f.label === '');
  expect(fields).toHaveLength(1);
  expect(fields[0].field_id).toBe('country');
});
```

- [ ] **Step 2: Run it and confirm failure.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts -g "partner input"`
Expected: FAIL — `fields` has length 2 (the anonymous partner is still emitted, because the `slice(0,60)` aria-label fallback is empty but the partner has no id so it is *currently* dropped by `if (!id) continue`... verify: the nameless/idless/aria-less input yields `id === ""` and is already skipped). If length is already 1, adjust the fixture so the partner input carries a stray `aria-label=" "` (whitespace) that defeats the `!id` guard, proving the need for an explicit partner check:

```typescript
    <input type="text" aria-label=" " />
```

- [ ] **Step 3: Add `_isComboPartner` and call it.** In `form_enumerate.js`, add this helper after `_cleanLabel`:

```javascript
// A combobox renders a second input in its container with no real identity.
// Skip it explicitly (rather than relying on the empty-id guard) so a genuinely
// anonymous field elsewhere is still logged, not silently swallowed.
function _isComboPartner(el) {
  const idish = el.name || el.id || (el.getAttribute("aria-label") || "").trim();
  if (idish) return false;
  const container = el.closest("div, fieldset, label") || el.parentElement;
  return !!(container && container.querySelector('[role="combobox"]'));
}
```

Then, in `enumerateForm`, insert the partner check immediately after the `domType` skip line and before the `id` computation:

```javascript
    if (["hidden", "submit", "button", "search"].includes(domType)) continue;

    if (_isComboPartner(el)) continue;

    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
    if (!id) {
      console.debug("[job-scraper][enumerate] skipped anonymous control", el.tagName, domType);
      continue;
    }
```

(The `console.debug` makes a *non-partner* anonymous drop diagnosable per the Global Constraint intent.)

- [ ] **Step 4: Run the spec.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts`
Expected: PASS — all Task 2 cases plus the partner-drop case.

- [ ] **Step 5: Commit.**

```bash
git add browser-extension/content/form_enumerate.js e2e/extension/tests/enumerate.spec.ts
git commit -m "[feat] Skip anonymous combobox partner inputs during enumeration"
```

---

### Task 4: Radio/checkbox group association (JS)

**Files:**
- Modify: `browser-extension/content/form_enumerate.js` (add grouping; branch in the loop)
- Modify: `e2e/extension/tests/enumerate.spec.ts` (add cases)

**Interfaces:**
- Consumes: `enumerateForm`, `labelFor`, `_cleanLabel`, `_isRequired` from Tasks 2–3.
- Produces: helper globals `_groupOf(form, el) -> HTMLElement[]`, `_groupLabel(el) -> string`.

- [ ] **Step 1: Add the failing tests.** Append to `enumerate.spec.ts`:

```typescript
test('collapses a radio group into one field with the legend as the question', async ({ context }) => {
  const fields = await enumerate(context, `
    <fieldset>
      <legend>Are you authorized to work in the US?*</legend>
      <label><input type="radio" name="work_auth" value="yes"> Yes</label>
      <label><input type="radio" name="work_auth" value="no"> No</label>
    </fieldset>
  `);
  expect(fields).toHaveLength(1);
  expect(fields[0].field_id).toBe('work_auth');
  expect(fields[0].input_type).toBe('radio_group');
  expect(fields[0].label).toBe('Are you authorized to work in the US?');
  expect(fields[0].required).toBe(true);
  expect(fields[0].options).toEqual(['Yes', 'No']);
});

test('keeps a lone consent checkbox as a single checkbox field', async ({ context }) => {
  const fields = await enumerate(context, `
    <label><input type="checkbox" name="consent"> I consent to data processing</label>
  `);
  expect(fields).toHaveLength(1);
  expect(fields[0].input_type).toBe('checkbox');
  expect(fields[0].field_id).toBe('consent');
});
```

- [ ] **Step 2: Run and confirm failure.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts -g "radio group"`
Expected: FAIL — the radio group currently emits two `radio` fields, not one `radio_group`; label is the option text, not the legend.

- [ ] **Step 3: Add grouping.** In `form_enumerate.js`, add these helpers after `_isComboPartner`:

```javascript
// All same-name radio/checkbox controls within the form (a logical group).
function _groupOf(form, el) {
  if (!el.name) return [el];
  return [...form.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`)];
}

// The group's question: <legend>, then a labelled radiogroup/group container,
// falling back to the first member's own label so the field is never dropped.
function _groupLabel(el) {
  const fs = el.closest("fieldset");
  const legend = fs && fs.querySelector("legend");
  if (legend) return legend.textContent.trim();
  const grp = el.closest('[role="radiogroup"], [role="group"]');
  if (grp && grp.getAttribute("aria-label")) return grp.getAttribute("aria-label");
  return labelFor(el);
}
```

Then add a grouping branch in `enumerateForm`, immediately after the `_isComboPartner` check and before the `id` computation. Track handled groups so each emits once:

```javascript
    if (_isComboPartner(el)) continue;

    if (domType === "radio" || (domType === "checkbox" && el.name && _groupOf(form, el).length > 1)) {
      const members = _groupOf(form, el);
      const key = el.name || (el.closest("fieldset") && el.closest("fieldset").id) || "";
      if (!key || seenGroups.has(key)) continue;
      seenGroups.add(key);
      const rawLabel = _groupLabel(el);
      out.push({
        field_id: el.name || key,
        label: _cleanLabel(rawLabel),
        input_type: domType === "radio" ? "radio_group" : "checkbox_group",
        options: members.map((m) => _cleanLabel(labelFor(m))),
        required: members.some((m) => _isRequired(m, _groupLabel(m))),
      });
      continue;
    }

    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
```

Declare `seenGroups` at the top of `enumerateForm`, next to `out`:

```javascript
  const out = [];
  const seenGroups = new Set();
```

(A lone checkbox — `_groupOf(...).length === 1` — falls through to the normal path and keeps `input_type: "checkbox"` via `_logicalType`, satisfying the consent-checkbox test.)

- [ ] **Step 4: Run the enumerate spec.**

Run: `cd e2e/extension && npx playwright test enumerate.spec.ts`
Expected: PASS — all cases from Tasks 2–4.

- [ ] **Step 5: Run the full extension suite.**

Run: `cd e2e/extension && npx playwright test`
Expected: PASS — no regression in `autofill.spec.ts`/`extension-loads.spec.ts`.

- [ ] **Step 6: Commit.**

```bash
git add browser-extension/content/form_enumerate.js e2e/extension/tests/enumerate.spec.ts
git commit -m "[feat] Group radio/checkbox controls into one enumerated field"
```

---

### Task 5: Documentation sync

**Files:**
- Modify: `browser-extension/CONTEXT.md` (the `enumerateForm` description + the "Selector-fragility caveat")
- Modify: `.claude/TODO.md` (mark the enumeration-correctness spec item as implemented)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `browser-extension/CONTEXT.md`.** In the "Application-plan enumeration + autofill" section (the step-2 bullet describing `enumerateForm()`), replace the sentence that says it "returns `{field_id, label, input_type, options, required}` per field" by walking `input`/`select`/`textarea` with the accurate behavior:

```markdown
2. If matched, waits (MutationObserver, 8s timeout via `_waitForFormReady`) for
   the form UI to render, then calls `enumerateForm()` (`content/form_enumerate.js`),
   which walks the form's `input`/`select`/`textarea` controls (skipping
   hidden/submit/button/search) and returns `{field_id, label, input_type, options,
   required}` per field. `input_type` is a **logical** type, not the raw DOM type:
   `role="combobox"`/`aria-autocomplete` inputs report `combobox` (or `multiselect`);
   native `<select>` reports `select`/`multiselect`; same-name radio/checkbox sets
   collapse into one `radio_group`/`checkbox_group` field whose `label` is the
   `<legend>`/group question and whose `options` are the member labels. `required`
   is derived from `el.required` **or** `aria-required="true"` **or** a trailing `*`
   in the label (modern Greenhouse/Ashby set none of these as the DOM `required`
   attribute). Labels have the trailing `*` stripped. Combobox options render on
   focus and are **not** harvested (read-only enumeration) — comboboxes ship
   `options: []`. The anonymous partner input each combobox pairs with is skipped.
```

- [ ] **Step 2: Update the fragility caveat.** In the "Selector-fragility caveat" paragraph, append a sentence noting the new coverage and its verification:

```markdown
The logical-type/requiredness/grouping behavior is unit-tested against synthetic
fixtures in `e2e/extension/tests/enumerate.spec.ts` (combobox typing, ARIA/`*`
requiredness, radio-group collapse, partner-input skip); live-DOM label derivation
for radio *group questions* remains heuristic (`<legend>` → labelled group → first
member label) and is the known Ashby-class risk.
```

- [ ] **Step 3: Update `.claude/TODO.md`.** Find the enumeration-correctness follow-up note added under "Full automation of document submission" → sub-project 2 and mark it implemented, referencing this plan and the EEO-guard fix. Keep the follow-on stages (classification breadth, fill-commit) listed as still-open.

- [ ] **Step 4: Commit.**

```bash
git add browser-extension/CONTEXT.md .claude/TODO.md
git commit -m "[docs] Document logical enumeration typing + grouping + EEO fix"
```

---

## Self-Review

**Spec coverage** (§4 of the spec → task):
- §4.1 logical type resolver → Task 2 (`_logicalType`).
- §4.2 ARIA requiredness + label de-noise → Task 2 (`_isRequired`, `_cleanLabel`).
- §4.3 radio/checkbox grouping → Task 4.
- §4.4 intentional partner-input skipping → Task 3.
- §4.5 combobox options deferred → encoded as a Global Constraint + documented in Task 5; no code (correct — it's a non-goal).
- §4.6 EEO guard hardening + real-label regression fixtures → Task 1.
- §6 testing (extension harness + classifier unit + live spot-check) → Tasks 1–4 tests; live spot-check is manual (noted in the spec, not a code task).

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N" — every code step shows complete code. Task 3 Step 2 gives an explicit fixture adjustment rather than a vague "make it fail."

**Type consistency:** `enumerateForm`, `labelFor`, `_logicalType`, `_isRequired`, `_cleanLabel`, `_isComboPartner`, `_groupOf`, `_groupLabel`, `seenGroups` are named identically across Tasks 2–4. `input_type` values (`combobox`/`multiselect`/`select`/`radio_group`/`checkbox_group`/`checkbox`) match the Global Constraint vocabulary. `_EEO_RE` change is additive (`transgender|`) and consistent with Task 1's test.

One known-fragile point flagged for the implementer: Task 3 Step 2 — verify whether the empty-`id` guard already drops the partner input; if so, use the `aria-label=" "` fixture variant so the test genuinely exercises `_isComboPartner`.
