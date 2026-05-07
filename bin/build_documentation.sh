#!/usr/bin/env bash
# Generates docs/index.html from all markdown files in docs/
# Run whenever you add or update documentation files.

set -euo pipefail
cd "$(dirname "$0")/.."

# Resolve the venv python — follow symlink if .venv is one
VENV_DIR="$(readlink -f .venv 2>/dev/null || echo .venv)"
PYTHON="${VENV_DIR}/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

"$PYTHON" - <<'PYEOF'
import os, re, pathlib, markdown

ROOT    = pathlib.Path(".")
DOCS    = ROOT / "docs"
BIN     = ROOT / "bin"
OUTPUT  = DOCS / "index.html"

md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])

# ---------- collect markdown files ----------
EXCLUDE = {"index.html"}
md_files = sorted(
    f for f in DOCS.glob("*.md")
    if f.name not in EXCLUDE
)

# ---------- collect bin scripts ----------
bin_files = sorted(
    f for f in BIN.iterdir()
    if f.is_file()
) if BIN.exists() else []

# ---------- build sections ----------
sections = []

# Overview — pulled from CLAUDE.md project description
claude_md = ROOT / "CLAUDE.md"
if claude_md.exists():
    txt = claude_md.read_text()
    overview_match = re.search(r"## Project Overview(.*?)(?=\n## )", txt, re.DOTALL)
    overview_text = overview_match.group(1).strip() if overview_match else ""
else:
    overview_text = ""

sections.append({
    "id":    "overview",
    "title": "Overview",
    "html":  md.convert(overview_text) if overview_text else "<p>AutoApply is an automated job application pipeline.</p>",
})
md.reset()

for f in md_files:
    slug  = f.stem.lower().replace("_", "-")
    title = f.stem.replace("_", " ").title()
    html  = md.convert(f.read_text())
    md.reset()
    sections.append({"id": slug, "title": title, "html": html})

