# Combobox Fill-Commit + Honest Reporting — Design

**Date:** 2026-07-22
**Status:** Draft (pending review)
**Area:** `browser-extension/content/form_fill.js`, `browser-extension/content/injector.js`, `e2e/extension/`
**Related:** `docs/superpowers/specs/2026-07-22-extension-form-enumeration-correctness-design.md` → §8 follow-on stage 2 (this spec fulfills the "combobox selection commit + honest per-field fill reporting" half; option harvesting stays deferred). `browser-extension/CONTEXT.md` → "`form_fill.js` — the writer".

## 1. Problem

The extension's autofill pipeline is enumerate → `/application-plan` (server resolves values) → `fillForm` (writer). A live audit of a real Greenhouse form showed `fillForm` reports every field "filled," but **combobox fields never actually commit a selection**. Modern Greenhouse renders single-selects (Country, Location, work-authorization, degree, and the EEO questions) as **react-select** widgets: a `role="combobox"` text input backed by an ARIA `listbox`. The current `_writeValue` treats such an input as plain text — it writes the value through the native setter and fires `input`/`change`, which merely *opens and filters the menu*. No option is selected, so the field submits empty and, when required, blocks submission.

Two problems compound: (1) the commit never happens, and (2) `fillForm`'s `{ filled: count }` return can't distinguish a real commit from a typed-but-uncommitted value — which is exactly what hid the bug.

## 2. Evidence (live audit, Reddit Greenhouse, 2026-07-22)

- `country` / `candidate-location` and all single-select questions are `input[role="combobox"][aria-autocomplete="list"]`, `aria-expanded` toggling on open, no `name`.
- Options render as `[role="option"]` within a `[role="listbox"]`; react-select **commits a choice on `mousedown`** of an option (not `click`), then renders the choice as a `select__single-value` element inside the `select__control`.
- Classes are emotion-generated (`remix-css-<hash>`, `select__` prefix) — the hash is unstable across builds, so private class names are unreliable anchors; the ARIA roles are stable.
- Current `_writeValue` combobox path = the text fallthrough (`_setNativeValue` + `_fire`) → menu opens, nothing selected.

## 3. Goals / Non-goals

**Goals**
- A `role="combobox"` field with a plan-resolved value **commits a real selection** on Greenhouse react-select, verified before it is reported as filled.
- `fillForm` returns an **honest per-field report**; `injector.js` logs a truthful summary (the missing signal that hid the bug).
- A value that can't be matched/verified leaves the field **cleared** (no stray typed text) and is reported `uncommitted`.
- Preserve the existing safety invariant: **EEO/demographic fields are never typed** into a combobox.
- Text/`<select>`/checkbox/radio fills keep working unchanged (regression-guarded).

**Non-goals (deferred)**
- Lever and Ashby combobox commit (different widgets/DOM) — Greenhouse react-select only.
- **Option harvesting** into the plan (focus-render + scrape option lists server-side) — out of scope; commit matches at fill time.
- **Multi-select** commit. The only multi-selects on real Greenhouse forms are EEO ("select up to 2 ethnicities"), which are never filled. A `multiselect` input type is routed to `skipped`, never a partial commit.
- Any user-facing UI change (no new banner/modal; console logging only, matching the current convention).
- Data-sourcing correctness (whether the plan's resolved value matches an option's wording) — a mismatch correctly surfaces as `uncommitted`.

## 4. Design

### 4.1 Async writer

`fillForm(plannedFields)` becomes **`async`**. It iterates fields, awaits each write, and accumulates a per-field result. Synchronous paths (text/select/checkbox/radio) simply resolve immediately; the combobox path is genuinely async.

### 4.2 Routing

In `_writeValue` (or a new `_writeValueAsync`), branch on the logical control shape **before** the text fallthrough:

- `el.getAttribute("role") === "combobox"` **or** `el.hasAttribute("aria-autocomplete")` → `await _commitCombobox(el, value)`.
- `el.getAttribute("aria-multiselectable") === "true"` (multi-select combobox) → **not attempted**; caller records `skipped` (see §4.5). (In practice these arrive already `skipped` from the plan, but the guard is defensive.)
- Otherwise the existing `<select>` / checkbox / radio / native-text paths, unchanged.

### 4.3 `_commitCombobox(el, value) -> Promise<boolean>`

1. `el.focus()`.
2. Write `value` into the input via the native-setter path (reuse `_setNativeValue`) and dispatch `input` (bubbling) so react-select filters and opens the menu.
3. **Poll** for a matching option: every ~60ms up to a ~1500ms cap, scan `[role="option"]` for one whose **normalized** text (trim → collapse whitespace → case-fold) matches the normalized `value` — exact match preferred; if none, a **unique** `startsWith` match; ambiguous/none → keep waiting until the cap.
4. On a match: dispatch `mousedown`, `mouseup`, then `click` (bubbling, with `{ bubbles: true }`) on the option element — react-select commits on `mousedown`; the extra events are harmless and cover minor variants.
5. **Verify:** within the field's `select__control`/container, read the committed text from `[class*="singleValue"]` (fallback: `[class*="single-value"]`). Return `true` only if its normalized text **equals** the matched option's normalized text.
6. **On failure** (no match by cap, or verify not equal): call `_clearCombobox(el)` and return `false`.

