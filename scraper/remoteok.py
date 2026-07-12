from __future__ import annotations

import httpx

from scraper.base import SearchConfig
from scraper.base import JobSource, ScrapedJob

_BASE_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    @property
    def source_id(self) -> str:
        return "remoteok"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        response = httpx.get(
            _BASE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()

        whitelist = [term.lower() for term in config.keywords_whitelist]
        blacklist = [term.lower() for term in config.keywords_blacklist]

        # Skip first element (metadata object has no "id" key)
        raw_jobs = [item for item in response.json() if isinstance(item, dict) and "id" in item]

        results: list[ScrapedJob] = []
        for job in raw_jobs:
            url = job.get("url", "")
            if not url:
                continue

            title = job.get("position", "")
            description = job.get("description", "") or ""
            text = (title + " " + description).lower()

            if whitelist and not any(term in text for term in whitelist):
                continue
            if blacklist and any(term in text for term in blacklist):
                continue

            def _int(v):
                try:
                    return int(v) if v else None
                except (TypeError, ValueError):
                    return None

            results.append(ScrapedJob(
                source=self.source_id,
                job_key=f"remoteok_{job.get('id', '')}",
                title=title,
                company=job.get("company", ""),
                url=url,
                description=description,
                location=job.get("location", "") or "",
                salary_min=_int(job.get("salary_min")),
                salary_max=_int(job.get("salary_max")),
                remote=True,
                posted_at=job.get("date", ""),
            ))

            if len(results) >= max_jobs:
                break

        return results
