"""Parser for linkedin.com/jobs/view/... job ad pages.

Unlike Indeed, LinkedIn's public (logged-out) job-view page is server-rendered
static HTML with no auth-wall (confirmed: a plain GET with a browser
User-Agent returns 200 with the full description already present) — so this
parser is normally reached via the direct fetch, same as SEEK. LinkedIn is
known to rate-limit/block more aggressively than SEEK at higher volume or from
datacenter IPs, though; if that starts happening here, the dispatcher's
existing Playwright fallback (and manual-paste as a last resort) already
covers it without any change to this module.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import JobParseError, JobPosting

SITE = "linkedin"


def parse(html: str) -> JobPosting:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find("h1", class_="top-card-layout__title")
    company_el = soup.find(class_="topcard__org-name-link")
    location_el = soup.find(class_="topcard__flavor--bullet")
    desc_el = soup.find(class_="description__text")

    description = desc_el.get_text("\n", strip=True) if desc_el else ""
    if not description:
        raise JobParseError("Could not find a job description on this LinkedIn page.")

    return JobPosting(
        title=title_el.get_text(" ", strip=True) if title_el else "",
        company=company_el.get_text(" ", strip=True) if company_el else "",
        location=location_el.get_text(" ", strip=True) if location_el else "",
        description=description,
        site=SITE,
    )
