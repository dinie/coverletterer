"""Single job application: parsed job ad, resume override, cover-letter drafts."""

from __future__ import annotations

import reflex as rx

from ..components.auth import require_login
from ..components.navbar import layout
from ..schemas import DraftVM
from ..state.draft_state import DraftState

_OVERRIDE_UPLOAD_ID = "override_resume_upload"


def _parsing_banner() -> rx.Component:
    return rx.callout(
        "Fetching and parsing the job ad… this can take a few seconds "
        "(longer if a headless-browser fallback is needed).",
        icon="loader",
        color_scheme="blue",
    )


def _error_banner() -> rx.Component:
    return rx.callout(DraftState.error, icon="triangle_alert", color_scheme="red")


def _manual_paste_panel() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(
                "We couldn't automatically parse this job ad (the site may be "
                "blocking automated access). Paste the job description below "
                "to continue.",
                weight="medium",
            ),
            rx.text_area(
                value=DraftState.manual_paste_text,
                on_change=DraftState.set_manual_paste_text,
                placeholder="Paste the full job description here…",
                rows="10",
                width="100%",
            ),
            rx.button(
                "Use this description",
                on_click=DraftState.submit_manual_paste,
                size="3",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def _job_details_panel() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.input(
                    value=DraftState.job_title,
                    on_change=DraftState.set_job_title,
                    placeholder="Job title",
                    width="100%",
                ),
                rx.input(
                    value=DraftState.company,
                    on_change=DraftState.set_company,
                    placeholder="Company",
                    width="100%",
                ),
                width="100%",
            ),
            rx.text_area(
                value=DraftState.job_description,
                on_change=DraftState.set_job_description,
                rows="12",
                width="100%",
            ),
            rx.button(
                "Save details",
                on_click=DraftState.save_job_details,
                variant="soft",
                size="2",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
    )


def _resume_panel() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading("Resume for this application", size="4"),
                rx.spacer(),
                rx.cond(
                    DraftState.resume_is_override,
                    rx.badge("Override", color_scheme="purple"),
                    rx.badge("Account default", variant="soft"),
                ),
                width="100%",
                align="center",
            ),
            rx.cond(
                DraftState.resume.present,
                rx.vstack(
                    rx.text(DraftState.resume.source_label, weight="medium"),
                    rx.text(DraftState.resume.preview, size="2", color_scheme="gray"),
                    spacing="1",
                    align="start",
                ),
                rx.callout(
                    "No resume set yet — add a default on the Profile page, "
                    "or upload one just for this application below.",
                    icon="triangle_alert",
                    color_scheme="amber",
                ),
            ),
            rx.cond(
                DraftState.resume_is_override,
                rx.button(
                    "Revert to account default",
                    on_click=DraftState.revert_resume_to_default,
                    variant="soft",
                    size="2",
                ),
            ),
            rx.divider(),
            rx.text("Override with a PDF", size="2", weight="bold"),
            rx.upload(
                rx.vstack(
                    rx.icon("upload", size=20),
                    rx.text("Drag & drop or click to select a PDF"),
                    align="center",
                    spacing="1",
                ),
                id=_OVERRIDE_UPLOAD_ID,
                accept={"application/pdf": [".pdf"]},
                max_files=1,
                border="1px dashed var(--gray-6)",
                border_radius="8px",
                padding="1rem",
                width="100%",
            ),
            rx.button(
                "Save override",
                on_click=DraftState.override_with_upload(
                    rx.upload_files(_OVERRIDE_UPLOAD_ID)
                ),
                loading=DraftState.resume_saving,
                size="2",
                variant="soft",
            ),
            rx.text("…or override with a URL", size="2", weight="bold"),
            rx.hstack(
                rx.input(
                    placeholder="https://your-resume-site.com",
                    value=DraftState.override_url_input,
                    on_change=DraftState.set_override_url_input,
                    width="100%",
                ),
                rx.button(
                    "Save",
                    on_click=DraftState.override_with_url,
                    loading=DraftState.resume_saving,
                    size="2",
                    variant="soft",
                ),
                width="100%",
            ),
            rx.cond(
                DraftState.resume_error != "",
                rx.callout(
                    DraftState.resume_error, icon="triangle_alert", color_scheme="red"
                ),
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
        width="100%",
    )


def _draft_card(draft: DraftVM) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.text(draft.label, weight="bold"),
                rx.text(draft.content[:160], size="1", color_scheme="gray"),
                rx.text(
                    "Updated " + draft.updated_at, size="1", color_scheme="gray"
                ),
                align="start",
                spacing="1",
                width="100%",
            ),
            rx.spacer(),
            rx.vstack(
                rx.button(
                    "Edit",
                    on_click=DraftState.select_draft(draft.id),
                    size="2",
                    variant="soft",
                ),
                rx.button(
                    "Export PDF",
                    on_click=DraftState.export_draft_pdf(draft.id),
                    size="2",
                    variant="soft",
                ),
                rx.button(
                    rx.icon("trash-2", size=14),
                    on_click=DraftState.delete_draft(draft.id),
                    size="2",
                    variant="soft",
                    color_scheme="red",
                ),
                spacing="2",
            ),
            width="100%",
            align="start",
        ),
        width="100%",
    )


def _editor_panel() -> rx.Component:
    return rx.cond(
        DraftState.active_draft_id >= 0,
        rx.card(
            rx.vstack(
                rx.heading("Editing " + DraftState.active_draft_label, size="4"),
                rx.text_area(
                    value=DraftState.active_draft_content,
                    on_change=DraftState.set_active_draft_content,
                    rows="16",
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        "Save draft", on_click=DraftState.save_active_draft, size="3"
                    ),
                    rx.button(
                        "Export PDF",
                        on_click=DraftState.export_draft_pdf(
                            DraftState.active_draft_id
                        ),
                        variant="soft",
                        size="3",
                    ),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
    )


def _drafts_section() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Drafts", size="5"),
            rx.spacer(),
            rx.button(
                rx.icon("sparkles", size=16),
                "Generate draft",
                on_click=DraftState.generate_draft,
                loading=DraftState.generating,
                size="3",
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            DraftState.generate_error != "",
            rx.callout(
                DraftState.generate_error, icon="triangle_alert", color_scheme="red"
            ),
        ),
        _editor_panel(),
        rx.cond(
            DraftState.drafts.length() == 0,
            rx.text("No drafts yet — generate one above.", color_scheme="gray"),
            rx.vstack(
                rx.foreach(DraftState.drafts, _draft_card),
                spacing="3",
                width="100%",
            ),
        ),
        spacing="4",
        width="100%",
    )


@require_login
def application_page() -> rx.Component:
    return layout(
        rx.vstack(
            rx.cond(
                DraftState.is_parsing,
                _parsing_banner(),
                rx.cond(
                    DraftState.needs_manual_paste,
                    _manual_paste_panel(),
                    rx.vstack(
                        rx.cond(DraftState.has_error, _error_banner()),
                        _job_details_panel(),
                        _resume_panel(),
                        _drafts_section(),
                        spacing="4",
                        width="100%",
                    ),
                ),
            ),
            spacing="4",
            width="100%",
        )
    )
