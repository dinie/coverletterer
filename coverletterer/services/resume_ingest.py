"""Turn a resume (uploaded PDF or a URL) into stored, extracted text.

One `ingest` entry point backs both the account-level default resume (Profile
page, `application_id=None`) and a one-off per-application override (an
application's "Override resume" action, `application_id=<that application>`).
At most one `Resume` row exists per `(user_id, application_id)` pair — ingest
upserts in place.
"""

from __future__ import annotations

import datetime
import io

import reflex as rx
from sqlmodel import select

from .. import job_sources
from ..models import Resume
from . import storage


class ResumeIngestError(RuntimeError):
    """Raised when a resume PDF or URL could not be read/parsed."""


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:  # noqa: BLE001
        raise ResumeIngestError(f"Could not read this PDF: {e}") from e

    text = "\n".join(p.strip() for p in pages if p.strip())
    if not text:
        raise ResumeIngestError("No extractable text found in this PDF.")
    return text


def _existing(user_id: int, application_id: int | None) -> Resume | None:
    with rx.session() as session:
        return session.exec(
            select(Resume).where(
                Resume.user_id == user_id, Resume.application_id == application_id
            )
        ).one_or_none()


def _upsert(
    user_id: int,
    application_id: int | None,
    *,
    source_type: str,
    source_url: str | None,
    stored_path: str | None,
    extracted_text: str,
) -> Resume:
    with rx.session() as session:
        row = session.exec(
            select(Resume).where(
                Resume.user_id == user_id, Resume.application_id == application_id
            )
        ).one_or_none()
        if row is None:
            row = Resume(user_id=user_id, application_id=application_id)  # type: ignore[call-arg]
        row.source_type = source_type
        row.source_url = source_url
        row.stored_path = stored_path
        row.extracted_text = extracted_text
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def ingest_pdf(
    user_id: int, application_id: int | None, filename: str, data: bytes
) -> Resume:
    text = extract_pdf_text(data)
    key = f"resumes/{user_id}/{application_id or 'default'}/{filename}"
    storage.put_bytes(key, data, "application/pdf")
    return _upsert(
        user_id,
        application_id,
        source_type="pdf_upload",
        source_url=None,
        stored_path=key,
        extracted_text=text,
    )


def ingest_url(user_id: int, application_id: int | None, url: str) -> Resume:
    text = job_sources.fetch_readable_html_text(url)
    return _upsert(
        user_id,
        application_id,
        source_type="html_url",
        source_url=url,
        stored_path=None,
        extracted_text=text,
    )


def get_effective_resume(user_id: int, application_id: int | None) -> Resume | None:
    """The resume that applies to `application_id`: its override if one
    exists, otherwise the user's account-level default. `None` if neither.
    """
    if application_id is not None:
        override = _existing(user_id, application_id)
        if override is not None:
            return override
    return _existing(user_id, None)


def delete_override(user_id: int, application_id: int) -> None:
    """Revert an application to the account default by deleting its override."""
    with rx.session() as session:
        row = session.exec(
            select(Resume).where(
                Resume.user_id == user_id, Resume.application_id == application_id
            )
        ).one_or_none()
        if row is not None:
            session.delete(row)
            session.commit()
