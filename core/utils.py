from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def render_pdf(md_path: Path, pdf_path: Path, template_path: Path) -> None:
    """Invoke pandoc/xelatex to render a PDF from a markdown file.

    Args:
        md_path: Path to the source markdown file.
        pdf_path: Destination path for the rendered PDF.
        template_path: Path to the LaTeX template file.

    Raises:
        subprocess.CalledProcessError: If pandoc exits with a non-zero code.
    """
    subprocess.run(
        [
            "pandoc", str(md_path),
            "-o", str(pdf_path),
            "--pdf-engine=xelatex",
            f"--template={template_path}",
        ],
        check=True,
    )


def _get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF using pdfinfo."""
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"Could not determine page count for {pdf_path.name}")


def render_resume_pdf(
    md_path: Path,
    pdf_path: Path,
    job_key: str,
    template_path: Path,
) -> None:
    """Render a resume PDF, shrinking font and margins to fit one page if needed.

    Tries up to three progressively tighter layouts before raising.

    Args:
        md_path: Path to the source markdown file.
        pdf_path: Destination path for the rendered PDF.
        job_key: Job identifier used in error messages.
        template_path: Path to the LaTeX template file.

    Raises:
        RuntimeError: If the resume cannot fit on one page at minimum settings.
    """
    attempts = [
        {"fontsize": "11pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "0.8in", "bottom": "0.8in"},
    ]
    template_text = template_path.read_text(encoding="utf-8")
    for s in attempts:
        modified = re.sub(
            r"\\documentclass\[\d+pt\]",
            f"\\\\documentclass[{s['fontsize']}]",
            template_text,
        )
        modified = re.sub(
            r"top=[\d.]+in, bottom=[\d.]+in",
            f"top={s['top']}, bottom={s['bottom']}",
            modified,
        )
        with tempfile.NamedTemporaryFile(
            suffix=".tex", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(modified)
            tmp = Path(f.name)
        try:
            render_pdf(md_path, pdf_path, tmp)
            if _get_page_count(pdf_path) <= 1:
                return
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(
        f"Resume '{job_key}' exceeds 1 page at minimum settings (10pt, 0.8in margins)."
    )


def strip_header_block(md: str) -> str:
    """Remove a name/contact header block from LLM-generated resume markdown.

    Scans past any YAML front matter and any leading non-section lines,
    returning content starting from the first '## ' section header.

    Args:
        md: Raw markdown string, possibly with a header block.

    Returns:
        Markdown string starting from the first section header.
    """
    if not md:
        return md
    lines = md.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    while i < len(lines):
        if lines[i].strip().startswith("## "):
            break
        if i >= 10:
            break
        i += 1
    return "\n".join(lines[i:])
