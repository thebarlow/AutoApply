# Extension Form-Enumeration Correctness — Design

**Date:** 2026-07-22
**Status:** Draft (pending review)
**Area:** `browser-extension/content/form_enumerate.js`, `core/application_classify.py`, `core/schemas.py`
**Related:** `.claude/TODO.md` → "Full automation of document submission" sub-projects 2–3; `browser-extension/CONTEXT.md` → "Application-plan enumeration"; the deferred `fillForm` honest-reporting design (superseded/absorbed here).

## 1. Problem

Before the pipeline can classify a form field or source a value for it, it must **first read the field correctly**: what the control is (type), what it's asking (question/label), and whether it's required. A live audit of two real Greenhouse application forms (Reddit board, 2026-07-22) shows `enumerateForm()` gets this wrong on a large fraction of real fields — including every EEO demographic question. Downstream classification and data-sourcing inherit these errors.

This spec covers **enumeration correctness only** (pipeline stage 1) plus one **safety fix** that spans enumeration→classification. Classification improvements (broadening label→canonical matching) and data-sourcing/fill-commit are explicitly **out of scope** here and tracked as later stages (see §8).

## 2. Evidence (live audit)

Two real Greenhouse forms audited via the browser (Reddit `job-boards.greenhouse.io/reddit/jobs/7669372` and `.../7330347`). Modern Greenhouse renders **33 of 34 controls as `<input>`**; almost no native `<select>`/`<radio>`. Requiredness and type live in ARIA, not DOM attributes.

Field types actually present, and how current `enumerateForm()` reports them:

| Real type | Renders as | Current report | Correct? |
|---|---|---|---|
| Free text | `input/text` | `text` | ✅ |
| Phone | `input/tel` | `tel` | ✅ |
| File (resume/cover) | `input/file` | `file` | ✅ |
| Single-select (Country, work-auth, degree, **all EEO**) | `input/text` + `role="combobox"` | `text` | ❌ |
| Multi-select ("select up to 2 ethnicities") | `role="combobox"` multi | `text` | ❌ |
| Consent checkbox | `input/checkbox` | `checkbox` | ✅ |

### Confirmed defects

1. **Comboboxes are invisible as a type.** ~10 fields/form — including every EEO demographic question (gender identity, transgender experience, sexual orientation, disability, veteran, ethnicity), the consent dropdown, and all eligibility questions — enumerate as generic `text`.
2. **`required` is `false` for everything.** Enumerator reads `el.required`; truth is `aria-required="true"` (+ a trailing `*` in the label). Every question loses its requiredness in the plan.
3. **Anonymous partner inputs.** Each combobox pairs with a second no-`id`/no-`name` input; the `field_id` fallback silently drops it. Correct outcome, but incidental rather than intentional, and fragile.
4. **Combobox options never captured.** `options` is populated only for `<select>`. Combobox lists render on focus, so classification/data-sourcing get zero valid values to match against.
5. **Label carries `*` noise** ("First Name\*") instead of that marker driving `required`.

### Safety finding (spans enumerate → classify)

Because EEO fields now render as generic comboboxes with `question_<id>` ids, the EEO guard in `core/application_classify.py` (`_EEO_RE`) is the *only* thing keeping demographics out of the LLM essay pass — and it is **label-only**, which is correct, but has a live gap:

- Real label **"Are you a person of transgender experience?"** does **not** match `_EEO_RE`. `\bgender` fails inside "transgender" (no word boundary mid-word), and no other term matches → `classify_custom` returns `"essay"` → the field routes to the metered LLM pass. A demographic question the guard was designed to never touch.

Other real EEO labels *do* match today: gender identity (`\bgender`), sexual orientation, disability (`disab`), veteran, ethnicity (`ethnicit`). Only the transgender phrasing slips through — but one gap is enough to violate the invariant, and confirms the guard needs hardening against real-world phrasings.

## 3. Goals / Non-goals

