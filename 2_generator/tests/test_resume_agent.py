"""
Unit and integration tests for resume_agent.py.

Unit tests cover pure/logic functions with no external dependencies.
Integration test verifies the full pandoc+xelatex render pipeline using the
existing sample fixture.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Resolve paths relative to this file so tests run from any cwd.
GENERATOR_DIR = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_RESUME_MD = FIXTURES_DIR / "sample_resume.md"
TEMPLATE = GENERATOR_DIR / "resume_template.tex"

sys.path.insert(0, str(GENERATOR_DIR))
import resume_agent  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests: strip_header_block
# ---------------------------------------------------------------------------

class TestStripHeaderBlock:
    def test_no_header_returns_content_unchanged(self):
        md = "## Profile\n\nSome content here.\n\n## Education\n\nStuff."
        assert resume_agent.strip_header_block(md) == md

    def test_strips_name_and_contact_lines_before_first_section(self):
        md = (
            "# Matthew Barlow\n"
            "hireme@matthewbarlow.me | (203) 617-7390\n"
            "\n"
            "## Profile\n"
            "\n"
            "Engineer with experience in X."
        )
        result = resume_agent.strip_header_block(md)
        assert result.startswith("## Profile")
        assert "Matthew Barlow" not in result

    def test_strips_yaml_style_header_before_first_section(self):
        md = (
            "Matthew Barlow\n"
            "Email: foo@bar.com\n"
            "Phone: 555-1234\n"
            "## Profile\n"
            "Content."
        )
        result = resume_agent.strip_header_block(md)
        assert result.startswith("## Profile")

    def test_stops_stripping_at_line_10_if_no_section_found(self):
        # 12 non-section lines — should return from line 10 onward, not strip everything.
        lines = [f"line{i}" for i in range(12)]
        md = "\n".join(lines)
        result = resume_agent.strip_header_block(md)
        # Lines from index 10 onward must be present.
        assert "line10" in result
        assert "line11" in result

    def test_empty_string_returns_empty(self):
        assert resume_agent.strip_header_block("") == ""

    def test_single_section_header_preserved(self):
        md = "## Skills\n\nPython, Go"
        assert resume_agent.strip_header_block(md) == md


# ---------------------------------------------------------------------------
# Unit tests: process_job (mocked I/O and subprocesses)
# ---------------------------------------------------------------------------

class TestProcessJob:
    def _make_job_file(self, tmp_path: Path) -> Path:
        job = {
            "title": "Software Engineer",
            "company": "Acme",
            "location": "Remote",
            "description": "Build things with Python.",
        }
        job_file = tmp_path / "acme_12345.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        return job_file

    def test_writes_resume_and_cover_outputs(self, tmp_path):
        job_file = self._make_job_file(tmp_path)
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        with (
            patch.object(resume_agent, "OUTPUTS_DIR", outputs_dir),
            patch.object(resume_agent, "PROCESSED_DIR", processed_dir),
            patch.object(resume_agent, "run_claude", return_value="## Profile\n\nFake resume."),
            patch.object(resume_agent, "render_pdf"),
        ):
            resume_agent.process_job(job_file, master_resume="Fake master resume.")

        assert (outputs_dir / "acme_12345_resume.md").exists()
        assert (outputs_dir / "acme_12345_cover.md").exists()

    def test_moves_json_to_processed_after_success(self, tmp_path):
        job_file = self._make_job_file(tmp_path)
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        with (
            patch.object(resume_agent, "OUTPUTS_DIR", outputs_dir),
            patch.object(resume_agent, "PROCESSED_DIR", processed_dir),
            patch.object(resume_agent, "run_claude", return_value="## Profile\n\nFake."),
            patch.object(resume_agent, "render_pdf"),
        ):
            resume_agent.process_job(job_file, master_resume="Fake master resume.")

        assert not job_file.exists()
        assert (processed_dir / "acme_12345.json").exists()

    def test_skips_job_when_outputs_already_exist(self, tmp_path):
        job_file = self._make_job_file(tmp_path)
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        # Pre-create both output files to trigger the skip path.
        (outputs_dir / "acme_12345_resume.md").write_text("existing", encoding="utf-8")
        (outputs_dir / "acme_12345_cover.md").write_text("existing", encoding="utf-8")

        with (
            patch.object(resume_agent, "OUTPUTS_DIR", outputs_dir),
            patch.object(resume_agent, "PROCESSED_DIR", processed_dir),
            patch.object(resume_agent, "run_claude") as mock_claude,
        ):
            resume_agent.process_job(job_file, master_resume="Fake master resume.")
            mock_claude.assert_not_called()

    def test_resume_md_contains_frontmatter(self, tmp_path):
        job_file = self._make_job_file(tmp_path)
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        with (
            patch.object(resume_agent, "OUTPUTS_DIR", outputs_dir),
            patch.object(resume_agent, "PROCESSED_DIR", processed_dir),
            patch.object(resume_agent, "run_claude", return_value="## Profile\n\nFake."),
            patch.object(resume_agent, "render_pdf"),
        ):
            resume_agent.process_job(job_file, master_resume="Fake master resume.")

        content = (outputs_dir / "acme_12345_resume.md").read_text(encoding="utf-8")
        assert "name: Matthew Barlow" in content
        assert content.startswith("---")


# ---------------------------------------------------------------------------
# Integration test: PDF render pipeline
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPdfRender:
    def test_sample_fixture_renders_to_pdf(self, tmp_path):
        """Render sample_resume.md with the real template; assert a non-empty PDF is produced."""
        if not SAMPLE_RESUME_MD.exists():
            pytest.skip("sample fixture not found")
        if not TEMPLATE.exists():
            pytest.skip("LaTeX template not found")

        # Check pandoc is available.
        if subprocess.run(["pandoc", "--version"], capture_output=True).returncode != 0:
            pytest.skip("pandoc not available")

        output_pdf = tmp_path / "sample_resume.pdf"
        result = subprocess.run(
            [
                "pandoc", str(SAMPLE_RESUME_MD),
                "-o", str(output_pdf),
                "--pdf-engine=xelatex",
                f"--template={TEMPLATE}",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"pandoc failed:\n{result.stderr}"
        assert output_pdf.exists(), "PDF not created"
        assert output_pdf.stat().st_size > 1000, "PDF suspiciously small"
