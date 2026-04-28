from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.types import SearchConfig


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
    remote: bool = False
    posted_at: str = ""


class JobSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]: ...
