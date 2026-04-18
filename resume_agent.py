"""
Resume and cover letter generator for pending job postings.

Reads JSON job files from jobs/pending/, calls Claude Code non-interactively
to generate tailored markdown resume and cover letter for each, writes outputs
to jobs/outputs/, then moves the JSON to jobs/processed/.

Usage:
    python resume_agent.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

MASTER_RESUME = Path(r"C:\Users\barlo\Personal\Resume\master_resume.md")
PENDING_DIR = Path("jobs/pending")
PROCESSED_DIR = Path("jobs/processed")
OUTPUTS_DIR = Path("jobs/outputs")

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
- Output ONLY the resume Markdown. No preamble, no explanation.
- Keep it to one page when rendered (be concise).
- Reorder and emphasize skills and projects that match this specific job.
- Drop the Soft Skills section entirely.
- Update the location line to: Vero Beach, FL 32963 — open to relocation
- Do not invent experience or skills not in the master resume.
- Keep all section headers from the master resume except Soft Skills.
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
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def process_job(job_path: Path, master_resume: str) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))

    job_key = job_path.stem  # e.g. "remotive_2069747"
    resume_out = OUTPUTS_DIR / f"{job_key}_resume.md"
    cover_out = OUTPUTS_DIR / f"{job_key}_cover.md"

    # Skip if already processed.
    if resume_out.exists() and cover_out.exists():
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
    resume_out.write_text(resume_md, encoding="utf-8")

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

    # Move JSON to processed only after both outputs are written.
    shutil.move(str(job_path), PROCESSED_DIR / job_path.name)
    print(f"  [done]   {job_key} → jobs/processed/")


def main() -> None:
    if not MASTER_RESUME.exists():
        print(f"ERROR: master resume not found at {MASTER_RESUME}", file=sys.stderr)
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
