from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

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
    extraction_md = Column(Text)
    applied_at = Column(String)
    sheets_row_id = Column(String)


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text)


class UserProfileModel(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="Default")
    data = Column(Text, nullable=False)
