from __future__ import annotations


def test_resume_eval_prompt_v2_migration(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import core.job   # noqa: F401
    import core.user  # noqa: F401
    from db.database import Base, PromptDefault, Prompt, Config
    import db.database as dbmod

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    # Seed stale default + profile prompt.
    session.add(PromptDefault(type_key="resume_eval", content="OLD eval prompt"))
    session.add(Prompt(profile_id=1, type_key="resume_eval", content="OLD", model=""))
    session.commit()

    monkeypatch.setattr(dbmod, "SessionLocal", lambda: session, raising=True)
    monkeypatch.setattr(session, "close", lambda: None, raising=False)

    dbmod._migrate_resume_eval_prompt_v2()

    default = session.query(PromptDefault).filter_by(type_key="resume_eval").first()
    prof = session.query(Prompt).filter_by(profile_id=1, type_key="resume_eval").first()
    assert default.content != "OLD eval prompt"
    assert prof.content == default.content
    assert session.query(Config).filter_by(key="resume_eval_prompt_v2").first().value == "1"

    # Idempotent: a second run does not overwrite a later user edit.
    prof.content = "user edited"
    session.commit()
    dbmod._migrate_resume_eval_prompt_v2()
    assert session.query(Prompt).filter_by(profile_id=1, type_key="resume_eval").first().content == "user edited"
