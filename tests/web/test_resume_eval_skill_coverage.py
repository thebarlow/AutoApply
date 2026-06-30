from pathlib import Path


def test_resume_eval_prompt_grounds_in_candidate_skills_and_keyword_coverage():
    """The eval prompt scores document quality for THIS candidate (not job fit):
    it grounds in the candidate's real skill inventory, only credits skills the
    candidate actually has, and never deducts for genuinely-absent required skills.
    """
    content = Path("prompts/defaults/resume_eval.md").read_text(encoding="utf-8")
    # Grounded in the candidate's own skill inventory.
    assert "Skills: {user.skills}" in content
    # keyword_coverage only flags skills the candidate genuinely has.
    assert "keyword_coverage" in content
    assert "skill the candidate ACTUALLY HAS" in content
    # Quality-not-fit: absent required skills are not a document defect.
    assert "NEVER lower the score because a job-required skill is absent" in content