**Goals**
- `enumerateForm()` emits one entry per **logical** question, each with: a correct logical `input_type`, ARIA-aware `required`, a de-noised `label`, and `options` where discoverable without mutating the page.
- Radio/checkbox groups collapse to one logical field with the group question as label and the per-option labels as `options` (needed for Ashby/Lever even though Greenhouse doesn't use them).
- The EEO guard never routes a real demographic question to the essay pass; hardened against the transgender gap and similar phrasings, with the real labels captured as regression fixtures.
- No page mutation, no writes, no network — enumeration stays read-only.

**Non-goals (later stages)**
- Broadening label→canonical matching so deterministic fields (LinkedIn URL, location, name synonyms) stop falling into the essay bucket — classification stage.
- Committing combobox selections / async option harvesting for fill — data-sourcing + fill stage (absorbs the deferred `fillForm` honest-reporting work).
- Multi-step / iframe / paginated forms.

## 4. Design

### 4.1 Logical type resolver (`form_enumerate.js`)

Replace `const type = (el.type || el.tagName).toLowerCase()` with a `logicalType(el)` resolver, in precedence order:

1. `role="combobox"` **or** `aria-autocomplete` present → `combobox`. If `aria-multiselectable="true"` (or a known multi container) → `multiselect`.
2. native `<select>` → `select` (multiple → `multiselect`).
3. `type="radio"`/`type="checkbox"` that is part of a group (shares `name`, or ≥2 siblings in one `fieldset`/`[role=radiogroup]`) → handled by grouping (§4.3), emitted as `radio_group` / `checkbox_group`. A lone checkbox stays `checkbox`.
4. otherwise the DOM `type` (`text`/`tel`/`email`/`url`/`number`/`date`/`file`/`textarea`).

`input_type` in `EnumeratedField` stays a free-form `str` (schema unchanged) but now carries these logical values. **Downstream note:** the mapper (`core/application_mapper.py`) routes by *label*, not `input_type`, so this is additive for classification; the value matters for the future fill stage (`form_fill.js` branches on type).

### 4.2 ARIA-aware requiredness + label de-noising

- `required = el.required || el.getAttribute("aria-required") === "true" || /[*]\s*$/.test(rawLabel)`.
- `label` = raw label with a single trailing `*` (and surrounding whitespace) stripped, whitespace collapsed. The `*` informs `required`, never survives in the label text.

### 4.3 Radio/checkbox grouping

Before the per-control loop, partition group controls: bucket radios/checkboxes by `name` (fallback: common `fieldset`/`[role=radiogroup]` ancestor). For each group emit **one** `EnumeratedField`:
- `field_id` = shared `name` (fallback: group ancestor's id, else a stable synthesized key).
- `label` = group question, resolved from `<legend>`, `[role=radiogroup][aria-label]`, or the nearest preceding heading/label above the group — **not** an individual option's label.
- `options` = each member's own `labelFor()`.
- `input_type` = `radio_group` (single-select) or `checkbox_group`.

### 4.4 Intentional partner-input skipping

Make combobox partner-input dropping explicit: skip an `<input>` that has no `name`/`id`/`aria-label` **and** sits alongside a sibling `role="combobox"` in the same field container. Keeps the current outcome but by intent, and prevents a future anonymous *real* field from being dropped by a blanket fallback (log-and-skip so it's diagnosable).

### 4.5 Option discovery for comboboxes

Combobox options render on focus. Harvesting them requires focusing each control (async, mutates page/focus state) — **out of scope** for read-only enumeration. Enumeration emits `options: []` for comboboxes; classification/data-sourcing matches by label and (later stage) may focus-harvest at fill time. Decision recorded so it isn't silently re-litigated.

### 4.6 EEO guard hardening (`core/application_classify.py`)

- Extend `_EEO_RE` to cover the real gaps: add `transgender`, and broaden to catch `gender identity`, `sexual orientation`, `person of ... experience` demographic phrasings. Keep the guard deliberately over-broad (a false positive just leaves a field blank for manual entry; a false negative is the dangerous case).
- Add a regression test seeded with the **exact real labels** captured in this audit (all six Reddit EEO questions, including the transgender one) asserting `classify_custom(label) == "eeo"` for each. This locks the invariant against future phrasings.

## 5. Interfaces

- `EnumeratedField` (`core/schemas.py`) — **unchanged shape**; `input_type` now carries logical values, `required`/`options` now populated more accurately. No migration.
- `enumerateForm() -> EnumeratedField[]` — same signature, richer/correct output.
- `classify_custom(label) -> "eeo"|"eligibility"|"essay"` — unchanged signature; EEO branch widened.

## 6. Testing

- **Extension harness** (`e2e/extension/`): extend fixtures to include (a) a `role="combobox"` control, (b) a radio group with a `<legend>`, (c) a `*`-marked required field with `aria-required`. Assert the enumerator returns the right `input_type`, grouped single entry, `required=true`, and de-noised label. Fixtures are canonical/synthetic (no LLM) per the existing harness invariant.
- **Classifier unit test** (`tests/core/test_application_classify.py`): the six real EEO labels → `"eeo"`; a sample of eligibility + essay labels unchanged.
- **Live spot-check** (manual, not CI): re-run the enumerator against the two audited Reddit forms and confirm combobox typing + requiredness now match ground truth.

## 7. Risks

- **Group-question resolution is heuristic** — `<legend>`/preceding-heading derivation is DOM-shape dependent (the known Ashby fragility). Mitigation: fall back to the first option's label with a diagnostic console line rather than dropping the field.
- **Over-broad EEO regex** could capture a non-EEO essay question containing "gender"/"sex" — acceptable by design (leaves it blank for manual entry).
- Focus-free enumeration means comboboxes ship with empty `options`; the classification stage must not assume options are present.

## 8. Follow-on stages (not this spec)

1. **Classification breadth** — label→canonical synonyms (url/location/name), so deterministic fields stop over-invoking the essay pass.
2. **Data-sourcing + fill commit** — combobox selection commit, focus-harvest options, and honest per-field fill reporting (absorbs the earlier `fillForm` `{filled, results[]}` design: `filled`/`failed`/`uncommitted` per field, logged by `injector.js`).
