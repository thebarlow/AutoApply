from pathlib import Path


def test_extraction_prompt_excludes_non_skills():
    text = Path("prompts/defaults/extraction.md").read_text(encoding="utf-8").lower()
    # The prompt must instruct the model to keep credentials/titles out of skills.
    assert "degree" in text
    assert "title" in text
