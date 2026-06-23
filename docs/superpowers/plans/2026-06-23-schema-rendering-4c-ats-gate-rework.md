# 4C ATS Gate Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the fixed-section hard-block and skill synonym map from the ATS mechanical layer, and move section-structure verification to the advisory semantic roundtrip.

**Architecture:** Two focused edits to `core/ats_gate.py`. Task 1 strips `section_missing` and the synonym map from `check_mechanical` (literal-only skill matching). Task 2 adds an advisory `roundtrip_sections` diff to `check_roundtrip` and re-documents the adapter whose `section_order` now feeds the roundtrip. No schema, wiring, or blocking-contract change.

**Tech Stack:** Python, pytest. Spec: `docs/superpowers/specs/2026-06-23-4c-ats-gate-rework-design.md`.

## Global Constraints

- Merges to LOCAL `main` only — do NOT push `main` (whole-swap release gate, #4–#6 + #5).
- Critical mechanical issues still hard-block; warnings never block. Do not change `AtsReport.build` or the confirm-applied gate.
- No section is universally required; no roles; no synonym/vendor-dictionary matching.
- Do not change `run_ats_check`, PDF extraction, report storage, or the score formula.
- New roundtrip finding is `code="roundtrip_sections"`, `severity="warning"`, `layer="semantic"`.

---

### Task 1: Strip `section_missing` + synonym map from `check_mechanical`

**Files:**
- Modify: `core/ats_gate.py` (remove `_RAW_SYNONYMS`/`_SKILL_SYNONYMS`, simplify `_present`, delete the `section_missing` loop)
- Test: `tests/core/test_ats_mechanical.py`

**Interfaces:**
- Consumes: `check_mechanical(pt, doc, required_skills, preferred_skills, user_skills) -> list[AtsIssue]` (signature unchanged).
- Produces: `check_mechanical` no longer emits `section_missing`; `present_skill_dropped` now matches literal-only.

- [ ] **Step 1: Update the existing section test to assert the block is gone**

In `tests/core/test_ats_mechanical.py`, replace `test_missing_section_is_critical` with:

```python
def test_missing_section_no_longer_blocks():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nSKILLS\n"  # no EDUCATION
    pt = PdfText(text=full, lines=[ln.strip() for ln in full.splitlines() if ln.strip()])
    issues = check_mechanical(pt, _doc(), [], [], [])
    assert "section_missing" not in _codes(issues)
    assert not any(i.severity == "critical" for i in issues)
```

- [ ] **Step 2: Add a synonym-removal test**

Append to `tests/core/test_ats_mechanical.py`:

```python
def test_synonym_no_longer_matches_dropped_skill():
    # Resume renders "postgres" but the owned/wanted skill is "postgresql".
    # With the synonym map gone, this is a literal miss -> warning.
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\npostgres\n"
    pt = PdfText(text=full, lines=[ln.strip() for ln in full.splitlines() if ln.strip()])
    issues = check_mechanical(pt, _doc(), ["postgresql"], [], ["postgresql"])
    dropped = [i for i in issues if i.code == "present_skill_dropped"]
    assert dropped and dropped[0].severity == "warning"


def test_literal_skill_match_emits_nothing():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\npostgresql\n"
    pt = PdfText(text=full, lines=[ln.strip() for ln in full.splitlines() if ln.strip()])
    issues = check_mechanical(pt, _doc(), ["postgresql"], [], ["postgresql"])
    assert not any(i.code == "present_skill_dropped" for i in issues)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/core/test_ats_mechanical.py -q`
Expected: `test_missing_section_no_longer_blocks` FAILS (still emits `section_missing`); `test_synonym_no_longer_matches_dropped_skill` FAILS (synonym map still matches `postgres`→`postgresql`, so no warning).

- [ ] **Step 4: Remove the synonym map and simplify `_present`**

In `core/ats_gate.py`, delete the `_RAW_SYNONYMS` and `_SKILL_SYNONYMS` blocks (the lines between the `extract_text` function and `_present`), and replace `_present` with:

```python
def _present(term: str, haystack_lower: str) -> bool:
    """Case-insensitive literal substring match."""
    t = term.strip().lower()
    return bool(t) and t in haystack_lower
```

- [ ] **Step 5: Delete the `section_missing` loop**

In `core/ats_gate.py` `check_mechanical`, remove the entire block:

```python
    # section_missing — section_order values are lowercase by convention; the
    # PDF text is lowercased into `low`, so the comparison is case-insensitive.
    for section in doc.section_order:
        if section.lower() not in low:
            issues.append(AtsIssue(layer="mechanical", severity="critical",
                                   code="section_missing",
                                   message=f"Section '{section}' header missing from extracted text."))
```

Leave the `present_skill_dropped`, `glyph_junk`, and contact blocks untouched.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/core/test_ats_mechanical.py -q`
Expected: PASS (all, including the unchanged contact/glyph/skill regression tests).

- [ ] **Step 7: Commit**

```bash
git add core/ats_gate.py tests/core/test_ats_mechanical.py
git commit -m "[refactor] Drop section_missing hard-block and skill synonym map from ATS gate"
```

---

### Task 2: Advisory `roundtrip_sections` diff + adapter docstring

**Files:**
- Modify: `core/ats_gate.py` (`check_roundtrip` — add section diff)
- Modify: `core/ats_tree_adapter.py` (module docstring only)
- Test: `tests/core/test_ats_roundtrip.py`

**Interfaces:**
- Consumes: `check_roundtrip(pt, doc, prompt, client, model) -> list[AtsIssue]` (signature unchanged); reads `doc.section_order` and `parsed.sections`.
- Produces: a warning-only `roundtrip_sections` issue when document sections are missing from a non-empty parse.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_ats_roundtrip.py`:

```python
def _doc_with_sections():
    return ResumeDocument(
        header=ResumeHeader(name="Jane Doe", email="jane@x.com"),
        section_order=["experience", "skills"],
    )


def test_roundtrip_flags_missing_section():
    parsed = {"name": "Jane Doe", "email": "jane@x.com", "phone": "",
              "sections": ["experience"], "skills": [], "experience_dates": []}
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(_pt(), _doc_with_sections(), "P {extracted_text}", client=object(), model="m")
    sec = [i for i in issues if i.code == "roundtrip_sections"]
    assert sec and sec[0].severity == "warning" and sec[0].layer == "semantic"
    assert "skills" in sec[0].message


def test_roundtrip_no_section_issue_when_all_present():
    parsed = {"name": "Jane Doe", "email": "jane@x.com", "phone": "",
              "sections": ["experience", "skills"], "skills": [], "experience_dates": []}
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(_pt(), _doc_with_sections(), "P {extracted_text}", client=object(), model="m")
    assert not any(i.code == "roundtrip_sections" for i in issues)


def test_roundtrip_empty_parse_suppresses_section_issue():
    parsed = {"name": "Jane Doe", "email": "jane@x.com", "phone": "",
              "sections": [], "skills": [], "experience_dates": []}
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(_pt(), _doc_with_sections(), "P {extracted_text}", client=object(), model="m")
    assert not any(i.code == "roundtrip_sections" for i in issues)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/core/test_ats_roundtrip.py -q`
Expected: `test_roundtrip_flags_missing_section` FAILS (no `roundtrip_sections` issue yet).

- [ ] **Step 3: Add the section diff to `check_roundtrip`**

In `core/ats_gate.py`, in `check_roundtrip`, immediately before `return issues`, insert:

```python
    # roundtrip_sections (advisory) — document sections the parser did not recover.
    # Suppressed when the parse returned no sections (under-parse, not a layout fault).
    if parsed.sections:
        parsed_set = {s.strip().lower() for s in parsed.sections if s.strip()}
        missing = [s for s in doc.section_order
                   if s.strip() and s.strip().lower() not in parsed_set]
        if missing:
            issues.append(AtsIssue(layer="semantic", severity="warning",
                                   code="roundtrip_sections",
                                   message=f"Parser did not recover section(s): {', '.join(missing)}."))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/core/test_ats_roundtrip.py -q`
Expected: PASS (including the unchanged name/email/phone/error tests).

- [ ] **Step 5: Update the adapter docstring**

In `core/ats_tree_adapter.py`, replace the module docstring with:

```python
"""Project a tree-v1 document into the minimal ResumeDocument the ATS gate reads
(header + section_order). The header feeds the mechanical contact checks; section_order
feeds the advisory semantic roundtrip (4C removed the mechanical section hard-block).
"""
```

- [ ] **Step 6: Run the full ATS suite to confirm no regressions**

Run: `pytest tests/core/test_ats_mechanical.py tests/core/test_ats_roundtrip.py tests/core/test_ats_run_gate.py tests/web/test_confirm_applied_ats_gate.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/ats_gate.py core/ats_tree_adapter.py tests/core/test_ats_roundtrip.py
git commit -m "[feat] Add advisory roundtrip_sections diff to ATS semantic layer"
```

---

## Self-Review

- **Spec coverage:** `section_missing` deletion (Task 1, steps 1/3/5), synonym-map removal + literal `_present` (Task 1, steps 2/4), advisory `roundtrip_sections` with empty-parse suppression (Task 2), adapter docstring (Task 2, step 5). Kept checks guarded by existing regression tests. All spec sections covered.
- **Placeholder scan:** none — every step shows full code/commands.
- **Type consistency:** `check_mechanical`/`check_roundtrip` signatures unchanged; `AtsIssue` fields match existing usage; `_codes`/`_doc`/`_pt` helpers reused from the existing test files.
