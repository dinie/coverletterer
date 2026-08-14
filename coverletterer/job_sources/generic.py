"""Fallback readable-text extraction for HTML pages with no known markup.

Used for: unlisted/future job-board sources, Indeed once its markup drifts
enough to break `indeed.parse`, and resume pages supplied as a URL (a
personal site like resume.arulnathan.org has no fixed structure to key off,
just headings/paragraphs/lists).

Heuristic: strip non-content chrome (script/style/nav/header/footer/form),
prefer a <main>/<article> if present, then join block-level text with
newlines and collapse blank runs. Not perfect boilerplate removal, but good
enough for the kind of content-first static pages this app deals with.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import JobParseError, JobPosting

SITE = "other"

_CHROME_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "form", "svg"]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_CHROME_TAGS):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [
        line.strip()
        for line in root.get_text("\n").splitlines()
        if line.strip()
    ]
    return "\n".join(lines)


def _title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def parse(html: str) -> JobPosting:
    description = extract_text(html)
    if not description:
        raise JobParseError("Could not find any readable content on this page.")

    soup = BeautifulSoup(html, "lxml")
    return JobPosting(
        title=_title(soup),
        company="",
        description=description,
        site=SITE,
    )
