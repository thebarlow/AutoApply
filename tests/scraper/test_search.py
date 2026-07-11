from __future__ import annotations

from unittest.mock import patch

from scraper.base import ScrapedJob
from scraper.search import search_sources


def _job(source: str, key: str, url: str) -> ScrapedJob:
    return ScrapedJob(source=source, job_key=key, title="T", company="C",
                      url=url, description="d")


def test_empty_query_calls_no_sources():
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        assert search_sources("   ") == []
        rm.assert_not_called()
        rok.assert_not_called()


def test_merges_and_dedupes_by_url():
    a = _job("remotive", "remotive_1", "https://x.com/1")
    b = _job("remoteok", "remoteok_2", "https://x.com/2")
    dup = _job("remoteok", "remoteok_1", "https://x.com/1")  # same url as a
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.return_value = [a]
        rok.return_value.fetch.return_value = [dup, b]
        out = search_sources("python")
    urls = [j.url for j in out]
    assert urls == ["https://x.com/1", "https://x.com/2"]


def test_source_failure_is_skipped():
    b = _job("remoteok", "remoteok_2", "https://x.com/2")
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.side_effect = RuntimeError("boom")
        rok.return_value.fetch.return_value = [b]
        out = search_sources("python")
    assert [j.url for j in out] == ["https://x.com/2"]
