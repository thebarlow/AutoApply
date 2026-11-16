"""Render tailored résumé/cover-letter JSON to ATS-passing PDFs.

Reuses the live app's rendering pipeline directly rather than reimplementing
PDF generation: `core.document_assembler` (structured doc -> canonical
Markdown, pure) and `core.utils.render_pdf` (Markdown -> pandoc -> Jinja2 ->
headless Chromium PDF, pure — no DB/session param at all). The Jinja2
templates/CSS in `generator/` are documented as ATS-safe by design (contact
field DOM order, no images/tables in the text layer), so this step is a thin
adapter mapping `workflows/output/resumes.json` / `cover_letters.json` onto
the existing Pydantic models, not a new rendering path.

After rendering each résumé, runs the *mechanical* half of the live app's ATS
gate (`core.ats_gate.extract_text` + `check_mechanical` — also pure, no DB/LLM)
to verify contact fields and job-relevant skills survived into the PDF's text
layer. The LLM semantic round-trip layer (parse-from-text-and-diff) is instead
run by a dispatched subagent — see `prompts/ats_semantic_prompt.md` and
`merge_semantic_issues()` below — rather than the app's real LLM API client,
keeping this step local/offline like the rest of `workflows/`. This script
writes the ground-truth files the subagent needs (`{job_key}_resume_extracted.txt`,
`{job_key}_resume_doc.json`); the subagent dispatch itself happens outside this
script (Claude Code orchestrates it, same pattern as the eval/patch loop).

Usage:
    python -m workflows.render_documents
"""
from __future__ import annotations

import json
from pathlib import Path

from core.document_assembler import assemble_cover_markdown, assemble_resume_markdown, resume_section_order
from core.schemas import (
    CoverDocument,
    EducationItem,
    ResumeDocument,
    ResumeExperience,
    ResumeHeader,
    ResumeProject,
    ResumeSkillGroup,
    SignOff,
)
from core.utils import render_pdf
from core.ats_gate import check_mechanical, extract_text

_OUT_DIR = Path("workflows/output")
_PDF_DIR = _OUT_DIR / "pdfs"
_GENERATOR_DIR = Path("generator")


def _build_header(profile: dict) -> ResumeHeader:
    return ResumeHeader(
        name=profile.get("name", ""),
        email=profile.get("email", ""),
        phone=profile.get("phone", ""),
        location=profile.get("location", ""),
        github=profile.get("github", ""),
        linkedin=profile.get("linkedin", ""),
        website=profile.get("website", ""),
    )


def _build_resume_document(resume: dict, profile: dict) -> ResumeDocument:
    education = [
        EducationItem(
            institution=e.get("institution", ""),
            degree=e.get("degree", ""),
            field=e.get("field", ""),
            graduated=e.get("graduated", ""),
        )
        for e in profile.get("education", [])
    ]
    experience = [
        ResumeExperience(
            company=e.get("company", ""),
            title=e.get("title", ""),
            start=e.get("start", ""),
            end=e.get("end", ""),
            # Blank line before a "- " list lets pandoc's tight-list normalization
            # (core.utils.markdown_to_html) recognize it as a bullet list.
            description="\n".join(f"- {b}" for b in e.get("bullets", [])),
        )
        for e in resume.get("work_history", [])
    ]
    projects = [
        ResumeProject(
            name=p.get("name", ""),
            # Flowing prose, not a bullet list: _projects_section joins
            # "**Name**: {description}" on one line, which isn't list-safe.
            description=" ".join(p.get("bullets", [])),
        )
        for p in resume.get("projects", [])
        if p.get("include", True)
    ]
    skills = [
        ResumeSkillGroup(category=g.get("category", ""), items=g.get("items", []))
        for g in resume.get("skills", [])
    ]
    return ResumeDocument(
        header=_build_header(profile),
        education=education,
        profile_summary=resume.get("summary", ""),
        experience=experience,
        projects=projects,
        skills=skills,
    )


def _build_cover_document(cover: dict, profile: dict) -> CoverDocument:
    return CoverDocument(
        header=_build_header(profile),
        body=cover.get("letter", ""),
        signoff=SignOff(name=profile.get("name", "")),
    )


def _meta_dict(header: ResumeHeader, education: list[EducationItem]) -> dict:
    meta = header.model_dump()
    meta["education"] = [e.model_dump() for e in education]
    return meta


def render_resume(job_key: str, resume: dict, profile: dict) -> tuple[Path, ResumeDocument]:
    doc = _build_resume_document(resume, profile)
    body = assemble_resume_markdown(doc)
    md_path = _PDF_DIR / f"{job_key}_resume.md"
    md_path.write_text(body, encoding="utf-8")

    pdf_path = _PDF_DIR / f"{job_key}_resume.pdf"
    render_pdf(
        md_path,
        pdf_path,
        _GENERATOR_DIR / "resume_template.html",
        max_pages=1,
        meta=_meta_dict(doc.header, doc.education),
        css_path=None,
    )
    return pdf_path, doc


