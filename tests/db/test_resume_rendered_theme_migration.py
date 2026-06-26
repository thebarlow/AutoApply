from core.job import Job


def test_job_has_resume_rendered_theme_column():
    assert "resume_rendered_theme" in Job.__table__.columns


def test_column_is_nullable_string():
    col = Job.__table__.columns["resume_rendered_theme"]
    assert col.nullable is True
