import json
import pytest
from unittest.mock import MagicMock, patch

from core.profile_parser import markdown_to_profile, pdf_to_markdown


SAMPLE_PROFILE = {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "(555) 123-4567",
    "location": "New York, NY",
    "skills": ["Python", "SQL"],
    "work_history": [
        {"title": "Engineer", "company": "Acme", "start": "2022-01", "end": "2024-03", "summary": "Built APIs."}
    ],
    "education": [
        {"institution": "Columbia University", "degree": "B.S.", "field": "Computer Science", "graduated": "2018", "gpa": 3.7}
    ],
}


def _make_db():
    return MagicMock()


def _make_llm_response(content: str):
    """Build a mock openai ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def test_returns_llm_parsed_fields():
    db = _make_db()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(json.dumps(SAMPLE_PROFILE))

    with patch("core.profile_parser.get_openai_client", return_value=(mock_client, "test-model")):
        result = markdown_to_profile("resume text", db)

    assert result["name"] == "John Doe"
    assert result["email"] == "john@example.com"
    assert "Python" in result["skills"]
    assert result["work_history"][0]["company"] == "Acme"
    assert result["education"][0]["institution"] == "Columbia University"


def test_includes_default_fields_not_in_llm_response():
    db = _make_db()
    partial = {"name": "Jane", "email": "j@j.com", "phone": "", "location": "",
               "skills": [], "work_history": [], "education": []}
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(json.dumps(partial))

    with patch("core.profile_parser.get_openai_client", return_value=(mock_client, "test-model")):
        result = markdown_to_profile("resume text", db)

    assert result["target_salary_min"] is None
    assert result["target_salary_max"] is None
    assert result["target_roles"] == []
    assert result["resume_path"] == ""
    assert result["md_path"] == ""
    assert result["name"] == "Jane"
    assert result["email"] == "j@j.com"


def test_raises_value_error_on_invalid_json():
    db = _make_db()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response("not json at all")

    with patch("core.profile_parser.get_openai_client", return_value=(mock_client, "test-model")):
        with pytest.raises(ValueError, match="LLM returned invalid JSON"):
            markdown_to_profile("resume text", db)


def test_raises_runtime_error_when_no_provider():
    db = _make_db()
    with patch("core.profile_parser.get_openai_client", side_effect=RuntimeError("No active LLM provider configured")):
        with pytest.raises(RuntimeError, match="No active LLM provider"):
            markdown_to_profile("resume text", db)


def test_strips_markdown_fences_from_llm_response():
    """LLMs sometimes wrap JSON in ```json ... ``` fences."""
    db = _make_db()
    fenced = f"```json\n{json.dumps(SAMPLE_PROFILE)}\n```"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(fenced)

    with patch("core.profile_parser.get_openai_client", return_value=(mock_client, "test-model")):
        result = markdown_to_profile("resume text", db)

    assert result["name"] == "John Doe"
    assert result["email"] == "john@example.com"


# ---- pdf_to_markdown (unchanged) ----

def _make_mock_pdf(pages_text: list):
    mock_pdf = MagicMock()
    mock_pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        mock_pages.append(page)
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


def test_pdf_to_markdown_extracts_text():
    page_text = "WORK EXPERIENCE\nSoftware Engineer at Acme (2022-2024)\n• Built APIs"
    mock_pdf = _make_mock_pdf([page_text])

    with patch("core.profile_parser.pdfplumber.open", return_value=mock_pdf):
        result = pdf_to_markdown(b"fake-pdf-bytes")

    assert "## Work Experience" in result
    assert "Software Engineer" in result
    assert "- Built APIs" in result


def test_pdf_to_markdown_handles_empty_page():
    mock_pdf = _make_mock_pdf([None])
    with patch("core.profile_parser.pdfplumber.open", return_value=mock_pdf):
        result = pdf_to_markdown(b"fake-pdf-bytes")
    assert result == ""
