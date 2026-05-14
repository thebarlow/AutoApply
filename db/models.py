from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text

from db.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    job_key = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean)
    description = Column(Text)
    url = Column(String, unique=True, nullable=False)
    posted_at = Column(String)
    scraped_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    state = Column(String, nullable=False, default="draft")
    desirability_score = Column(Float)
    fit_score = Column(Float)
    final_score = Column(Float)
    score_justification = Column(Text)
    resume_path = Column(String)
    cover_path = Column(String)
    extraction_json = Column(Text)
    applied_at = Column(String)
    sheets_row_id = Column(String)


class FieldHelp(Base):
    __tablename__ = "field_help"

    table_name = Column(String, primary_key=True)
    column_name = Column(String, primary_key=True)
    description = Column(Text, nullable=False, default="")


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text)


class UserProfileModel(Base):
    __tablename__ = "user_profile"
    # extend_existing allows core.user.User and this class to share the same table
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="Default")
    data = Column(Text, nullable=False)
