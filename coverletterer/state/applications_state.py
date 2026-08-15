"""State for the dashboard: list, create, and delete job applications."""

from __future__ import annotations

import reflex as rx
from reflex.utils.misc import run_in_thread
from sqlmodel import select

from ..models import CoverLetterDraft, JobApplication, Resume
from ..schemas import ApplicationVM
from ..services import application_ingest
from .base import AppState
from .draft_state import DraftState


def _fmt_dt(dt) -> str:
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


class ApplicationsState(AppState):
    """Dashboard listing + new-application form."""

    applications: list[ApplicationVM] = []

    new_url: str = ""
    creating: bool = False
    create_error: str = ""

    def _query_applications(self) -> list[ApplicationVM]:
        if not self.is_authenticated:
            return []
        with rx.session() as session:
            rows = session.exec(
                select(JobApplication)
                .where(JobApplication.user_id == self.user_id)
                .order_by(JobApplication.created_at.desc())  # type: ignore[attr-defined]
            ).all()
            out = []
            for app in rows:
                draft_count = len(
                    session.exec(
                        select(CoverLetterDraft).where(
                            CoverLetterDraft.application_id == app.id
                        )
                    ).all()
                )
                out.append(
                    ApplicationVM(
                        id=app.id,
                        job_title=app.job_title,
                        company=app.company,
                        site=app.site,
                        status=app.status,
                        draft_count=draft_count,
                        created_at=_fmt_dt(app.created_at),
                    )
                )
            return out

    @rx.event
    def load_applications(self):
        self.applications = self._query_applications()

    @rx.event
    def delete_application(self, application_id: int):
        if not self.is_authenticated:
            return
        with rx.session() as session:
            app = session.get(JobApplication, application_id)
            if app is None or app.user_id != self.user_id:
                return
            for draft in session.exec(
                select(CoverLetterDraft).where(
                    CoverLetterDraft.application_id == application_id
                )
            ).all():
                session.delete(draft)
            override = session.exec(
                select(Resume).where(
                    Resume.user_id == self.user_id,
                    Resume.application_id == application_id,
                )
            ).one_or_none()
            if override is not None:
                session.delete(override)
            session.delete(app)
            session.commit()
        self.applications = self._query_applications()

    @rx.event
    def set_new_url(self, value: str):
        self.new_url = value
        self.create_error = ""

    @rx.event(background=True)
    async def create_application(self):
        """Create a JobApplication row and kick off background parsing."""
        url = self.new_url.strip()
        if not url:
            async with self:
                self.create_error = "Enter a job ad URL."
            return

        user_id = self.user_id

        with rx.session() as session:
            existing = session.exec(
                select(JobApplication).where(
                    JobApplication.user_id == user_id,
                    JobApplication.source_url == url,
                )
            ).one_or_none()
        if existing is not None:
            async with self:
                self.create_error = "You already have an application for this URL."
            return

        async with self:
            self.creating = True
            self.create_error = ""

        app, _created = await run_in_thread(
            lambda: application_ingest.get_or_create(user_id, url)
        )

        async with self:
            self.creating = False
            self.new_url = ""

        yield [
            rx.redirect(f"/application/{app.id}"),
            DraftState.parse_job_ad(app.id),
        ]
