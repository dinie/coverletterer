"""Auth-aware top navigation."""

from __future__ import annotations

import reflex as rx
import reflex_local_auth


def navbar() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("file-text", size=24),
                rx.heading("CoverLetterer", size="5"),
                align="center",
                spacing="2",
            ),
            href="/",
            underline="none",
            color="inherit",
        ),
        rx.spacer(),
        rx.cond(
            reflex_local_auth.LocalAuthState.is_authenticated,
            rx.hstack(
                rx.link("Dashboard", href="/"),
                rx.link("Resume", href="/profile"),
                rx.link("New application", href="/new"),
                rx.text(
                    reflex_local_auth.LocalAuthState.authenticated_user.username,
                    weight="medium",
                ),
                rx.button(
                    "Logout",
                    on_click=[
                        reflex_local_auth.LocalAuthState.do_logout,
                        rx.redirect(reflex_local_auth.routes.LOGIN_ROUTE),
                    ],
                    variant="soft",
                    size="2",
                ),
                align="center",
                spacing="4",
            ),
            rx.hstack(
                rx.link("Login", href=reflex_local_auth.routes.LOGIN_ROUTE),
                rx.link("Register", href=reflex_local_auth.routes.REGISTER_ROUTE),
                spacing="4",
            ),
        ),
        width="100%",
        padding="1rem 1.5rem",
        border_bottom="1px solid var(--gray-4)",
        align="center",
    )


def layout(*children: rx.Component) -> rx.Component:
    """Page shell: navbar + centered container."""
    return rx.vstack(
        navbar(),
        rx.container(*children, padding_y="1.5rem"),
        width="100%",
        spacing="0",
        min_height="100vh",
    )
