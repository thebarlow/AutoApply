from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclasses.dataclass
class SearchConfig:
    """Search parameters passed to every scraper source when fetching jobs."""

    keywords_whitelist: list[str] = dataclasses.field(default_factory=list)
    keywords_blacklist: list[str] = dataclasses.field(default_factory=list)
    location: str = ""
    remote_only: bool = True
    full_time_only: bool = True
    target_salary_min: Optional[int] = None
    benefits_priorities: list[str] = dataclasses.field(default_factory=list)


@dataclass
class ScrapedJob:
    source: str
    job_key: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    salary: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    remote: bool = False
    posted_at: str = ""


class JobSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]: ...