# Bin scripts section
if bin_files:
    rows = "\n".join(
        f'<tr><td><code>{f.name}</code></td>'
        f'<td><a href="../bin/{f.name}" target="_blank">view</a></td>'
        f'<td>{f.stat().st_size:,} bytes</td></tr>'
        for f in bin_files
    )
    bin_html = f"""
<p>Utility scripts in <code>bin/</code>. Run from the project root.</p>
<table>
  <thead><tr><th>Script</th><th>Link</th><th>Size</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""
    sections.append({"id": "bin-scripts", "title": "Bin Scripts", "html": bin_html})

# ---------- sidebar links ----------
sidebar_links = "\n".join(
    f'<a href="#{s["id"]}" class="sidebar-link">{s["title"]}</a>'
    for s in sections
)

# ---------- content sections ----------
content_sections = "\n".join(
    f'<section id="{s["id"]}">\n{s["html"]}\n</section>'
    for s in sections
)

# ---------- render ----------
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Auto Apply — Help</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 14px;
      background: #f5f5f5;
      color: #1a1a1a;
      min-height: 100vh;
    }}

    /* Nav — matches app */
    nav.app-nav {{
      display: flex;
      align-items: center;
      gap: 1.5rem;
      padding: 0 1.5rem;
      height: 48px;
      background: #1a1a1a;
      color: #fff;
    }}
    nav.app-nav a {{ color: #ccc; text-decoration: none; font-size: 14px; }}
    nav.app-nav a:hover {{ color: #fff; }}
    nav.app-nav a.nav-active {{ color: #fff; font-weight: 600; }}
    nav.app-nav .brand {{ font-weight: 700; font-size: 15px; color: #fff; margin-right: auto; }}
    nav.app-nav .nav-right {{ margin-left: auto; }}

    /* Layout */
    .help-layout {{
      display: flex;
      min-height: calc(100vh - 48px);
    }}

    /* Sidebar */
    .help-sidebar {{
      width: 220px;
      flex-shrink: 0;
      background: #fff;
      border-right: 1px solid #e5e5e5;
      padding: 1.5rem 0;
      position: sticky;
      top: 0;
      height: calc(100vh - 48px);
      overflow-y: auto;
    }}
    .sidebar-heading {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: #888;
      padding: 0 1.25rem 0.5rem;
      margin-top: 1rem;
    }}
    .sidebar-heading:first-child {{ margin-top: 0; }}
    a.sidebar-link {{
      display: block;
      padding: 0.4rem 1.25rem;
      color: #444;
      text-decoration: none;
      font-size: 13px;
      border-left: 3px solid transparent;
      transition: background 0.1s, border-color 0.1s;
    }}
    a.sidebar-link:hover {{
      background: #f5f5f5;
      color: #1a1a1a;
      border-left-color: #0a66c2;
    }}
    a.sidebar-link.active {{
      background: #f0f4ff;
      color: #0a66c2;
      font-weight: 600;
      border-left-color: #0a66c2;
    }}

    /* Content */
    .help-content {{
      flex: 1;
      padding: 2rem 2.5rem;
      max-width: 860px;
    }}

    section {{
      margin-bottom: 3rem;
      padding-top: 0.5rem;
    }}

    /* Typography */
    .help-content h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 0.75rem; color: #111; }}
    .help-content h2 {{ font-size: 17px; font-weight: 700; margin: 2rem 0 0.6rem; color: #111; border-bottom: 1px solid #eee; padding-bottom: 0.3rem; }}
    .help-content h3 {{ font-size: 15px; font-weight: 600; margin: 1.25rem 0 0.4rem; color: #333; }}
    .help-content p  {{ line-height: 1.7; margin-bottom: 0.75rem; color: #333; }}
    .help-content ul,
    .help-content ol {{ padding-left: 1.5rem; margin-bottom: 0.75rem; line-height: 1.7; color: #333; }}
    .help-content li {{ margin-bottom: 0.2rem; }}
    .help-content a  {{ color: #0a66c2; text-decoration: none; }}
    .help-content a:hover {{ text-decoration: underline; }}

    /* Code */
    .help-content code {{
      background: #f0f0f0;
      border-radius: 3px;
      padding: 1px 5px;
      font-size: 12.5px;
      font-family: "SFMono-Regular", Consolas, monospace;
      color: #c7254e;
    }}
    .help-content pre {{
      background: #1e1e1e;
      color: #d4d4d4;
      border-radius: 6px;
      padding: 1rem 1.25rem;
      overflow-x: auto;
      margin: 0.75rem 0 1rem;
      font-size: 13px;
      line-height: 1.5;
    }}
    .help-content pre code {{
      background: none;
      color: inherit;
      padding: 0;
      font-size: inherit;
    }}

    /* Tables */
    .help-content table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0.75rem 0 1.25rem;
      font-size: 13px;
      background: #fff;
      border-radius: 6px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    }}
    .help-content th {{
      text-align: left;
      padding: 9px 12px;
      background: #f0f0f0;
      font-weight: 600;
      border-bottom: 1px solid #e0e0e0;
    }}
    .help-content td {{
      padding: 8px 12px;
      border-bottom: 1px solid #f0f0f0;
      vertical-align: top;
    }}
    .help-content tr:last-child td {{ border-bottom: none; }}
  </style>
</head>
<body>

<nav class="app-nav">
  <a class="brand" href="/">Auto Apply</a>
  <a href="/">Dashboard</a>
  <a href="/config">Config</a>
  <a href="/setup">Setup</a>
  <a href="/help" class="nav-active nav-right">Help</a>
</nav>

<div class="help-layout">
  <aside class="help-sidebar">
    <div class="sidebar-heading">Documentation</div>
    {sidebar_links}
  </aside>

  <main class="help-content">
    {content_sections}
  </main>
</div>

<script>
  // Highlight active sidebar link on scroll
  const links = document.querySelectorAll('.sidebar-link');
  const sections = document.querySelectorAll('section[id]');
  const observer = new IntersectionObserver(entries => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id));
      }}
    }});
  }}, {{ rootMargin: '-30% 0px -60% 0px' }});
  sections.forEach(s => observer.observe(s));
</script>

</body>
</html>
"""

OUTPUT.write_text(html)
print(f"Built {OUTPUT}  ({len(sections)} sections)")
PYEOF