def render_cover(job_key: str, cover: dict, profile: dict) -> Path:
    doc = _build_cover_document(cover, profile)
    body = assemble_cover_markdown(doc)
    md_path = _PDF_DIR / f"{job_key}_cover.md"
    md_path.write_text(body, encoding="utf-8")

    pdf_path = _PDF_DIR / f"{job_key}_cover.pdf"
    render_pdf(
        md_path,
        pdf_path,
        _GENERATOR_DIR / "cover_template.html",
        max_pages=1,
        meta=_meta_dict(doc.header, []),
        css_path=None,
    )
    return pdf_path


def _score(issues: list[dict]) -> float:
    """Same formula as core.ats_gate.run_gate: 1.0 - 0.25*critical - 0.05*warning."""
    n_crit = sum(1 for i in issues if i["severity"] == "critical")
    n_warn = sum(1 for i in issues if i["severity"] == "warning")
    return max(0.0, min(1.0, 1.0 - 0.25 * n_crit - 0.05 * n_warn))


def run_ats_check(job_key: str, pdf_path: Path, doc: ResumeDocument, extracted_skills: list[dict], profile: dict) -> dict:
    """Mechanical-only ATS check (no LLM). Also writes the ground-truth files a
    dispatched subagent needs to run the semantic round-trip layer separately
    (extracted text + {header, section_order})."""
    stated = [s for s in extracted_skills if (s.get("source") or "stated") == "stated"]
    required = [s["name"] for s in stated if s.get("requirement") == "required"]
    preferred = [s["name"] for s in stated if s.get("requirement") == "preferred"]
    user_skills = profile.get("skills", [])

    pt = extract_text(pdf_path)
    issues = check_mechanical(pt, doc, required, preferred, user_skills)
    issue_dicts = [i.model_dump() for i in issues]

    (_PDF_DIR / f"{job_key}_resume_extracted.txt").write_text(pt.text, encoding="utf-8")
    (_PDF_DIR / f"{job_key}_resume_doc.json").write_text(
        json.dumps({"header": doc.header.model_dump(), "section_order": resume_section_order(doc)}, indent=2),
        encoding="utf-8",
    )

    return {
        "passed": not any(i["severity"] == "critical" for i in issue_dicts),
        "score": _score(issue_dicts),
        "issues": issue_dicts,
    }


def merge_semantic_issues(ats_reports_path: Path, job_key: str, semantic_issues: list[dict]) -> dict:
    """Append semantic-layer issues (from a dispatched subagent) into an existing
    ats_reports.json entry, recomputing score. `passed` is unaffected — semantic
    issues are advisory/warning-only by convention, never critical, matching
    core.ats_gate.check_roundtrip.

    Args:
        ats_reports_path: Path to ats_reports.json (read then overwritten).
        job_key: Which job's entry to update.
        semantic_issues: List of {layer, severity, code, message} dicts.

    Returns:
        The updated entry for `job_key`.
    """
    reports = json.loads(ats_reports_path.read_text(encoding="utf-8"))
    entry = reports[job_key]
    # Idempotent: drop any prior semantic issues before appending fresh ones,
    # so re-running the subagent doesn't accumulate duplicates.
    entry["issues"] = [i for i in entry["issues"] if i.get("layer") != "semantic"] + semantic_issues
    entry["score"] = _score(entry["issues"])
    entry["passed"] = not any(i["severity"] == "critical" for i in entry["issues"])
    reports[job_key] = entry
    ats_reports_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return entry


def main() -> None:
    resumes = json.loads((_OUT_DIR / "resumes.json").read_text(encoding="utf-8"))
    covers = json.loads((_OUT_DIR / "cover_letters.json").read_text(encoding="utf-8")) if (_OUT_DIR / "cover_letters.json").exists() else {}
    extracted = json.loads((_OUT_DIR / "extracted.json").read_text(encoding="utf-8")) if (_OUT_DIR / "extracted.json").exists() else {}
    profile = json.loads((_OUT_DIR / "profile.json").read_text(encoding="utf-8"))

    _PDF_DIR.mkdir(parents=True, exist_ok=True)
    ats_reports: dict[str, dict] = {}

    for job_key, resume in resumes.items():
        pdf_path, doc = render_resume(job_key, resume, profile)
        skills = extracted.get(job_key, {}).get("skills", [])
        report = run_ats_check(job_key, pdf_path, doc, skills, profile)
        ats_reports[job_key] = report
        status = "PASS" if report["passed"] else "FAIL"
        n_crit = sum(1 for i in report["issues"] if i["severity"] == "critical")
        n_warn = sum(1 for i in report["issues"] if i["severity"] == "warning")
        print(f"{job_key}: resume -> {pdf_path.name} [{status}] score={report['score']:.2f} critical={n_crit} warning={n_warn}")

        if job_key in covers:
            cover_pdf = render_cover(job_key, covers[job_key], profile)
            print(f"{job_key}: cover -> {cover_pdf.name}")

    (_OUT_DIR / "ats_reports.json").write_text(json.dumps(ats_reports, indent=2), encoding="utf-8")
    print(f"\nwrote {_OUT_DIR / 'ats_reports.json'}")


if __name__ == "__main__":
    main()
