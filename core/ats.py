"""Classify a resolved job-application URL to its hosting ATS by domain.

Pure, no network, no LLM. The domain-signature table below is the single
source of truth for the recognized-ATS set (see the ATS-detection spec).
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

# Ordered list of (host-suffix, ats_type). First matching suffix wins.
# Suffixes match the END of the hostname, so "greenhouse.io" catches both
# "boards.greenhouse.io" and "acme.greenhouse.io".
_ATS_SUFFIXES: list[tuple[str, str]] = [
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    ("myworkdayjobs.com", "workday"),
    ("workday.com", "workday"),
    ("icims.com", "icims"),
    ("taleo.net", "taleo"),
    ("smartrecruiters.com", "smartrecruiters"),
    ("jobvite.com", "jobvite"),
    ("bamboohr.com", "bamboohr"),
]


def unwrap_apply_url(url: str) -> str:
    """Unwrap a LinkedIn interstitial apply URL to its real destination.

    LinkedIn wraps external apply links in a ``/safety/go/?url=<encoded>``
    redirect page that requires a human click and never auto-forwards, so a
    headless tab resolution stalls on it and misreads the ATS as ``linkedin``.
    The true destination is carried in the ``url`` query parameter. Non-wrapper
    URLs (and anything malformed) are returned unchanged.

    Args:
        url: A raw apply URL, possibly a LinkedIn safety-redirect wrapper.

    Returns:
        The unwrapped target URL, or the input unchanged if it is not a
        recognized wrapper.
    """
    try:
        parts = urlparse(url)
    except ValueError:
        return url
    host = (parts.hostname or "").lower()
    if (host == "linkedin.com" or host.endswith(".linkedin.com")) and "/safety/go/" in parts.path:
        target = parse_qs(parts.query).get("url", [""])[0]
        if target:
            return target
    return url


def classify_ats(url: str) -> tuple[str, str]:
    """Return (ats_type, hostname) for a resolved apply URL.

    Args:
        url: The final apply-destination URL after redirects.

    Returns:
        A tuple of the ATS type (a recognized key or ``"other"``) and the
        lowercased hostname. Malformed or empty input yields ``("other", "")``.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ("other", "")
    if not host:
        return ("other", "")
    for suffix, ats_type in _ATS_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return (ats_type, host)
    return ("other", host)
