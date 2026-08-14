"""State for a single job application: job-ad parsing, resume override, and
cover-letter drafts (generate / edit / save / export)."""

from __future__ import annotations

import datetime

import reflex as rx
from reflex.utils.misc import run_in_thread
from sqlmodel import select

from .. import job_sources
from ..models import CoverLetterDraft, JobApplication, Resume, Status
from ..schemas import DraftVM, ResumeVM
from ..services import cover_letter, pdf_export, resume_ingest
from .base import AppState


def _fmt_dt(dt) -> str:
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _resume_vm(resume: Resume | None) -> ResumeVM:
    if resume is None:
        return ResumeVM()
    label = (
        resume.source_url
        if resume.source_type == "html_url"
        else (resume.stored_path or "").rsplit("/", 1)[-1]
    )
    return ResumeVM(
        present=True,
        source_type=resume.source_type,
        source_label=label or "",
        preview=resume.extracted_text[:600],
        updated_at=resume.updated_at.strftime("%Y-%m-%d %H:%M")
        if resume.updated_at
        else "",
    )


def _query_effective_resume(user_id: int, application_id: int) -> tuple[ResumeVM, bool]:
    resume = resume_ingest.get_effective_resume(user_id, application_id)
    is_override = bool(resume and resume.application_id is not None)
    return _resume_vm(resume), is_override


def _query_drafts(application_id: int) -> list[DraftVM]:
    with rx.session() as session:
        rows = session.exec(
            select(CoverLetterDraft)
            .where(CoverLetterDraft.application_id == application_id)
            .order_by(CoverLetterDraft.created_at)  # type: ignore[arg-type]
        ).all()
    return [
        DraftVM(
            id=d.id,
            label=d.label,
            content=d.content,
            saved=d.saved,
            updated_at=_fmt_dt(d.updated_at),
        )
        for d in rows
    ]


def _mark_status(application_id: int, status: str, error: str = "") -> None:
    with rx.session() as session:
        app = session.get(JobApplication, application_id)
        if app is not None:
            app.status = status
            app.error = error
            session.add(app)
            session.commit()


