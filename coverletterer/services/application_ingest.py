"""Job-application creation + parsing, shared by the web UI's "New
application" flow (`state/applications_state.py` + `state/draft_state.py`)
and the browser-extension API route (`api_routes.py`).

Split into two steps so each caller can compose them the way it needs to:
- `get_or_create`: dedupe by (user_id, url); creates a `status=PARSING` row
  if none exists yet. Fast, no network I/O.
- `parse_and_persist`: does the actual fetch + parse for an existing row and
  updates its status. Slow (network I/O, possibly the Playwright fallback) —
  callers control threading (`run_in_thread` for Reflex background events,
  `asyncio.to_thread` for the API route).

Pure module — no Reflex-state imports, just `rx.session()` for the DB.
"""

from __future__ import annotations

import reflex as rx
from sqlmodel import select

from .. import job_sources
from ..models import JobApplication, Status


def get_or_create(user_id: int, url: str) -> tuple[JobApplication, bool]:
    """Return the existing (user_id, url) application if one exists,
    otherwise create it with status=PARSING. Does not fetch/parse.

    Returns (application, created) — `created` is False when an existing row
    was returned, so callers (e.g. the extension API) can tell "just added"
    apart from "already tracked".
    """
    with rx.session() as session:
        existing = session.exec(
            select(JobApplication).where(
                JobApplication.user_id == user_id, JobApplication.source_url == url
            )
        ).one_or_none()
        if existing is not None:
            return existing, False

        app = JobApplication(
            user_id=user_id,
            source_url=url,
            site=job_sources.detect_site(url),
            status=Status.PARSING,
        )
        session.add(app)
        session.commit()
        session.refresh(app)
        return app, True


def parse_and_persist(application_id: int) -> JobApplication | None:
    """Fetch + parse the job ad for an existing row, update its status, and
    return the updated row. None if the row doesn't exist."""
    with rx.session() as session:
        app = session.get(JobApplication, application_id)
        if app is None:
            return None
        source_url = app.source_url

    try:
        posting = job_sources.fetch_job_posting(source_url)
    except job_sources.JobParseError as e:
        return _mark_status(application_id, Status.NEEDS_MANUAL_PASTE, str(e))
    except Exception as e:  # noqa: BLE001
        return _mark_status(application_id, Status.ERROR, str(e))

    with rx.session() as session:
        app = session.get(JobApplication, application_id)
        app.job_title = posting.title
        app.company = posting.company
        app.job_description = posting.description
        app.status = Status.PARSED
        app.error = None
        session.add(app)
        session.commit()
        session.refresh(app)
        return app


def _mark_status(application_id: int, status: str, error: str = "") -> JobApplication | None:
    with rx.session() as session:
        app = session.get(JobApplication, application_id)
        if app is not None:
            app.status = status
            app.error = error
            session.add(app)
            session.commit()
            session.refresh(app)
        return app
