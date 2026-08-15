"""Tests for the shared job-application create/parse logic used by both the
web UI's "New application" flow and the browser-extension API route.

Uses an isolated in-memory SQLite engine (monkeypatched in place of
`rx.session`) so this doesn't touch the dev database, and monkeypatches
`job_sources.fetch_job_posting` so no live network call happens.
"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine

from coverletterer import models  # noqa: F401  (registers all tables)
from coverletterer.job_sources.base import JobParseError, JobPosting
from coverletterer.models import JobApplication, Status
from coverletterer.services import application_ingest


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def user_id(engine) -> int:
    from reflex_local_auth.user import LocalUser

    with Session(engine) as session:
        user = LocalUser(
            username=f"user-{uuid.uuid4().hex}", password_hash=b"x", enabled=True
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


@pytest.fixture(autouse=True)
def patched_session(monkeypatch, engine):
    """Point application_ingest's `rx.session()` calls at the isolated engine."""
    monkeypatch.setattr(application_ingest.rx, "session", lambda: Session(engine))


def test_get_or_create_creates_a_pending_row(user_id):
    app, created = application_ingest.get_or_create(user_id, "https://example.com/job/1")
    assert created is True
    assert app.status == Status.PARSING
    assert app.job_title == ""


def test_get_or_create_is_idempotent(user_id):
    first, created_first = application_ingest.get_or_create(
        user_id, "https://example.com/job/1"
    )
    second, created_second = application_ingest.get_or_create(
        user_id, "https://example.com/job/1"
    )
    assert created_first is True
    assert created_second is False
    assert first.id == second.id


def test_parse_and_persist_updates_status_on_success(monkeypatch, user_id):
    monkeypatch.setattr(
        application_ingest.job_sources,
        "fetch_job_posting",
        lambda url: JobPosting(
            title="Senior Engineer",
            company="Acme",
            description="Do great things.",
            site="seek",
        ),
    )
    app, _ = application_ingest.get_or_create(user_id, "https://example.com/job/2")
    updated = application_ingest.parse_and_persist(app.id)

    assert updated.status == Status.PARSED
    assert updated.job_title == "Senior Engineer"
    assert updated.company == "Acme"
    assert updated.job_description == "Do great things."


def test_parse_and_persist_falls_back_to_manual_paste_on_parse_error(
    monkeypatch, user_id
):
    def _raise(url):
        raise JobParseError("blocked")

    monkeypatch.setattr(application_ingest.job_sources, "fetch_job_posting", _raise)
    app, _ = application_ingest.get_or_create(user_id, "https://example.com/job/3")
    updated = application_ingest.parse_and_persist(app.id)

    assert updated.status == Status.NEEDS_MANUAL_PASTE
    assert updated.error == "blocked"


def test_parse_and_persist_marks_error_on_unexpected_exception(monkeypatch, user_id):
    def _raise(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(application_ingest.job_sources, "fetch_job_posting", _raise)
    app, _ = application_ingest.get_or_create(user_id, "https://example.com/job/4")
    updated = application_ingest.parse_and_persist(app.id)

    assert updated.status == Status.ERROR
    assert updated.error == "boom"


def test_parse_and_persist_returns_none_for_missing_application(user_id):
    assert application_ingest.parse_and_persist(999999) is None


def test_get_or_create_does_not_reparse_existing_application(monkeypatch, user_id):
    calls = []
    monkeypatch.setattr(
        application_ingest.job_sources,
        "fetch_job_posting",
        lambda url: calls.append(url)
        or JobPosting(title="T", company="C", description="D", site="seek"),
    )
    app, _ = application_ingest.get_or_create(user_id, "https://example.com/job/5")
    application_ingest.parse_and_persist(app.id)
    assert len(calls) == 1

    # A second get_or_create for the same URL must not touch the parser.
    application_ingest.get_or_create(user_id, "https://example.com/job/5")
    assert len(calls) == 1
