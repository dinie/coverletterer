"""Tests for DB-level constraints on our models.

Uses an isolated in-memory SQLite engine (not the app's configured Reflex
session), so this doesn't touch the dev database.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from coverletterer import models  # noqa: F401  (registers all tables)
from coverletterer.models import JobApplication


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    return eng


def _make_user(session: Session) -> int:
    import uuid

    from reflex_local_auth.user import LocalUser

    user = LocalUser(
        username=f"user-{uuid.uuid4().hex}", password_hash=b"x", enabled=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id


def test_same_user_cannot_have_duplicate_source_url(engine):
    with Session(engine) as session:
        user_id = _make_user(session)
        session.add(
            JobApplication(user_id=user_id, source_url="https://example.com/job/1")
        )
        session.commit()
        session.add(
            JobApplication(user_id=user_id, source_url="https://example.com/job/1")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_different_users_can_share_a_source_url(engine):
    with Session(engine) as session:
        user_a = _make_user(session)
        user_b = _make_user(session)
        session.add(
            JobApplication(user_id=user_a, source_url="https://example.com/job/1")
        )
        session.commit()
        session.add(
            JobApplication(user_id=user_b, source_url="https://example.com/job/1")
        )
        session.commit()  # should not raise