### 4.4 `_clearCombobox(el)`

Reset to empty so nothing looks half-filled: dispatch `Escape` `keydown`/`keyup` (closes the menu), set the input value back to `""` via the native setter + `input`, and `el.blur()`. react-select discards unselected input text on blur; the explicit reset guarantees it regardless of variant.

### 4.5 Per-field report

`fillForm` returns:

```
{ filled: <number>, results: Array<{ field_id, input_type, status }> }
```

`status` values:
- `filled` — written; for comboboxes, commit verified.
- `uncommitted` — combobox value unmatched/unverified; field cleared; needs manual entry.
- `failed` — control found but the write threw, or a `<select>`/checkbox/radio value matched no option.
- `skipped` — plan status not `filled`/`drafted`, or empty value, or a `multiselect` combobox. **Every EEO field lands here.**
- `not_found` — `_findControl` returned nothing.

`filled` remains the count of `status === "filled"` for backward-compatible logging.

### 4.6 `injector.js` integration

`_runFormEnumeration` (currently `fillForm(result.fields)`, fire-and-forget) becomes:

```
const report = await fillForm(result.fields);
const notFilled = report.results.filter(r => r.status !== "filled");
console.info(`${_AP_LOG} fill: ${report.filled}/${report.results.length} committed`,
  notFilled.length ? notFilled : "(all filled)");
```

No other injector behavior changes; the answers-nudge banner is untouched. All fill work stays inside the existing try/catch so a writer error never blocks page interaction.

### 4.7 Resilience

Match on the stable ARIA contract (`[role="option"]`, `[role="listbox"]`, `[class*="singleValue"]`) rather than exact emotion hashes. The `equals` verification (not "non-empty") ensures a pre-existing selection can't be misread as our commit, and a future react-select variant that commits differently degrades to `uncommitted` (safe) rather than a silent false success.

## 5. Interfaces

- `fillForm(plannedFields) -> Promise<{ filled, results }>` — was `-> { filled }`. Sole caller is `injector.js` (`await`ed).
- `_commitCombobox(el, value) -> Promise<boolean>` — new page-context global.
- `_clearCombobox(el) -> void` — new page-context global.
- No module system (page-context function declarations), consistent with `form_enumerate.js`/`form_fill.js`.

## 6. Testing

Extension harness (`e2e/extension/`), synthetic fixtures, no LLM/backend.

- **New fixture:** a hand-rolled minimal combobox (~40-line inline `<script>`) reproducing the react-select *contract* the commit depends on: a `role="combobox"` input that, on `input`, renders a `[role="listbox"]` of matching `[role="option"]`s, and on an option's `mousedown` renders a `[class*="singleValue"]` element and sets the committed value. Deterministic; exercises both happy and clear paths. (Rationale: bundling real react-select is version-coupled and slow; the interaction contract is what we verify.)
- **New spec `e2e/extension/tests/fill.spec.ts`:**
  1. Combobox with a matching option → `mousedown` commits, single-value shows the value, status `filled`.
  2. Combobox with no matching option → input ends empty, status `uncommitted`.
  3. Plain text / native `<select>` / checkbox still fill (sync-path regression).
  4. A field with a blank/`unknown` plan status (EEO stand-in) → never typed, status `skipped`.
  5. `fillForm` resolves and returns `results[]` with the correct per-field statuses.
- **Full-suite regression:** `autofill.spec.ts` + `enumerate.spec.ts` + `extension-loads.spec.ts` still pass (needs local stack on `:8080`).
- **Live spot-check (manual, not CI):** on the audited Reddit form, drive a plan whose `country` resolves to a real option and confirm the single-value commits and verifies.

## 7. Risks

- **Commit-on-mousedown is the load-bearing assumption.** If a Greenhouse variant commits differently, the verify step reports `uncommitted` instead of a false success — degrades safely.
- **Async timing:** menu render latency varies; the bounded poll trades a small worst-case delay per unmatched combobox (~1.5s) for reliability. On a form with many unresolved comboboxes this adds up, but only for fields that had a value to try.
- **Option-text wording mismatch** (plan says "USA", option says "United States") surfaces as `uncommitted` — correct behavior; the fix belongs to the deferred data-sourcing/option-harvesting stage.
- **Hand-rolled fixture drift from real react-select:** mitigated by keeping the fixture faithful to the ARIA contract and retaining the manual live spot-check as the real-DOM backstop.

## 8. Follow-on stages (not this spec)

1. **Option harvesting** — focus-render and scrape combobox option lists so the plan/data-sourcing can pick a value that will actually match.
2. **Lever + Ashby combobox commit** — per-widget commit strategies.
3. **Multi-select commit** — once a non-EEO multi-select use case exists.