class DraftState(AppState):
    """Drives the /application/[application_id] page."""

    application_id_loaded: int = -1
    job_title: str = ""
    company: str = ""
    job_description: str = ""
    status: str = ""
    error: str = ""
    manual_paste_text: str = ""

    resume: ResumeVM = ResumeVM()
    resume_is_override: bool = False
    override_url_input: str = ""
    resume_saving: bool = False
    resume_error: str = ""

    drafts: list[DraftVM] = []
    generating: bool = False
    generate_error: str = ""
    active_draft_id: int = -1
    active_draft_content: str = ""
    active_draft_label: str = ""

    @rx.var
    def needs_manual_paste(self) -> bool:
        return self.status == Status.NEEDS_MANUAL_PASTE

    @rx.var
    def is_parsing(self) -> bool:
        return self.status == Status.PARSING

    @rx.var
    def has_error(self) -> bool:
        return self.status == Status.ERROR

    # ---- load (reload-safe) ----

    @rx.event
    def load_application(self):
        self.error = ""
        raw_id = getattr(self, "application_id", "")
        try:
            application_id = int(raw_id)
        except (TypeError, ValueError):
            return
        with rx.session() as session:
            app = session.get(JobApplication, application_id)
            if app is None or app.user_id != self.user_id:
                self.status = Status.ERROR
                self.error = "Application not found."
                return
            self.application_id_loaded = application_id
            self.job_title = app.job_title
            self.company = app.company
            self.job_description = app.job_description
            self.status = app.status
            self.error = app.error or ""
        self.resume, self.resume_is_override = _query_effective_resume(
            self.user_id, application_id
        )
        self.drafts = _query_drafts(application_id)
        self.active_draft_id = -1
        self.active_draft_content = ""
        self.active_draft_label = ""

    # ---- job-ad parsing (background) ----

    @rx.event(background=True)
    async def parse_job_ad(self, application_id: int):
        with rx.session() as session:
            app = session.get(JobApplication, application_id)
            if app is None:
                return
            source_url = app.source_url

        try:
            posting = await run_in_thread(
                lambda: job_sources.fetch_job_posting(source_url)
            )
        except job_sources.JobParseError as e:
            _mark_status(application_id, Status.NEEDS_MANUAL_PASTE, str(e))
            async with self:
                if self.application_id_loaded == application_id:
                    self.status = Status.NEEDS_MANUAL_PASTE
                    self.error = str(e)
            return
        except Exception as e:  # noqa: BLE001
            _mark_status(application_id, Status.ERROR, str(e))
            async with self:
                if self.application_id_loaded == application_id:
                    self.status = Status.ERROR
                    self.error = str(e)
            return

        with rx.session() as session:
            app = session.get(JobApplication, application_id)
            app.job_title = posting.title
            app.company = posting.company
            app.job_description = posting.description
            app.status = Status.PARSED
            app.error = None
            session.add(app)
            session.commit()

        async with self:
            if self.application_id_loaded == application_id:
                self.job_title = posting.title
                self.company = posting.company
                self.job_description = posting.description
                self.status = Status.PARSED
                self.error = ""

    # ---- manual paste fallback / editing the parsed job details ----

    @rx.event
    def set_manual_paste_text(self, value: str):
        self.manual_paste_text = value

    @rx.event
    def submit_manual_paste(self):
        text = self.manual_paste_text.strip()
        if not text:
            self.error = "Paste the job description text first."
            return
        with rx.session() as session:
            app = session.get(JobApplication, self.application_id_loaded)
            if app is None or app.user_id != self.user_id:
                return
            app.job_description = text
            app.status = Status.PARSED
            app.error = None
            session.add(app)
            session.commit()
        self.job_description = text
        self.status = Status.PARSED
        self.error = ""
        self.manual_paste_text = ""

    @rx.event
    def set_job_title(self, value: str):
        self.job_title = value

    @rx.event
    def set_company(self, value: str):
        self.company = value

    @rx.event
    def set_job_description(self, value: str):
        self.job_description = value

    @rx.event
    def save_job_details(self):
        """Persist edits to the title/company/description (parsing isn't perfect)."""
        with rx.session() as session:
            app = session.get(JobApplication, self.application_id_loaded)
            if app is None or app.user_id != self.user_id:
                return
            app.job_title = self.job_title
            app.company = self.company
            app.job_description = self.job_description
            session.add(app)
            session.commit()

    # ---- resume override for this application ----

    @rx.event
    def set_override_url_input(self, value: str):
        self.override_url_input = value
        self.resume_error = ""

    @rx.event
    async def override_with_upload(self, files: list[rx.UploadFile]):
        # Note: upload handlers can't be `background=True` (Reflex restriction),
        # so this runs with the state lock held for its duration.
        if not files:
            self.resume_error = "No file selected."
            return
        file = files[0]
        filename = file.filename or "resume.pdf"
        if not filename.lower().endswith(".pdf"):
            self.resume_error = "Please upload a PDF file."
            return

        data = await file.read()
        application_id = self.application_id_loaded
        user_id = self.user_id
        self.resume_saving = True
        self.resume_error = ""
        yield  # flush the spinner state to the UI

        try:
            await run_in_thread(
                lambda: resume_ingest.ingest_pdf(
                    user_id, application_id, filename, data
                )
            )
        except resume_ingest.ResumeIngestError as e:
            self.resume_saving = False
            self.resume_error = str(e)
            return

        resume_vm, is_override = _query_effective_resume(user_id, application_id)
        self.resume_saving = False
        self.resume = resume_vm
        self.resume_is_override = is_override

    @rx.event(background=True)
    async def override_with_url(self):
        url = self.override_url_input.strip()
        if not url:
            async with self:
                self.resume_error = "Enter a URL."
            return

        application_id = self.application_id_loaded
        user_id = self.user_id
        async with self:
            self.resume_saving = True
            self.resume_error = ""

        try:
            await run_in_thread(
                lambda: resume_ingest.ingest_url(user_id, application_id, url)
            )
        except Exception as e:  # noqa: BLE001
            async with self:
                self.resume_saving = False
                self.resume_error = f"Could not read that page: {e}"
            return

        resume_vm, is_override = _query_effective_resume(user_id, application_id)
        async with self:
            self.resume_saving = False
            self.override_url_input = ""
            self.resume = resume_vm
            self.resume_is_override = is_override

    @rx.event
    def revert_resume_to_default(self):
        resume_ingest.delete_override(self.user_id, self.application_id_loaded)
        self.resume, self.resume_is_override = _query_effective_resume(
            self.user_id, self.application_id_loaded
        )

    # ---- cover-letter drafts ----

    @rx.event(background=True)
    async def generate_draft(self):
        application_id = self.application_id_loaded
        user_id = self.user_id
        async with self:
            self.generating = True
            self.generate_error = ""

        with rx.session() as session:
            app = session.get(JobApplication, application_id)
            job_title, company, job_description = (
                app.job_title,
                app.company,
                app.job_description,
            )

        resume = resume_ingest.get_effective_resume(user_id, application_id)
        if resume is None or not resume.extracted_text:
            async with self:
                self.generating = False
                self.generate_error = (
                    "Add a resume first — set a default on the Profile page, "
                    "or override it for this application."
                )
            return

        try:
            content = await run_in_thread(
                lambda: cover_letter.generate(
                    resume.extracted_text, job_title, company, job_description
                )
            )
        except cover_letter.LLMConfigError as e:
            async with self:
                self.generating = False
                self.generate_error = str(e)
            return
        except Exception as e:  # noqa: BLE001
            async with self:
                self.generating = False
                self.generate_error = f"Could not generate a draft: {e}"
            return

        def _save_draft() -> None:
            with rx.session() as session:
                existing_count = len(
                    session.exec(
                        select(CoverLetterDraft).where(
                            CoverLetterDraft.application_id == application_id
                        )
                    ).all()
                )
                draft = CoverLetterDraft(
                    application_id=application_id,
                    label=f"Draft {existing_count + 1}",
                    content=content,
                )
                session.add(draft)
                session.commit()

        await run_in_thread(_save_draft)
        drafts = _query_drafts(application_id)
        async with self:
            self.generating = False
            self.drafts = drafts

    @rx.event
    def select_draft(self, draft_id: int):
        for d in self.drafts:
            if d.id == draft_id:
                self.active_draft_id = draft_id
                self.active_draft_content = d.content
                self.active_draft_label = d.label
                return

    @rx.event
    def set_active_draft_content(self, value: str):
        self.active_draft_content = value

    @rx.event
    def save_active_draft(self):
        if self.active_draft_id < 0:
            return
        with rx.session() as session:
            draft = session.get(CoverLetterDraft, self.active_draft_id)
            if draft is None:
                return
            app = session.get(JobApplication, draft.application_id)
            if app is None or app.user_id != self.user_id:
                return
            draft.content = self.active_draft_content
            draft.saved = True
            draft.updated_at = datetime.datetime.now(datetime.timezone.utc)
            session.add(draft)
            session.commit()
        self.drafts = _query_drafts(self.application_id_loaded)

    @rx.event
    def delete_draft(self, draft_id: int):
        with rx.session() as session:
            draft = session.get(CoverLetterDraft, draft_id)
            if draft is None:
                return
            app = session.get(JobApplication, draft.application_id)
            if app is None or app.user_id != self.user_id:
                return
            session.delete(draft)
            session.commit()
        if self.active_draft_id == draft_id:
            self.active_draft_id = -1
            self.active_draft_content = ""
            self.active_draft_label = ""
        self.drafts = _query_drafts(self.application_id_loaded)

    @rx.event
    def export_draft_pdf(self, draft_id: int):
        target = next((d for d in self.drafts if d.id == draft_id), None)
        if target is None:
            return
        pdf_bytes = pdf_export.render_cover_letter_pdf(
            target.content, job_title=self.job_title, company=self.company
        )
        safe_company = "".join(
            c if c.isalnum() else "-" for c in (self.company or "application")
        ).strip("-").lower() or "application"
        filename = f"cover-letter-{safe_company}-{target.label.replace(' ', '-').lower()}.pdf"
        return rx.download(data=pdf_bytes, filename=filename)
