"""Serve workflow output as a local slide deck: one job per slide.

Each slide shows the raw description (left, with matched spans marked) next
to the processed/extracted fields (right). Clicking a skill chip or a
responsibility/signal bullet on the right jumps to and highlights the
matching span(s) in the raw text on the left — only one item is highlighted
at a time. In compare mode (--compare-a/--compare-b) each slide adds a
second processed column for A/B review of two prompt versions.

Usage:
    python -m workflows.view_slides
    python -m workflows.view_slides --compare-a workflows/output/extracted_v1.json --compare-b workflows/output/extracted_v2.json
"""
from __future__ import annotations

import argparse
import html
import http.server
import json
import re
import webbrowser
from pathlib import Path

_DEFAULT_FILE = Path("workflows/output/recent_jobs.json")
_DEFAULT_EXTRACTED = Path("workflows/output/extracted.json")
_DEFAULT_COMPARED = Path("workflows/output/compared.json")
_DEFAULT_COVERS = Path("workflows/output/cover_letters.json")
_DEFAULT_RESUMES = Path("workflows/output/resumes.json")
_DEFAULT_RESUME_EVALS = Path("workflows/output/resume_evals.json")
_DEFAULT_ATS_REPORTS = Path("workflows/output/ats_reports.json")
_DEFAULT_PORT = 8766

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(s: str) -> set[str]:
    return set(_WORD_RE.findall(s.lower()))


def _slug(key: str) -> str:
    return html.escape(key, quote=True)


def _best_line_match(lines: list[str], phrase: str, used: set[int]) -> int | None:
    """Return the index of the raw line most similar to `phrase` by word overlap, or None."""
    phrase_tokens = _tokenize(phrase)
    if not phrase_tokens:
        return None
    best_i, best_score = None, 0.0
    for i, line in enumerate(lines):
        if i in used or not line.strip():
            continue
        line_tokens = _tokenize(line)
        if not line_tokens:
            continue
        overlap = phrase_tokens & line_tokens
        score = len(overlap) / len(phrase_tokens | line_tokens)
        if score > best_score:
            best_score, best_i = score, i
    return best_i if best_score >= 0.15 else None


def _normalize_skills(ext: dict) -> list[dict]:
    """Return a list of {name, category, requirement, expansion} dicts.

    Supports both the current `skills` schema and the legacy flat
    required_skills/preferred_skills/tech_stack lists (v1 extraction files),
    so old extraction runs still render in A/B compare mode.
    """
    if "skills" in ext:
        return ext["skills"]
    skills = []
    for name in ext.get("required_skills", []):
        skills.append({"name": name, "category": None, "requirement": "required", "expansion": None})
    for name in ext.get("preferred_skills", []):
        skills.append({"name": name, "category": None, "requirement": "preferred", "expansion": None})
    for name in ext.get("tech_stack", []):
        skills.append({"name": name, "category": "Tech Stack", "requirement": "required", "expansion": None})
    return skills


def _annotate_raw(description: str, skills: list[dict], phrase_groups: list[tuple[str, list[str]]]) -> tuple[str, dict[str, bool]]:
    """Mark up the raw description with clickable spans for skills and phrases.

    Args:
        description: Raw job description text.
        skills: Normalized skill dicts (see `_normalize_skills`) to find as exact
            substrings of their `name`.
        phrase_groups: List of (key_prefix, phrases) — phrases are matched to the
            single best raw line by word overlap (LLM phrasing rarely quotes verbatim).

    Returns:
        (annotated_html, matched) where matched maps every phrase's data-key to
        whether a raw-text match was found (skills are always considered matched
        if the term appears at all — checked separately by the caller).
    """
    lines = description.split("\n")
    used: set[int] = set()
    line_key: dict[int, str] = {}
    matched: dict[str, bool] = {}

    for prefix, phrases in phrase_groups:
        for idx, phrase in enumerate(phrases):
            key = f"{prefix}::{idx}"
            best_i = _best_line_match(lines, phrase, used)
            if best_i is not None:
                used.add(best_i)
                line_key[best_i] = key
                matched[key] = True
            else:
                matched[key] = False

    annotated_lines = []
    for i, line in enumerate(lines):
        escaped = html.escape(line)
        key = line_key.get(i)
        if key:
            escaped = f'<mark class="hl" data-key="{_slug(key)}">{escaped}</mark>'
        annotated_lines.append(escaped)
    annotated = "\n".join(annotated_lines)

    # Skill names are exact substrings — mark every occurrence, longest names first
    # so e.g. "REST API" wins over "REST" when both are present.
    for skill in sorted(skills, key=lambda s: len(s.get("name", "")), reverse=True):
        term = (skill.get("name") or "").strip()
        if not term:
            continue
        key = f"skill::{term.lower()}"
        title_attr = f' title="{_slug(skill["expansion"])}"' if skill.get("expansion") else ""
        pattern = re.escape(html.escape(term))
        annotated = re.sub(
            rf"(?i)(?<![\w>])({pattern})(?![\w<])",
            lambda m, key=key, title_attr=title_attr: f'<mark class="hl" data-key="{_slug(key)}"{title_attr}>{m.group(1)}</mark>',
            annotated,
        )

    return annotated, matched


