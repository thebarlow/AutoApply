from db.database import _seed_skill_match_prompt, PromptDefault, SessionLocal


def test_seed_skill_match_prompt_idempotent(tmp_path, monkeypatch):
    _seed_skill_match_prompt()
    _seed_skill_match_prompt()  # second call must not duplicate
    db = SessionLocal()
    try:
        rows = db.query(PromptDefault).filter_by(type_key="skill_match").all()
        assert len(rows) == 1
        assert "{skills_to_match}" in rows[0].content
    finally:
        db.close()
