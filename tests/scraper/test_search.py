from __future__ import annotations

from unittest.mock import patch

from scraper.base import ScrapedJob
from scraper.search import search_sources


def _job(source: str, key: str, url: str, title: str = "T",
         company: str = "C", location: str = "") -> ScrapedJob:
    return ScrapedJob(source=source, job_key=key, title=title, company=company,
                      url=url, description="d", location=location)


def test_empty_query_calls_no_sources():
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        assert search_sources("   ") == []
        rm.assert_not_called()
        rok.assert_not_called()


def test_merges_and_dedupes_by_url():
    a = _job("remotive", "remotive_1", "https://x.com/1", title="A")
    b = _job("remoteok", "remoteok_2", "https://x.com/2", title="B")
    dup = _job("remoteok", "remoteok_1", "https://x.com/1", title="A")  # same url
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.return_value = [a]
        rok.return_value.fetch.return_value = [dup, b]
        out = search_sources("python")
    urls = [j.url for j in out]
    assert urls == ["https://x.com/1", "https://x.com/2"]


def test_dedupes_by_identity_across_urls():
    # Same title/company/location under two different URLs — collapse to one.
    a = _job("remotive", "remotive_1", "https://x.com/1", title="Eng", company="Acme")
    dup = _job("remoteok", "remoteok_9", "https://x.com/9", title="Eng", company="Acme")
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.return_value = [a]
        rok.return_value.fetch.return_value = [dup]
        out = search_sources("python")
    assert [j.url for j in out] == ["https://x.com/1"]


def test_exclude_forwarded_as_blacklist():
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.return_value = []
        rok.return_value.fetch.return_value = []
        search_sources("python", exclude=["senior", " ", "lead"])
    cfg = rm.return_value.fetch.call_args[0][0]
    assert cfg.keywords_blacklist == ["senior", "lead"]


def test_location_filter_keeps_matches_and_worldwide():
    usa = _job("remotive", "r1", "https://x.com/1", title="A", location="USA Only")
    eu = _job("remoteok", "r2", "https://x.com/2", title="B", location="Europe")
    ww = _job("remoteok", "r3", "https://x.com/3", title="C", location="Worldwide")
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.return_value = [usa]
        rok.return_value.fetch.return_value = [eu, ww]
        out = search_sources("python", location="usa")
    assert [j.url for j in out] == ["https://x.com/1", "https://x.com/3"]


def test_source_failure_is_skipped():
    b = _job("remoteok", "remoteok_2", "https://x.com/2")
    with patch("scraper.search.RemotiveSource") as rm, \
         patch("scraper.search.RemoteOKSource") as rok:
        rm.return_value.fetch.side_effect = RuntimeError("boom")
        rok.return_value.fetch.return_value = [b]
        out = search_sources("python")
    assert [j.url for j in out] == ["https://x.com/2"]