_MATCH_LABEL = {"direct": "Direct match", "near": "Near match", "miss": "Miss"}


def _skill_match_lookup(compare: dict) -> dict[str, tuple[str, str]]:
    """name.lower() -> (match_level, evidence) from a compared.json skill_matches list."""
    return {
        (m.get("name") or "").strip().lower(): (m.get("match") or "", m.get("evidence") or "")
        for m in compare.get("skill_matches", [])
    }


def _requirement_match_lookup(compare: dict) -> dict[str, tuple[str, str]]:
    """requirement text -> (match_level, evidence) from a compared.json requirement_matches list."""
    return {
        (m.get("text") or "").strip(): (m.get("match") or "", m.get("evidence") or "")
        for m in compare.get("requirement_matches", [])
    }


def _skill_groups(skills: list[dict], match_lookup: dict[str, tuple[str, str]] | None = None) -> str:
    """Render skills grouped by category; chip border = required/preferred, chip fill = match level."""
    if not skills:
        return ""
    match_lookup = match_lookup or {}
    groups: dict[str, list[dict]] = {}
    for s in skills:
        cat = (s.get("category") or "Other").strip() or "Other"
        groups.setdefault(cat, []).append(s)

    blocks = []
    for cat, items in groups.items():
        chips = []
        for s in items:
            name = (s.get("name") or "").strip()
            if not name:
                continue
            key = f"skill::{name.lower()}"
            req = s.get("requirement") or "required"
            source = s.get("source") or "stated"
            source_class = " src-inferred" if source == "inferred" else ""
            level, evidence = match_lookup.get(name.lower(), ("", ""))
            match_class = f" match-{html.escape(level)}" if level else ""
            title_bits = [
                t for t in (
                    s.get("expansion"),
                    source == "inferred" and "Inferred: not named in the JD, standard for this role type",
                    evidence and f"{_MATCH_LABEL.get(level, level)}: {evidence}",
                ) if t
            ]
            title_attr = f' title="{_slug(" — ".join(title_bits))}"' if title_bits else ""
            marker = ' <span class="src-marker">†</span>' if source == "inferred" else ""
            chips.append(
                f'<span class="chip linkable req-{html.escape(req)}{match_class}{source_class}" data-key="{_slug(key)}"{title_attr}>{html.escape(name)}{marker}</span>'
            )
        blocks.append(
            f'<div class="skill-group"><span class="group-label">{html.escape(cat)}</span>'
            f'<div class="chips">{"".join(chips)}</div></div>'
        )
    has_inferred = any((s.get("source") or "stated") == "inferred" for s in skills)
    legend = '<p class="skill-legend">† inferred: standard for this role, not stated in the JD</p>' if has_inferred else ""
    return f'<div class="field"><span class="field-label">Skills</span>{"".join(blocks)}{legend}</div>'


def _phrase_list(
    label: str,
    values: list[str],
    prefix: str,
    matched: dict[str, bool],
    match_lookup: dict[str, tuple[str, str]] | None = None,
) -> str:
    if not values:
        return ""
    match_lookup = match_lookup or {}
    items = []
    for idx, v in enumerate(values):
        key = f"{prefix}::{idx}"
        level, evidence = match_lookup.get(v.strip(), ("", ""))
        match_class = f" match-{html.escape(level)}" if level else ""
        title = f"{_MATCH_LABEL.get(level, level)}: {evidence}" if evidence else ""
        title_attr = f' title="{_slug(title)}"' if title else ""
        if matched.get(key):
            items.append(f'<li class="linkable{match_class}" data-key="{_slug(key)}"{title_attr}>{html.escape(v)}</li>')
        else:
            no_match_title = title or "No matching raw text found"
            items.append(f'<li class="unlinked{match_class}" title="{_slug(no_match_title)}">{html.escape(v)}</li>')
    return f'<div class="field"><span class="field-label">{html.escape(label)}</span><ul>{"".join(items)}</ul></div>'


def _phrase_groups(ext: dict, side: str) -> list[tuple[str, list[str]]]:
    """Phrase groups for one extraction, key-prefixed by `side` so A and B don't collide."""
    return [
        (f"resp-{side}", ext.get("key_responsibilities", [])),
        (f"sig-{side}", ext.get("company_signals", [])),
        (f"req-{side}", ext.get("unmatched_requirements", [])),
    ]


