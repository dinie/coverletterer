"""State for managing the account-level default resume (`/profile`)."""

from __future__ import annotations

import reflex as rx
from reflex.utils.misc import run_in_thread

from ..models import Resume
from ..schemas import ResumeVM
from ..services import resume_ingest
from .base import AppState


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


class ProfileState(AppState):
    """The user's default resume: upload a PDF or point at a URL."""

    resume: ResumeVM = ResumeVM()
    url_input: str = ""
    saving: bool = False
    error: str = ""

    @rx.event
    def load_resume(self):
        self.error = ""
        self.resume = _resume_vm(resume_ingest.get_effective_resume(self.user_id, None))

    @rx.event
    def set_url_input(self, value: str):
        self.url_input = value
        self.error = ""

    @rx.event
    async def handle_upload(self, files: list[rx.UploadFile]):
        # Note: upload handlers can't be `background=True` (Reflex restriction),
        # so this runs with the state lock held for its duration.
        if not files:
            self.error = "No file selected."
            return
        file = files[0]
        filename = file.filename or "resume.pdf"
        if not filename.lower().endswith(".pdf"):
            self.error = "Please upload a PDF file."
            return

        data = await file.read()
        user_id = self.user_id
        self.saving = True
        self.error = ""
        yield  # flush the spinner state to the UI

        try:
            row = await run_in_thread(
                lambda: resume_ingest.ingest_pdf(user_id, None, filename, data)
            )
        except resume_ingest.ResumeIngestError as e:
            self.saving = False
            self.error = str(e)
            return

        self.saving = False
        self.resume = _resume_vm(row)

    @rx.event(background=True)
    async def submit_url(self):
        url = self.url_input.strip()
        if not url:
            async with self:
                self.error = "Enter a URL."
            return

        user_id = self.user_id
        async with self:
            self.saving = True
            self.error = ""

        try:
            row = await run_in_thread(
                lambda: resume_ingest.ingest_url(user_id, None, url)
            )
        except Exception as e:  # noqa: BLE001
            async with self:
                self.saving = False
                self.error = f"Could not read that page: {e}"
            return

        async with self:
            self.saving = False
            self.url_input = ""
            self.resume = _resume_vm(row)
