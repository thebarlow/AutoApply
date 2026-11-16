"""Serve workflow output as a browsable local HTML page.

Renders the JSON produced by other `workflows/` scripts (default:
`workflows/output/recent_jobs.json`) into a static HTML page, then serves
`workflows/output/` on localhost via the stdlib HTTP server. Local-only —
no new dependencies, nothing added to the FastAPI app.

Usage:
    python -m workflows.view_output
    python -m workflows.view_output --file workflows/output/recent_jobs.json --port 8765
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
_DEFAULT_PORT = 8765


def _highlight_description(description: str, terms: list[str]) -> str:
    """Escape description text and wrap occurrences of `terms` in <mark>."""
    escaped = html.escape(description)
    # Longest-first so e.g. "REST API" wins over "REST" when both are present.
    for term in sorted({t for t in terms if t.strip()}, key=len, reverse=True):
        pattern = re.escape(html.escape(term))
        escaped = re.sub(
            rf"(?i)(?<![\w>])({pattern})(?![\w<])",
            r"<mark>\1</mark>",
            escaped,
        )
    return escaped


def _chip_list(label: str, values: list[str]) -> str:
    if not values:
        return ""
    chips = "".join(f'<span class="chip">{html.escape(v)}</span>' for v in values)
    return f'<div class="field"><span class="field-label">{html.escape(label)}</span><div class="chips">{chips}</div></div>'


def _phrase_list(label: str, values: list[str]) -> str:
    if not values:
        return ""
    items = "".join(f"<li>{html.escape(v)}</li>" for v in values)
    return f'<div class="field"><span class="field-label">{html.escape(label)}</span><ul>{items}</ul></div>'


def render_html(jobs: list[dict], extracted: dict[str, dict]) -> str:
    """Render a list of job dicts into a single self-contained HTML page."""
    cards = []
    for job in jobs:
        meta = " &middot; ".join(
            html.escape(str(job.get(field) or "—"))
            for field in ("company", "location", "source", "state", "scraped_at")
        )
        ext = extracted.get(job.get("job_key", ""), {})
        description_raw = job.get("description") or ""

        highlight_terms = [
            *ext.get("required_skills", []),
            *ext.get("preferred_skills", []),
            *ext.get("tech_stack", []),
        ]
        description = (
            _highlight_description(description_raw, highlight_terms)
            if description_raw
            else "(no description)"
        )

        salary_line = ""
        if ext.get("salary_min") or ext.get("salary_max"):
            currency = ext.get("salary_currency") or ""
            salary_line = (
                f'<div class="field"><span class="field-label">Salary</span>'
                f'<span class="salary">{currency} {ext.get("salary_min", "?"):,.0f} '
                f'&ndash; {ext.get("salary_max", "?"):,.0f}</span></div>'
            )

        badges = "".join(
            f'<span class="badge">{html.escape(str(ext[f]))}</span>'
            for f in ("seniority", "role_type", "domain", "work_arrangement", "employment_type")
            if ext.get(f) and ext[f] != "not specified"
        )

        highlights = "".join(
            [
                salary_line,
                badges and f'<div class="field"><span class="field-label">Signals</span><div class="chips">{badges}</div></div>',
                _chip_list("Required skills", ext.get("required_skills", [])),
                _chip_list("Preferred skills", ext.get("preferred_skills", [])),
                _chip_list("Tech stack", ext.get("tech_stack", [])),
                _phrase_list("Key responsibilities", ext.get("key_responsibilities", [])),
                _phrase_list("Company signals", ext.get("company_signals", [])),
            ]
        )
        highlights_block = f'<div class="highlights">{highlights}</div>' if highlights else ""

        cards.append(f"""
        <details class="job" open>
          <summary>
            <span class="title">{html.escape(job.get("title") or job.get("job_key", ""))}</span>
            <span class="meta">{meta}</span>
          </summary>
          {highlights_block}
          <pre>{description}</pre>
        </details>
        """)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Job output ({len(jobs)})</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  .job {{ border: 1px solid #ccc; border-radius: 6px; margin-bottom: 0.75rem; padding: 0.5rem 1rem; }}
  summary {{ cursor: pointer; display: flex; flex-direction: column; gap: 0.15rem; }}
  .title {{ font-weight: 600; }}
  .meta {{ color: #666; font-size: 0.85rem; }}
  pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 0.9rem; }}
  mark {{ background: #fff2a8; padding: 0 2px; border-radius: 2px; }}
  .highlights {{ background: #f7f7f9; border-radius: 4px; padding: 0.5rem 0.75rem; margin: 0.5rem 0; }}
  .field {{ margin-bottom: 0.4rem; }}
  .field-label {{ font-weight: 600; font-size: 0.8rem; text-transform: uppercase; color: #555; display: block; margin-bottom: 0.15rem; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 0.3rem; }}
  .chip {{ background: #e3ecff; color: #1a3a8f; border-radius: 12px; padding: 0.1rem 0.6rem; font-size: 0.8rem; }}
  .badge {{ background: #ddd; border-radius: 12px; padding: 0.1rem 0.6rem; font-size: 0.8rem; }}
  .salary {{ font-weight: 600; color: #1a7a3a; }}
  .field ul {{ margin: 0.1rem 0 0 1.1rem; padding: 0; font-size: 0.85rem; }}
</style>
</head>
<body>
  <h1>Job output ({len(jobs)})</h1>
  {"".join(cards)}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=_DEFAULT_FILE, help="Input JSON produced by a workflows script.")
    parser.add_argument("--extracted", type=Path, default=_DEFAULT_EXTRACTED, help="Extraction JSON keyed by job_key.")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"{args.file} not found — run a workflows fetch script first.")

    jobs = json.loads(args.file.read_text(encoding="utf-8"))
    extracted = json.loads(args.extracted.read_text(encoding="utf-8")) if args.extracted.exists() else {}
    out_html = args.file.parent / "index.html"
    out_html.write_text(render_html(jobs, extracted), encoding="utf-8")

    url = f"http://localhost:{args.port}/index.html"
    print(f"serving {args.file.parent}/ at {url} (ctrl+c to stop)")
    if not args.no_browser:
        webbrowser.open(url)

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(args.file.parent), **kw)
    with http.server.ThreadingHTTPServer(("localhost", args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