def _raw_column(description_raw: str, ext_a: dict, ext_b: dict | None = None) -> tuple[str, dict[str, bool]]:
    """Annotate the raw column against one or two extractions (A/B compare).

    Phrase keys are side-prefixed ("resp-a::0" / "resp-b::0") so A and B bullets
    never collide; the returned `matched` dict uses those same prefixed keys, and
    callers must pass the matching side prefix into `_phrase_list`/data-key building.
    """
    skills = _normalize_skills(ext_a)
    phrase_groups = _phrase_groups(ext_a, "a")
    if ext_b is not None:
        skills = skills + _normalize_skills(ext_b)
        phrase_groups = phrase_groups + _phrase_groups(ext_b, "b")

    if description_raw:
        annotated, matched = _annotate_raw(description_raw, skills, phrase_groups)
    else:
        annotated, matched = "(no description)", {}

    return f"""
    <div class="col raw">
      <h3 class="col-heading">Raw</h3>
      <pre>{annotated}</pre>
    </div>
    """, matched


def _cover_letter_panel(cover: dict | None, job_key: str = "") -> str:
    if not cover or not cover.get("letter"):
        return '<p class="empty-panel">No cover letter generated yet.</p>'
    research_note = ""
    if cover.get("used_web_research") and cover.get("research_note"):
        research_note = f'<p class="research-note">Web research used: {html.escape(cover["research_note"])}</p>'
    pdf_link = ""
    if job_key:
        pdf_href = f'pdfs/{html.escape(job_key)}_cover.pdf'
        pdf_link = f'<p><a class="pdf-link" href="{pdf_href}" target="_blank">Open cover letter PDF &rarr;</a></p>'
    return (
        f'{pdf_link}'
        f'<p class="cover-letter-text">{html.escape(cover["letter"])}</p>'
        f'<p class="cover-meta">{cover.get("word_count", "?")} words'
        f'{" &middot; web research used" if cover.get("used_web_research") else ""}</p>'
        f'{research_note}'
    )


def _eval_badge(evaluation: dict | None) -> str:
    if not evaluation:
        return ""
    checks = evaluation.get("checks", {})
    failing = [name for name, c in checks.items() if not c.get("pass", True)]
    if evaluation.get("overall_pass"):
        return '<div class="eval-badge eval-pass">&check; Passed evaluation</div>'
    issue_lines = "".join(
        f'<li><strong>{html.escape(name)}</strong>: {html.escape("; ".join(checks[name].get("issues", [])))}</li>'
        for name in failing
    )
    return f'<div class="eval-badge eval-fail">&cross; Failed evaluation ({len(failing)} check(s))<ul>{issue_lines}</ul></div>'


def _ats_badge(ats_report: dict | None, job_key: str) -> str:
    if not ats_report:
        return ""
    pdf_href = f'pdfs/{html.escape(job_key)}_resume.pdf'
    link = f'<a class="pdf-link" href="{pdf_href}" target="_blank">Open résumé PDF &rarr;</a>'
    issues = ats_report.get("issues", [])
    n_crit = sum(1 for i in issues if i.get("severity") == "critical")
    n_warn = sum(1 for i in issues if i.get("severity") == "warning")
    score = ats_report.get("score", 0)
    issue_lines = "".join(
        f'<li>[{html.escape(i.get("layer", ""))}] <strong>{html.escape(i.get("code", ""))}</strong>: {html.escape(i.get("message", ""))}</li>'
        for i in issues
    )
    issues_html = f"<ul>{issue_lines}</ul>" if issues else ""

    if ats_report.get("passed"):
        badge = (
            f'<div class="eval-badge eval-pass">&check; ATS check passed (score {score:.2f}'
            f'{f", {n_warn} warning(s)" if n_warn else ""})'
            f'<span class="ats-layers">mechanical + semantic layers checked</span>{issues_html}</div>'
        )
    else:
        badge = f'<div class="eval-badge eval-fail">&cross; ATS check failed (score {score:.2f}, {n_crit} critical, {n_warn} warning){issues_html}</div>'
    return f'<div class="ats-block">{link}{badge}</div>'


