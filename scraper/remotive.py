from __future__ import annotations

import httpx

from scraper.base import SearchConfig
from scraper.base import JobSource, ScrapedJob

_BASE_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    @property
    def source_id(self) -> str:
        return "remotive"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        keyword = config.keywords_whitelist[0] if config.keywords_whitelist else ""
        response = httpx.get(
            _BASE_URL,
            params={"search": keyword, "limit": max_jobs},
            timeout=30,
        )
        response.raise_for_status()

        whitelist = [term.lower() for term in config.keywords_whitelist]
        blacklist = [term.lower() for term in config.keywords_blacklist]
        results: list[ScrapedJob] = []

        for job in response.json().get("jobs", []):
            url = job.get("url", "")
            if not url:
                continue

            title = job.get("title", "")
            description = job.get("description", "")
            text = (title + " " + description).lower()

            # Remotive's API ignores the `search` param (returns a fixed feed),
            # so we filter by keyword client-side, same as RemoteOK.
            if whitelist and not any(term in text for term in whitelist):
                continue
            if blacklist and any(term in text for term in blacklist):
                continue

            results.append(ScrapedJob(
                source=self.source_id,
                job_key=f"remotive_{job.get('id', '')}",
                title=title,
                company=job.get("company_name", ""),
                url=url,
                description=description,
                location=job.get("candidate_required_location", ""),
                salary=job.get("salary", "") or "",
                remote=True,
                posted_at=job.get("publication_date", ""),
            ))

        return results
