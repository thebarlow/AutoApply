"""
Render resume markdown(s) to PDF using the current template and open them for inspection.

Usage:
    python tests/render_preview.py                              # uses tests/fixtures/sample_resume.md
    python tests/render_preview.py a.md b.md c.md              # copies each to fixtures/ then renders all

Run from the 2_generator/ directory. Clears fixtures/outputs/ on each run.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).parent.parent
TEMPLATE = GENERATOR_DIR / "resume_template.tex"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
OUTPUTS_DIR = FIXTURES_DIR / "outputs"



def render(fixture_md: Path) -> Path | None:
    output_pdf = OUTPUTS_DIR / fixture_md.with_suffix(".pdf").name
    print(f"Rendering {fixture_md.name} -> outputs/{output_pdf.name} ...")
    result = subprocess.run(
        [
            "pandoc", str(fixture_md),
            "-o", str(output_pdf),
            "--pdf-engine=xelatex",
            f"--template={TEMPLATE}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: pandoc failed on {fixture_md.name}:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return None
    return output_pdf


def main() -> None:
    if not TEMPLATE.exists():
        print(f"ERROR: template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1:
        fixture_mds = []
        for arg in sys.argv[1:]:
            source = Path(arg)
            if not source.exists():
                print(f"ERROR: file not found: {source}", file=sys.stderr)
                sys.exit(1)
            dest = FIXTURES_DIR / source.name
            if source.resolve() != dest.resolve():
                shutil.copy2(source, dest)
                print(f"Copied {source} -> fixtures/{source.name}")
            fixture_mds.append(dest)
    else:
        fixture_mds = sorted(FIXTURES_DIR.glob("*.md"))
        if not fixture_mds:
            print(f"ERROR: no .md files found in {FIXTURES_DIR}", file=sys.stderr)
            sys.exit(1)

    if OUTPUTS_DIR.exists():
        shutil.rmtree(OUTPUTS_DIR)
    OUTPUTS_DIR.mkdir()
    print("Cleared fixtures/outputs/")

    errors = []
    for fixture_md in fixture_mds:
        pdf = render(fixture_md)
        if pdf is None:
            errors.append(fixture_md.name)
        else:
            os.startfile(pdf)

    print(f"\nDone. {len(fixture_mds) - len(errors)}/{len(fixture_mds)} succeeded.")
    if errors:
        print(f"Failed: {', '.join(errors)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