def _resume_panel(resume: dict | None, evaluation: dict | None = None, ats_report: dict | None = None, job_key: str = "") -> str:
    if not resume:
        return '<p class="empty-panel">No tailored résumé generated yet.</p>'

    eval_html = _eval_badge(evaluation)
    ats_html = _ats_badge(ats_report, job_key)
    summary_html = f'<p class="resume-summary">{html.escape(resume["summary"])}</p>' if resume.get("summary") else ""

    skill_groups = resume.get("skills") or []
    skills_html = ""
    if skill_groups:
        # Supports both the categorized schema ({category, items}) and the legacy
        # flat list (plain strings), so older resumes.json files still render.
        if skill_groups and isinstance(skill_groups[0], dict):
            blocks = []
            for g in skill_groups:
                chips = "".join(f'<span class="chip">{html.escape(i)}</span>' for i in g.get("items", []))
                blocks.append(
                    f'<div class="skill-group"><span class="group-label">{html.escape(g.get("category", ""))}</span>'
                    f'<div class="chips">{chips}</div></div>'
                )
            skills_html = f'<div class="field"><span class="field-label">Skills</span>{"".join(blocks)}</div>'
        else:
            chips = "".join(f'<span class="chip">{html.escape(s)}</span>' for s in skill_groups)
            skills_html = f'<div class="field"><span class="field-label">Skills</span><div class="chips">{chips}</div></div>'

    def _entry_block(label: str, entries: list[dict], name_field: str, meta_fn) -> str:
        visible = [e for e in entries if e.get("include", True)]
        omitted = [e for e in entries if not e.get("include", True)]
        blocks = []
        for e in visible:
            bullets = "".join(f"<li>{html.escape(b)}</li>" for b in e.get("bullets", []))
            blocks.append(
                f'<div class="resume-entry"><div class="resume-entry-head">'
                f'<span class="resume-entry-name">{html.escape(e.get(name_field, ""))}</span>'
                f'<span class="resume-entry-meta">{meta_fn(e)}</span></div>'
                f'<ul>{bullets}</ul></div>'
            )
        omitted_html = ""
        if omitted:
            names = ", ".join(html.escape(e.get(name_field, "")) for e in omitted)
            omitted_html = f'<p class="resume-omitted">Omitted as not relevant: {names}</p>'
        return f'<div class="field"><span class="field-label">{html.escape(label)}</span>{"".join(blocks)}{omitted_html}</div>'

    work_html = _entry_block(
        "Work History", resume.get("work_history", []), "company",
        lambda e: f'{html.escape(e.get("title", ""))} &middot; {html.escape(e.get("start", ""))}&ndash;{html.escape(e.get("end", ""))}',
    )
    projects_html = _entry_block(
        "Projects", resume.get("projects", []), "name",
        lambda e: "",
    )

    education = resume.get("education") or []
    education_html = ""
    if education:
        items = "".join(
            f"<li>{html.escape(e.get('degree', ''))} {html.escape(e.get('field', ''))} &mdash; "
            f"{html.escape(e.get('institution', ''))} ({html.escape(e.get('graduated', ''))})</li>"
            for e in education
        )
        education_html = f'<div class="field"><span class="field-label">Education</span><ul>{items}</ul></div>'

    return f"""
      {ats_html}
      {eval_html}
      {summary_html}
      <div class="highlights">
        {skills_html}
        {work_html}
        {projects_html}
        {education_html}
      </div>
    """


