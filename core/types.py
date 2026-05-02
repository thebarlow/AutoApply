from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobState(str, Enum):
    PENDING = "pending"
    SCRAPED = "scraped"
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class WorkHistoryEntry:
    company: str
    title: str
    start: str
    end: str
    summary: str


@dataclass
class EducationEntry:
    institution: str
    degree: str
    field: str
    graduated: str
    gpa: float


@dataclass
class SearchConfig:
    keywords_whitelist: list[str] = field(default_factory=list)
    keywords_blacklist: list[str] = field(default_factory=list)
    location: str = ""
    remote_only: bool = True
    full_time_only: bool = True
    target_salary_min: Optional[int] = None
    benefits_priorities: list[str] = field(default_factory=list)


@dataclass
class UserProfile:
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    skills: list[str] = field(default_factory=list)
    work_history: list[WorkHistoryEntry] = field(default_factory=list)
    education: list[EducationEntry] = field(default_factory=list)
    target_salary_min: Optional[int] = None
    target_salary_max: Optional[int] = None
    target_roles: list[str] = field(default_factory=list)
    resume_path: str = ""
