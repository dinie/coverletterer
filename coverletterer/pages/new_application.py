"""Paste a job ad URL to start a new application."""

from __future__ import annotations

import reflex as rx

from ..components.auth import require_login
from ..components.navbar import layout
from ..state.applications_state import ApplicationsState


@require_login
def new_application_page() -> rx.Component:
    return layout(
        rx.vstack(
            rx.heading("New application", size="7"),
            rx.text(
                "Paste the URL of a job ad (SEEK, Indeed, or another site) and "
                "we'll fetch and parse the description.",
                color_scheme="gray",
            ),
            rx.hstack(
                rx.input(
                    placeholder="https://www.seek.com.au/job/...",
                    value=ApplicationsState.new_url,
                    on_change=ApplicationsState.set_new_url,
                    width="100%",
                ),
                rx.button(
                    "Create",
                    on_click=ApplicationsState.create_application,
                    loading=ApplicationsState.creating,
                    size="3",
                ),
                width="100%",
            ),
            rx.cond(
                ApplicationsState.create_error != "",
                rx.callout(
                    ApplicationsState.create_error,
                    icon="triangle_alert",
                    color_scheme="red",
                ),
            ),
            spacing="4",
            width="100%",
        )
    )
