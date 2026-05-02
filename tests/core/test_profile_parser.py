import pytest
from core.profile_parser import markdown_to_profile

SAMPLE_MD = """
John Doe
john@example.com | (555) 123-4567 | New York, NY

## Skills
Python, SQL, FastAPI, Docker

## Experience
Software Engineer at Acme Corp (2022-01–2024-03)
- Built internal APIs using FastAPI.
- Reduced query time by 40%.

## Education
B.S. in Computer Science, Columbia University (2018)
GPA: 3.7
"""


def test_extracts_email():
    result = markdown_to_profile(SAMPLE_MD)
    assert result["email"] == "john@example.com"


def test_extracts_phone():
    result = markdown_to_profile(SAMPLE_MD)
    assert "555" in result["phone"]


def test_extracts_name():
    result = markdown_to_profile(SAMPLE_MD)
    assert result["name"] == "John Doe"


def test_extracts_skills():
    result = markdown_to_profile(SAMPLE_MD)
    assert "Python" in result["skills"]
    assert "SQL" in result["skills"]


def test_extracts_work_history():
    result = markdown_to_profile(SAMPLE_MD)
    assert len(result["work_history"]) == 1
    entry = result["work_history"][0]
    assert entry["title"] == "Software Engineer"
    assert entry["company"] == "Acme Corp"
    assert entry["start"] == "2022-01"
    assert entry["end"] == "2024-03"
    assert "FastAPI" in entry["summary"]


def test_extracts_education():
    result = markdown_to_profile(SAMPLE_MD)
    assert len(result["education"]) == 1
    edu = result["education"][0]
    assert edu["institution"] == "Columbia University"
    assert edu["degree"] == "B.S."
    assert edu["field"] == "Computer Science"
    assert edu["graduated"] == "2018"
    assert edu["gpa"] == pytest.approx(3.7)


def test_returns_defaults_for_missing_sections():
    result = markdown_to_profile("Jane Smith\njane@example.com")
    assert result["skills"] == []
    assert result["work_history"] == []
    assert result["education"] == []
    assert result["target_roles"] == []
    assert result["target_salary_min"] is None
    assert result["target_salary_max"] is None