def _processed_column(
    ext: dict,
    matched: dict[str, bool],
    side: str,
    compare: dict | None = None,
    title: str = "",
    cover: dict | None = None,
    resume: dict | None = None,
    resume_eval: dict | None = None,
    ats_report: dict | None = None,
    job_key: str = "",
) -> str:
    """Render one processed column: tabbed Description / Cover Letter / Resume.

    `side` ("a" or "b") must match the prefix used when the raw column was
    annotated (see `_raw_column`/`_phrase_groups`), so phrase bullets link to
    the correct raw-text spans. `compare` is this job's entry from compared.json
    (skill_matches/requirement_matches/fit_summary), or None if not yet compared.
    `cover`/`resume` are this job's entries from cover_letters.json/resumes.json,
    or None if not generated. `resume_eval` is this job's entry from
    resume_evals.json (checks/overall_pass), or None if not evaluated. `ats_report`
    is this job's entry from ats_reports.json; `job_key` is needed to link the
    rendered PDF (workflows/output/pdfs/{job_key}_resume.pdf).
    Tabs are only shown when there's a `cover` to switch to — the A/B compare
    columns don't get one, so they stay untabbed.
    """
    compare = compare or {}
    skill_lookup = _skill_match_lookup(compare)
    req_lookup = _requirement_match_lookup(compare)

    summary_html = f'<p class="summary">{html.escape(ext["summary"])}</p>' if ext.get("summary") else ""

    fit_html = ""
    if compare.get("fit_summary"):
        fit_html = f'<p class="fit-summary">{html.escape(compare["fit_summary"])}</p>'

    education_line = (
        f'<div class="field"><span class="field-label">Education</span>'
        f'<span class="education">{html.escape(ext["education"])}</span></div>'
        if ext.get("education") else ""
    )

    clearance = ext.get("clearance")
    clearance_line = ""
    if clearance:
        status = clearance.get("status") or "not specified"
        level = clearance.get("level") or "unspecified"
        status_class = "clearance-hold" if status == "must already hold" else "clearance-obtain"
        clearance_line = (
            f'<div class="field"><span class="field-label">Clearance</span>'
            f'<span class="clearance {status_class}">{html.escape(level)} &mdash; {html.escape(status)}</span></div>'
        )

    salary_line = ""
    if ext.get("salary_min") or ext.get("salary_max"):
        currency = ext.get("salary_currency") or ""
        salary_line = (
            f'<div class="field"><span class="field-label">Salary</span>'
            f'<span class="salary">{currency} {ext.get("salary_min") or "?":,.0f} '
            f'&ndash; {ext.get("salary_max") or "?":,.0f}</span></div>'
        )

    badges = "".join(
        f'<span class="badge">{html.escape(str(ext[f]))}</span>'
        for f in ("seniority", "role_type", "domain", "work_arrangement", "employment_type")
        if ext.get(f) and ext[f] != "not specified"
    )

    fields = "".join(
        [
            education_line,
            clearance_line,
            salary_line,
            f'<div class="field"><span class="field-label">Signals</span><div class="chips">{badges}</div></div>' if badges else "",
            _skill_groups(_normalize_skills(ext), skill_lookup),
            _phrase_list("Key responsibilities", ext.get("key_responsibilities", []), f"resp-{side}", matched),
            _phrase_list("Company signals", ext.get("company_signals", []), f"sig-{side}", matched),
            _phrase_list("Other requirements", ext.get("unmatched_requirements", []), f"req-{side}", matched, req_lookup),
        ]
    )

    heading = f'<h3 class="col-heading">{html.escape(title)}</h3>' if title else '<h3 class="col-heading">Processed</h3>'
    description_panel = f"""
      {summary_html}
      {fit_html}
      <div class="highlights">{fields}</div>
    """

    if cover is None and resume is None:
        # No tabs to switch to yet — render the description content directly.
        return f"""
        <div class="col processed">
          {heading}
          {description_panel}
        </div>
        """

    resume_disabled = "" if resume is not None else " disabled title=\"Not yet generated\""
    return f"""
    <div class="col processed">
      {heading}
      <div class="tabs">
        <button class="tab-btn active" data-tab="description">Description</button>
        <button class="tab-btn" data-tab="cover">Cover Letter</button>
        <button class="tab-btn" data-tab="resume"{resume_disabled}>Resume</button>
      </div>
      <div class="tab-panel active" data-tab="description">{description_panel}</div>
      <div class="tab-panel" data-tab="cover">{_cover_letter_panel(cover, job_key)}</div>
      <div class="tab-panel" data-tab="resume">{_resume_panel(resume, resume_eval, ats_report, job_key)}</div>
    </div>
    """


