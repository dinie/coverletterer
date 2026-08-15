"""Dispatch a job ad URL to the right site parser, with a headless-browser
fallback for sources that block plain HTTP fetches.

Adding a new job board later means adding one module here (`SITE`, `parse`)
and one line in `_PARSERS_BY_DOMAIN` — existing sources are untouched.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ..services.browser_fetch import BrowserFetchError, fetch_rendered_html
from . import generic, indeed, linkedin, seek
from .base import JobParseError, JobPosting

_PARSERS_BY_DOMAIN = {
    "seek.com": seek,
    "indeed.com": indeed,
    "linkedin.com": linkedin,
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _parser_for(url: str):
    host = urlparse(url).netloc.lower()
    for domain, module in _PARSERS_BY_DOMAIN.items():
        if host == domain or host.endswith("." + domain):
            return module
    return generic


def detect_site(url: str) -> str:
    return _parser_for(url).SITE


def _direct_fetch(url: str) -> str:
    response = httpx.get(
        url,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.text


def fetch_job_posting(url: str) -> JobPosting:
    """Fetch + parse a job ad. Tries a direct HTTP fetch first, then falls
    back to a headless-browser fetch if that fails or the expected markup
    isn't found. Raises `JobParseError` if both attempts fail — the caller
    should fall back to asking the user to paste the description manually.
    """
    parser = _parser_for(url)

    try:
        html = _direct_fetch(url)
        return parser.parse(html)
    except (httpx.HTTPError, JobParseError):
        pass

    try:
        html = fetch_rendered_html(url)
    except BrowserFetchError as e:
        raise JobParseError(str(e)) from e

    return parser.parse(html)


def fetch_readable_html_text(url: str) -> str:
    """Fetch a page's readable text (used for resume URLs), same
    direct-then-browser fallback strategy as job ads.
    """
    try:
        html = _direct_fetch(url)
        return generic.extract_text(html)
    except httpx.HTTPError:
        pass

    try:
        html = fetch_rendered_html(url)
    except BrowserFetchError as e:
        raise JobParseError(str(e)) from e

    text = generic.extract_text(html)
    if not text:
        raise JobParseError(f"Could not find any readable content at {url}.")
    return text


__all__ = [
    "JobPosting",
    "JobParseError",
    "detect_site",
    "fetch_job_posting",
    "fetch_readable_html_text",
]
