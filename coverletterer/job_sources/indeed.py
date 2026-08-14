"""Parser for au.indeed.com job ad pages.

Indeed's Cloudflare bot-management blocks plain HTTP clients (confirmed: a
plain GET with a browser User-Agent returns 403 with
`cf-mitigated: challenge`), so this parser is normally only reached after a
headless-browser fetch (see `services/browser_fetch.py`) — the markup below is
otherwise identical to what a real browser sees, keyed off Indeed's
`data-testid` attributes / the long-stable `#jobDescriptionText` id.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import JobParseError, JobPosting

SITE = "indeed"


def parse(html: str) -> JobPosting:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(attrs={"data-testid": "jobsearch-JobInfoHeader-title"})
    company_el = soup.find(attrs={"data-testid": "inlineHeader-companyName"})
    location_el = soup.find(
        attrs={"data-testid": "jobsearch-JobInfoHeader-companyLocation"}
    )
    desc_el = soup.find(id="jobDescriptionText")

    description = desc_el.get_text("\n", strip=True) if desc_el else ""
    if not description:
        raise JobParseError("Could not find a job description on this Indeed page.")

    return JobPosting(
        title=title_el.get_text(" ", strip=True) if title_el else "",
        company=company_el.get_text(" ", strip=True) if company_el else "",
        location=location_el.get_text(" ", strip=True) if location_el else "",
        description=description,
        site=SITE,
    )