def render_html(
    jobs: list[dict],
    extracted: dict[str, dict],
    extracted_b: dict[str, dict] | None = None,
    label_a: str = "Prompt A",
    label_b: str = "Prompt B",
    compared: dict[str, dict] | None = None,
    covers: dict[str, dict] | None = None,
    resumes: dict[str, dict] | None = None,
    resume_evals: dict[str, dict] | None = None,
    ats_reports: dict[str, dict] | None = None,
) -> str:
    """Render one <section class="slide"> per job: raw column + one or two processed columns."""
    compared = compared or {}
    covers = covers or {}
    resumes = resumes or {}
    resume_evals = resume_evals or {}
    ats_reports = ats_reports or {}
    slides = []
    for job in jobs:
        job_key = job.get("job_key", "")
        description_raw = job.get("description") or ""
        meta = " &middot; ".join(
            html.escape(str(job.get(field) or "—"))
            for field in ("company", "location", "source", "state", "scraped_at")
        )

        ext_a = extracted.get(job_key, {})
        ext_b = extracted_b.get(job_key, {}) if extracted_b is not None else None
        # Raw column is annotated against both extractions at once (side-prefixed
        # keys) so both A's and B's bullets/chips can link into the shared left pane.
        raw_col, matched = _raw_column(description_raw, ext_a, ext_b)
        compare_a = compared.get(job_key) if extracted_b is None else None  # compare data only shown outside A/B mode
        cover_a = covers.get(job_key) if extracted_b is None else None  # cover/tabs only shown outside A/B mode
        resume_a = resumes.get(job_key) if extracted_b is None else None  # resume/tabs only shown outside A/B mode
        resume_eval_a = resume_evals.get(job_key) if extracted_b is None else None
        ats_a = ats_reports.get(job_key) if extracted_b is None else None
        cols = [raw_col, _processed_column(ext_a, matched, "a", compare_a, label_a if extracted_b else "", cover_a, resume_a, resume_eval_a, ats_a, job_key)]
        if ext_b is not None:
            cols.append(_processed_column(ext_b, matched, "b", None, label_b))

        slides.append(f"""
        <section class="slide">
          <header>
            <h2>{html.escape(job.get("title") or job_key)}</h2>
            <span class="meta">{meta}</span>
          </header>
          <div class="cols cols-{len(cols)}">
            {"".join(cols)}
          </div>
        </section>
        """)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Job slide deck ({len(jobs)})</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; background: #fafafa; }}
  .deck-bar {{ position: sticky; top: 0; background: #222; color: #fff; padding: 0.5rem 1rem; display: flex; align-items: center; gap: 1rem; z-index: 10; }}
  .deck-bar button {{ background: #444; color: #fff; border: none; padding: 0.35rem 0.9rem; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }}
  .deck-bar button:hover {{ background: #555; }}
  .deck-bar .counter {{ font-variant-numeric: tabular-nums; }}
  .slide {{ display: none; padding: 1.5rem 2rem; max-width: 1400px; margin: 0 auto; }}
  .slide.active {{ display: block; }}
  .slide header {{ margin-bottom: 1rem; }}
  .slide h2 {{ margin: 0 0 0.2rem 0; }}
  .meta {{ color: #666; font-size: 0.85rem; }}
  .cols {{ display: grid; gap: 1rem; }}
  .cols-2 {{ grid-template-columns: 1fr 1fr; }}
  .cols-3 {{ grid-template-columns: 1fr 1fr 1fr; }}
  .col {{ background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 0.75rem 1rem; max-height: 75vh; overflow-y: auto; }}
  .col-heading {{ margin: 0 0 0.5rem 0; font-size: 0.95rem; color: #333; border-bottom: 1px solid #eee; padding-bottom: 0.3rem; }}
  pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 0.85rem; margin: 0; }}
  mark.hl {{ background: transparent; padding: 0 1px; border-bottom: 2px dotted #999; cursor: pointer; }}
  mark.hl.active-hl {{ background: #fff2a8; border-bottom: 2px solid #e0a800; border-radius: 2px; }}
  .summary {{ font-size: 0.88rem; color: #333; margin: 0 0 0.5rem 0; }}
  .fit-summary {{ font-size: 0.85rem; color: #333; margin: 0 0 0.75rem 0; padding: 0.4rem 0.6rem; background: #eef2ff; border-left: 3px solid #3355cc; border-radius: 0 4px 4px 0; }}
  .education {{ font-size: 0.85rem; }}
  .clearance {{ font-size: 0.85rem; font-weight: 600; padding: 0.05rem 0.4rem; border-radius: 3px; }}
  .clearance.clearance-hold {{ background: #ffe1e1; color: #8f1a1a; }}
  .clearance.clearance-obtain {{ background: #fff3d6; color: #8f6a1a; }}
  .highlights {{ background: #f7f7f9; border-radius: 4px; padding: 0.5rem 0.75rem; margin-bottom: 0.75rem; }}
  .field {{ margin-bottom: 0.4rem; }}
  .field-label {{ font-weight: 600; font-size: 0.75rem; text-transform: uppercase; color: #555; display: block; margin-bottom: 0.15rem; }}
  .skill-group {{ margin-bottom: 0.35rem; }}
  .group-label {{ font-size: 0.72rem; color: #777; display: block; margin-bottom: 0.1rem; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 0.3rem; }}
  .chip {{ background: #e3ecff; color: #1a3a8f; border-radius: 12px; padding: 0.1rem 0.6rem; font-size: 0.78rem; }}
  .chip.req-preferred {{ background: transparent; border: 1px dashed #1a3a8f; }}
  .chip.linkable {{ cursor: pointer; }}
  .chip.linkable.chip-active {{ background: #ffe066; color: #333; box-shadow: 0 0 0 2px #e0a800 inset; }}
  /* Match levels: fill = direct (solid green), near (amber), miss (muted red).
     req-preferred's dashed border still applies on top, so preferred+match reads as e.g. green dashed. */
  .chip.match-direct {{ background: #d6f5df; color: #146c2e; border-color: #146c2e; }}
  .chip.match-near {{ background: #fff3d6; color: #8f6a1a; border-color: #8f6a1a; }}
  .chip.match-miss {{ background: #f3e2e2; color: #8f2f2f; border-color: #8f2f2f; }}
  .chip.src-inferred {{ border-style: dotted; }}
  .src-marker {{ color: #8850c9; font-weight: 700; }}
  .skill-legend {{ font-size: 0.72rem; color: #999; margin: 0.2rem 0 0 0; }}
  .ats-block {{ margin-bottom: 0.6rem; }}
  .pdf-link {{ display: inline-block; font-size: 0.82rem; font-weight: 600; color: #1a3a8f; text-decoration: none; margin-bottom: 0.4rem; }}
  .pdf-link:hover {{ text-decoration: underline; }}
  .ats-layers {{ display: block; font-weight: normal; font-size: 0.72rem; color: #146c2e; opacity: 0.75; margin-top: 0.1rem; }}
  .eval-badge ul {{ margin: 0.3rem 0 0 1.1rem; padding: 0; font-weight: normal; font-size: 0.78rem; }}
  .field li.match-direct {{ border-left: 3px solid #146c2e; padding-left: 0.4rem; }}
  .field li.match-near {{ border-left: 3px solid #8f6a1a; padding-left: 0.4rem; }}
  .field li.match-miss {{ border-left: 3px solid #8f2f2f; padding-left: 0.4rem; color: #8f2f2f; }}
  .badge {{ background: #ddd; border-radius: 12px; padding: 0.1rem 0.6rem; font-size: 0.78rem; }}
  .salary {{ font-weight: 600; color: #1a7a3a; }}
  .field ul {{ margin: 0.1rem 0 0 1.1rem; padding: 0; font-size: 0.82rem; list-style-position: inside; }}
  .field li {{ margin-bottom: 0.1rem; }}
  .field li.linkable {{ cursor: pointer; }}
  .field li.linkable.chip-active {{ background: #ffe066; border-radius: 3px; }}
  .field li.unlinked {{ color: #999; }}
  .tabs {{ display: flex; gap: 0.25rem; margin-bottom: 0.6rem; border-bottom: 1px solid #ddd; }}
  .tab-btn {{ background: none; border: none; border-bottom: 2px solid transparent; padding: 0.3rem 0.7rem; font-size: 0.82rem; cursor: pointer; color: #555; }}
  .tab-btn:hover:not(:disabled) {{ color: #222; }}
  .tab-btn.active {{ color: #1a3a8f; border-bottom-color: #1a3a8f; font-weight: 600; }}
  .tab-btn:disabled {{ color: #ccc; cursor: not-allowed; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .cover-letter-text {{ font-size: 0.88rem; white-space: pre-wrap; margin: 0 0 0.6rem 0; }}
  .cover-meta {{ font-size: 0.78rem; color: #666; margin: 0 0 0.4rem 0; }}
  .research-note {{ font-size: 0.78rem; color: #555; background: #f7f7f9; border-radius: 4px; padding: 0.4rem 0.6rem; }}
  .empty-panel {{ color: #999; font-size: 0.85rem; }}
  .resume-summary {{ font-size: 0.88rem; color: #333; margin: 0 0 0.6rem 0; font-style: italic; }}
  .resume-entry {{ margin-bottom: 0.6rem; }}
  .resume-entry-head {{ display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.85rem; margin-bottom: 0.1rem; }}
  .resume-entry-name {{ font-weight: 600; }}
  .resume-entry-meta {{ color: #666; font-size: 0.78rem; white-space: nowrap; }}
  .resume-entry ul {{ margin: 0 0 0 1.1rem; padding: 0; font-size: 0.82rem; }}
  .resume-omitted {{ color: #999; font-size: 0.78rem; font-style: italic; margin: 0.2rem 0 0 0; }}
  .eval-badge {{ font-size: 0.82rem; border-radius: 4px; padding: 0.4rem 0.6rem; margin-bottom: 0.6rem; }}
  .eval-badge.eval-pass {{ background: #d6f5df; color: #146c2e; font-weight: 600; }}
  .eval-badge.eval-fail {{ background: #f3e2e2; color: #8f2f2f; }}
  .eval-badge.eval-fail > ul {{ margin: 0.3rem 0 0 1.1rem; padding: 0; font-weight: normal; font-size: 0.8rem; }}
</style>
</head>
<body>
  <div class="deck-bar">
    <button id="prev">&larr; Prev</button>
    <span class="counter"><span id="idx">1</span> / {len(jobs)}</span>
    <button id="next">Next &rarr;</button>
  </div>
  {"".join(slides)}
  <script>
    const slides = document.querySelectorAll('.slide');
    let i = 0;
    function show(n) {{
      slides.forEach((s, idx) => s.classList.toggle('active', idx === n));
      document.getElementById('idx').textContent = n + 1;
    }}
    document.getElementById('prev').onclick = () => {{ i = Math.max(0, i - 1); show(i); }};
    document.getElementById('next').onclick = () => {{ i = Math.min(slides.length - 1, i + 1); show(i); }};
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'ArrowRight') {{ i = Math.min(slides.length - 1, i + 1); show(i); }}
      if (e.key === 'ArrowLeft') {{ i = Math.max(0, i - 1); show(i); }}
    }});
    show(0);

    // Bidirectional linking: clicking a processed chip/bullet highlights its
    // raw-text span(s) and scrolls to them; clicking a raw-text span does the
    // reverse — highlights and scrolls to the processed item(s) that cite it.
    // Only one data-key is ever active at a time.
    document.addEventListener('click', (e) => {{
      const el = e.target.closest('.linkable, mark.hl');
      if (!el) return;
      const slide = el.closest('.slide');
      const key = el.dataset.key;
      if (!key) return;
      slide.querySelectorAll('.active-hl').forEach(m => m.classList.remove('active-hl'));
      slide.querySelectorAll('.chip-active').forEach(c => c.classList.remove('chip-active'));

      const marks = slide.querySelectorAll(`.col.raw mark.hl[data-key="${{CSS.escape(key)}}"]`);
      const chips = slide.querySelectorAll(`.col.processed .linkable[data-key="${{CSS.escape(key)}}"]`);
      marks.forEach(m => m.classList.add('active-hl'));
      chips.forEach(c => c.classList.add('chip-active'));

      const fromRaw = el.matches('mark.hl');
      const scrollTarget = fromRaw ? chips[0] : marks[0];
      if (scrollTarget) scrollTarget.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
    }});

    // Tab switching within a processed column (Description / Cover Letter / Resume).
    document.addEventListener('click', (e) => {{
      const btn = e.target.closest('.tab-btn');
      if (!btn || btn.disabled) return;
      const col = btn.closest('.col.processed');
      const tab = btn.dataset.tab;
      col.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
      col.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === tab));
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=_DEFAULT_FILE, help="Input JSON produced by a workflows fetch script.")
    parser.add_argument("--extracted", type=Path, default=_DEFAULT_EXTRACTED, help="Extraction JSON keyed by job_key.")
    parser.add_argument("--compared", type=Path, default=_DEFAULT_COMPARED, help="Candidate-fit comparison JSON keyed by job_key (skill/requirement match levels + fit summary). Ignored in --compare-a/--compare-b A/B mode.")
    parser.add_argument("--covers", type=Path, default=_DEFAULT_COVERS, help="Cover-letter JSON keyed by job_key ({letter, word_count, used_web_research, research_note}). Adds a Cover Letter tab. Ignored in --compare-a/--compare-b A/B mode.")
    parser.add_argument("--resumes", type=Path, default=_DEFAULT_RESUMES, help="Tailored-resume JSON keyed by job_key (summary/skills/work_history/projects/education). Enables the Resume tab. Ignored in --compare-a/--compare-b A/B mode.")
    parser.add_argument("--resume-evals", type=Path, default=_DEFAULT_RESUME_EVALS, help="Resume evaluation JSON keyed by job_key (checks/overall_pass). Adds a pass/fail badge to the Resume tab. Ignored in --compare-a/--compare-b A/B mode.")
    parser.add_argument("--ats-reports", type=Path, default=_DEFAULT_ATS_REPORTS, help="ATS mechanical-check JSON keyed by job_key (passed/score/issues) from render_documents.py. Adds a PDF link + ATS badge to the Resume tab. Ignored in --compare-a/--compare-b A/B mode.")
    parser.add_argument("--compare-a", type=Path, default=None, help="Extraction JSON for prompt A (A/B mode).")
    parser.add_argument("--compare-b", type=Path, default=None, help="Extraction JSON for prompt B (A/B mode).")
    parser.add_argument("--label-a", default="Prompt A")
    parser.add_argument("--label-b", default="Prompt B")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"{args.file} not found — run a workflows fetch script first.")

    jobs = json.loads(args.file.read_text(encoding="utf-8"))
    jobs = [j for j in jobs if j.get("description")]

    if args.compare_a and args.compare_b:
        extracted_a = json.loads(args.compare_a.read_text(encoding="utf-8"))
        extracted_b = json.loads(args.compare_b.read_text(encoding="utf-8"))
        out_html_content = render_html(jobs, extracted_a, extracted_b, args.label_a, args.label_b)
    else:
        extracted = json.loads(args.extracted.read_text(encoding="utf-8")) if args.extracted.exists() else {}
        compared = json.loads(args.compared.read_text(encoding="utf-8")) if args.compared.exists() else {}
        covers = json.loads(args.covers.read_text(encoding="utf-8")) if args.covers.exists() else {}
        resumes = json.loads(args.resumes.read_text(encoding="utf-8")) if args.resumes.exists() else {}
        resume_evals = json.loads(args.resume_evals.read_text(encoding="utf-8")) if args.resume_evals.exists() else {}
        ats_reports = json.loads(args.ats_reports.read_text(encoding="utf-8")) if args.ats_reports.exists() else {}
        out_html_content = render_html(jobs, extracted, compared=compared, covers=covers, resumes=resumes, resume_evals=resume_evals, ats_reports=ats_reports)

    out_dir = args.file.parent
    out_html = out_dir / "slides.html"
    out_html.write_text(out_html_content, encoding="utf-8")

    url = f"http://localhost:{args.port}/slides.html"
    print(f"serving {out_dir}/ at {url} (ctrl+c to stop)")
    if not args.no_browser:
        webbrowser.open(url)

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(out_dir), **kw)
    with http.server.ThreadingHTTPServer(("localhost", args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
