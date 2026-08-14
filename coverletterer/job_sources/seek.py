"""Parser for au.seek.com job ad pages.

SEEK server-renders the job description as static HTML (confirmed: a plain
HTTP GET with a browser User-Agent returns 200 with the description already
present), keyed off stable `data-automation` attributes SEEK uses for its own
test automation.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import JobParseError, JobPosting

SITE = "seek"


def parse(html: str) -> JobPosting:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(attrs={"data-automation": "job-detail-title"})
    company_el = soup.find(attrs={"data-automation": "advertiser-name"})
    location_el = soup.find(attrs={"data-automation": "job-detail-location"})
    desc_el = soup.find(attrs={"data-automation": "jobAdDetails"})

    description = desc_el.get_text("\n", strip=True) if desc_el else ""
    if not description:
        raise JobParseError("Could not find a job description on this SEEK page.")

    return JobPosting(
        title=title_el.get_text(" ", strip=True) if title_el else "",
        company=company_el.get_text(" ", strip=True) if company_el else "",
        location=location_el.get_text(" ", strip=True) if location_el else "",
        description=description,
        site=SITE,
    )
