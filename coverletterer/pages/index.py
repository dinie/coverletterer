"""Dashboard: list, open, and delete job applications."""

from __future__ import annotations

import reflex as rx

from ..components.auth import require_login
from ..components.navbar import layout
from ..schemas import ApplicationVM
from ..state.applications_state import ApplicationsState


def _status_badge(app: ApplicationVM) -> rx.Component:
    return rx.badge(
        app.status.replace("_", " "),
        color_scheme=rx.match(
            app.status,
            ("parsing", "blue"),
            ("parsed", "green"),
            ("needs_manual_paste", "amber"),
            ("error", "red"),
            "gray",
        ),
    )


def _application_row(app: ApplicationVM) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.link(
                    rx.heading(
                        rx.cond(app.job_title != "", app.job_title, "Untitled role"),
                        size="4",
                    ),
                    href=f"/application/{app.id}",
                ),
                rx.text(app.company, color_scheme="gray"),
                rx.hstack(
                    _status_badge(app),
                    rx.badge(app.site, variant="soft"),
                    rx.text(
                        app.draft_count.to_string() + " draft(s)",
                        size="1",
                        color_scheme="gray",
                    ),
                    rx.text(app.created_at, size="1", color_scheme="gray"),
                    spacing="2",
                    align="center",
                ),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            rx.button(
                rx.icon("trash-2", size=16),
                on_click=ApplicationsState.delete_application(app.id),
                variant="soft",
                color_scheme="red",
                size="2",
            ),
            width="100%",
            align="center",
        ),
        width="100%",
    )


@require_login
def index() -> rx.Component:
    return layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Your applications", size="7"),
                rx.spacer(),
                rx.link(
                    rx.button(rx.icon("plus", size=16), "New application", size="3"),
                    href="/new",
                ),
                width="100%",
                align="center",
            ),
            rx.cond(
                ApplicationsState.applications.length() == 0,
                rx.callout(
                    "No applications yet. Add a job ad URL to get started.",
                    icon="inbox",
                ),
                rx.vstack(
                    rx.foreach(ApplicationsState.applications, _application_row),
                    spacing="3",
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
        )
    )
