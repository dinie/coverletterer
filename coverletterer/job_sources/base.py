"""Shared types for job-ad source parsers.

Each site module (`seek.py`, `indeed.py`, `generic.py`) exposes a `SITE`
constant and a `parse(html: str) -> JobPosting` function. Adding a new source
later is just adding one more small module and a domain entry in `__init__.py`
— existing sources are never touched.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class JobPosting:
    title: str
    company: str
    description: str
    location: str = ""
    site: str = "other"


class JobParseError(RuntimeError):
    """Raised when a job ad could not be fetched or parsed automatically.

    The caller (application creation flow) catches this and falls back to
    asking the user to paste the job description manually.
    """
