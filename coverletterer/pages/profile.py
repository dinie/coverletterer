"""Manage the account-level default resume."""

from __future__ import annotations

import reflex as rx

from ..components.auth import require_login
from ..components.navbar import layout
from ..state.profile_state import ProfileState

_UPLOAD_ID = "profile_resume_upload"


@require_login
def profile_page() -> rx.Component:
    return layout(
        rx.vstack(
            rx.heading("Your resume", size="7"),
            rx.text(
                "Used by default when generating a cover letter for any "
                "application. You can override it per-application if needed.",
                color_scheme="gray",
            ),
            rx.cond(
                ProfileState.resume.present,
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.badge(ProfileState.resume.source_type, variant="soft"),
                            rx.text(ProfileState.resume.source_label, weight="medium"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Updated " + ProfileState.resume.updated_at,
                            size="1",
                            color_scheme="gray",
                        ),
                        rx.text(
                            ProfileState.resume.preview, size="2", color_scheme="gray"
                        ),
                        spacing="2",
                        align="start",
                    ),
                    width="100%",
                ),
            ),
            rx.divider(),
            rx.text("Upload a PDF", weight="bold", size="3"),
            rx.upload(
                rx.vstack(
                    rx.icon("upload", size=24),
                    rx.text("Drag & drop or click to select a PDF"),
                    align="center",
                    spacing="2",
                ),
                id=_UPLOAD_ID,
                accept={"application/pdf": [".pdf"]},
                max_files=1,
                border="1px dashed var(--gray-6)",
                border_radius="8px",
                padding="1.5rem",
                width="100%",
            ),
            rx.hstack(
                rx.foreach(rx.selected_files(_UPLOAD_ID), rx.badge),
                spacing="2",
            ),
            rx.button(
                "Save resume",
                on_click=ProfileState.handle_upload(rx.upload_files(_UPLOAD_ID)),
                loading=ProfileState.saving,
                size="3",
            ),
            rx.divider(),
            rx.text("…or point at a URL", weight="bold", size="3"),
            rx.hstack(
                rx.input(
                    placeholder="https://your-resume-site.com",
                    value=ProfileState.url_input,
                    on_change=ProfileState.set_url_input,
                    width="100%",
                ),
                rx.button(
                    "Save",
                    on_click=ProfileState.submit_url,
                    loading=ProfileState.saving,
                    size="3",
                ),
                width="100%",
            ),
            rx.cond(
                ProfileState.error != "",
                rx.callout(
                    ProfileState.error, icon="triangle_alert", color_scheme="red"
                ),
            ),
            rx.divider(),
            _extension_access_card(),
            spacing="4",
            width="100%",
        )
    )


def _extension_access_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading("Extension access", size="4"),
            rx.text(
                "Generate a personal token for the CoverLetterer browser "
                "extension, so it can create job applications on your behalf.",
                color_scheme="gray",
                size="2",
            ),
            rx.cond(
                ProfileState.token_value != "",
                rx.vstack(
                    rx.callout(
                        "Copy this now — you won't be able to see it again.",
                        icon="triangle_alert",
                        color_scheme="amber",
                    ),
                    rx.hstack(
                        rx.code(ProfileState.token_value, size="2"),
                        rx.button(
                            rx.icon("copy", size=14),
                            "Copy",
                            on_click=rx.set_clipboard(ProfileState.token_value),
                            size="2",
                            variant="soft",
                        ),
                        align="center",
                        spacing="2",
                    ),
                    rx.button(
                        "Done",
                        on_click=ProfileState.dismiss_token_value,
                        size="2",
                        variant="soft",
                    ),
                    spacing="3",
                    width="100%",
                    align="start",
                ),
                rx.vstack(
                    rx.cond(
                        ProfileState.token_exists,
                        rx.hstack(
                            rx.badge("Token active", color_scheme="green"),
                            rx.text(
                                "Created " + ProfileState.token_created_at,
                                size="1",
                                color_scheme="gray",
                            ),
                            align="center",
                            spacing="2",
                        ),
                    ),
                    rx.hstack(
                        rx.button(
                            rx.cond(
                                ProfileState.token_exists,
                                "Regenerate token",
                                "Generate token",
                            ),
                            on_click=ProfileState.generate_token,
                            size="2",
                        ),
                        rx.cond(
                            ProfileState.token_exists,
                            rx.button(
                                "Revoke",
                                on_click=ProfileState.revoke_token,
                                size="2",
                                variant="soft",
                                color_scheme="red",
                            ),
                        ),
                        spacing="3",
                    ),
                    spacing="3",
                    width="100%",
                    align="start",
                ),
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
        width="100%",
    )
