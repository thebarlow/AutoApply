from pathlib import Path


def test_resume_eval_prompt_enforces_present_relevant_skills():
    content = Path("prompts/defaults/resume_eval.md").read_text(encoding="utf-8")
    assert "Skills: {user.skills}" in content
    assert "Hard Skills:" not in content
    assert "MUST appear in the resume" in content
    assert "highest priority" in content
    assert "transferable adjacent skills" in content
