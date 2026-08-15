"""Database models.

`reflex_local_auth` provides the `LocalUser` / `LocalAuthSession` tables; we
import it so its metadata is registered for migrations and FK targets resolve.
Our own tables are scoped to a user via `user_id -> localuser.id`.
"""

from __future__ import annotations

import datetime

import reflex as rx
import reflex_local_auth  # noqa: F401  (registers LocalUser/LocalAuthSession tables)
import sqlalchemy
import sqlmodel


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# JobApplication status values (stored as plain strings for portability).
class Status:
    PARSING = "parsing"
    PARSED = "parsed"
    NEEDS_MANUAL_PASTE = "needs_manual_paste"
    ERROR = "error"


class JobApplication(rx.Model, table=True):
    """One job ad a user is tracking, plus its scraped/pasted description."""

    user_id: int = sqlmodel.Field(foreign_key="localuser.id", index=True)
    source_url: str
    site: str = "other"  # "seek" | "indeed" | "linkedin" | "other"
    job_title: str = ""
    company: str = ""
    job_description: str = sqlmodel.Field(
        default="", sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )
    status: str = Status.PARSING
    error: str | None = None
    created_at: datetime.datetime = sqlmodel.Field(default_factory=_utcnow)

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            "user_id", "source_url", name="uq_jobapplication_user_source_url"
        ),
    )


class Resume(rx.Model, table=True):
    """A resume's extracted text, sourced from an uploaded PDF or a URL.

    `application_id` is NULL for a user's account-level default resume, or set
    to scope this row as a one-off override for that single application.
    """

    user_id: int = sqlmodel.Field(foreign_key="localuser.id", index=True)
    application_id: int | None = sqlmodel.Field(
        default=None, foreign_key="jobapplication.id", index=True
    )
    source_type: str = "pdf_upload"  # "pdf_upload" | "html_url"
    source_url: str | None = None
    stored_path: str | None = None  # object storage key, for pdf_upload
    extracted_text: str = sqlmodel.Field(
        default="", sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )
    updated_at: datetime.datetime = sqlmodel.Field(default_factory=_utcnow)


class CoverLetterDraft(rx.Model, table=True):
    """One generated/edited cover letter draft for a job application.

    Ownership is checked via the parent `JobApplication.user_id` rather than
    denormalizing `user_id` onto this table.
    """

    application_id: int = sqlmodel.Field(foreign_key="jobapplication.id", index=True)
    label: str = "Draft 1"
    content: str = sqlmodel.Field(
        default="", sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )
    saved: bool = False
    created_at: datetime.datetime = sqlmodel.Field(default_factory=_utcnow)
    updated_at: datetime.datetime = sqlmodel.Field(default_factory=_utcnow)


class MagicLinkToken(rx.Model, table=True):
    """A single-use, short-lived token backing a passwordless email sign-in.

    Only the SHA-256 hash of the token is stored; the raw token lives solely in
    the emailed link.
    """

    email: str = sqlmodel.Field(index=True)
    token_hash: str = sqlmodel.Field(index=True)
    expiration: datetime.datetime
    used: bool = False
    created_at: datetime.datetime = sqlmodel.Field(default_factory=_utcnow)
