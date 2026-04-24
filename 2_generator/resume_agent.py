"""
Resume and cover letter generator for pending job postings.

Reads JSON job files from jobs/pending/, calls Claude Code non-interactively
to generate tailored markdown resume and cover letter for each, renders the
resume to PDF via Pandoc+XeLaTeX, then moves the JSON to jobs/processed/.

Usage:
    python resume_agent.py
"""

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Force utf-8 on Windows console so non-ASCII job titles don't crash prints.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

MASTER_RESUME = Path(r"C:\Users\barlo\Personal\Resume\master_resume.md")
ROOT = Path(__file__).parent.parent
PENDING_DIR = ROOT / "jobs/pending"
PROCESSED_DIR = ROOT / "jobs/processed"
OUTPUTS_DIR = ROOT / "jobs/outputs"
TEMPLATE = Path(__file__).parent / "resume_template.tex"

FRONTMATTER = """\
---
name: Matthew Barlow
email: hireme@matthewbarlow.me
phone: (203) 617-7390
location: Vero Beach, FL --- open to relocation
github: github.com/thebarlow
linkedin: linkedin.com/in/matthew-barlow-433492199
website: matthewbarlow.me
---

"""

RESUME_PROMPT_TEMPLATE = """
You are writing a tailored one-page resume in Markdown for a job application.

# Master Resume
{master_resume}

# Job Posting
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

# Instructions
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block — those are handled separately.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Do not invent experience or skills not in the master resume.
- Drop the Soft Skills section entirely.

## Profile
- Max 500 characters total.

## Education
- Always include both degrees exactly as written. No bullets.

## Experience
- Always include all 3 entries.
- Max 2 bullets per entry, each bullet max 120 characters.
- Stress skills and responsibilities directly mentioned in the job description.

## Projects
- Reorder by relevance to this job. Drop least relevant project(s) if needed.
- Always include at least 2, max 4 projects.
- 1 bullet per project, max 120 characters.

## Skills
- Always include Python, Git, Docker, SQL regardless of job description.
- Include only categories that have 2 or more relevant skills for this job.
- If a category has only 1 relevant skill, fold it into the nearest adjacent category.
- Sort categories by relevance to the job description.
- Within each category, list skills directly mentioned in the job description first.
- Max 6 categories.
""".strip()

COVER_PROMPT_TEMPLATE = """
You are writing a concise cover letter in Markdown for a job application.

# Master Resume
{master_resume}

# Job Posting
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

# Instructions
- Output ONLY the cover letter Markdown. No preamble, no explanation.
- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
- Address it to the hiring team at {company}.
- Sign off as Matthew Barlow with contact info from the master resume.
- Do not mention n8n or any no-code tools.
- Do not invent experience or skills not in the master resume.
""".strip()


def run_claude(prompt: str) -> str:
    """Run a non-interactive Claude Code session and return stdout."""
    result = subprocess.run(
        ["claude", "-p", "-"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def strip_header_block(md: str) -> str:
    """Remove name/contact header if Claude included one despite instructions."""
    lines = md.splitlines()
    i = 0
    # Strip a leading YAML frontmatter block (--- ... ---) if present.
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    # Then drop any remaining non-section lines until ## or line 10.
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            break
        if i >= 10:
            break
        i += 1
    return "\n".join(lines[i:])


def render_pdf(md_path: Path, pdf_path: Path) -> None:
    """Render a markdown resume to PDF via Pandoc and XeLaTeX."""
    subprocess.run(
        [
            "pandoc", str(md_path),
            "-o", str(pdf_path),
            "--pdf-engine=xelatex",
            f"--template={TEMPLATE}",
        ],
        check=True,
    )


def process_job(job_path: Path, master_resume: str) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))

    job_key = job_path.stem  # e.g. "remotive_2069747"
    resume_md_out = OUTPUTS_DIR / f"{job_key}_resume.md"
    resume_pdf_out = OUTPUTS_DIR / f"{job_key}_resume.pdf"
    cover_out = OUTPUTS_DIR / f"{job_key}_cover.md"

    # Skip if already processed.
    if resume_md_out.exists() and cover_out.exists():
        print(f"  [skip] {job_key} — outputs already exist")
        return

    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    description = job.get("description", "")

    print(f"  [resume] {job_key} — {title} @ {company}")
    resume_md = run_claude(
        RESUME_PROMPT_TEMPLATE.format(
            master_resume=master_resume,
            title=title,
            company=company,
            location=location,
            description=description,
        )
    )
    resume_md = strip_header_block(resume_md)
    resume_md_out.write_text(FRONTMATTER + resume_md, encoding="utf-8")

    print(f"  [pdf]    {job_key}")
    render_pdf(resume_md_out, resume_pdf_out)

    print(f"  [cover]  {job_key}")
    cover_md = run_claude(
        COVER_PROMPT_TEMPLATE.format(
            master_resume=master_resume,
            title=title,
            company=company,
            location=location,
            description=description,
        )
    )
    cover_out.write_text(cover_md, encoding="utf-8")

    # Move JSON to processed only after all outputs are written.
    shutil.move(str(job_path), PROCESSED_DIR / job_path.name)
    print(f"  [done]   {job_key} → jobs/processed/")


def main() -> None:
    if not MASTER_RESUME.exists():
        print(f"ERROR: master resume not found at {MASTER_RESUME}", file=sys.stderr)
        sys.exit(1)

    if not TEMPLATE.exists():
        print(f"ERROR: LaTeX template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    master_resume = MASTER_RESUME.read_text(encoding="utf-8")
    pending = sorted(PENDING_DIR.glob("*.json"))

    if not pending:
        print("No pending jobs.")
        return

    print(f"Processing {len(pending)} job(s)...")
    errors = []
    for job_path in pending:
        try:
            process_job(job_path, master_resume)
        except Exception as e:
            print(f"  [error]  {job_path.stem}: {e}", file=sys.stderr)
            errors.append(job_path.stem)

    print(f"\nDone. {len(pending) - len(errors)}/{len(pending)} succeeded.")
    if errors:
        print(f"Failed: {', '.join(errors)}")


if __name__ == "__main__":
    main()
