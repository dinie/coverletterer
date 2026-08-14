"""A drop-in replacement for `reflex_local_auth.require_login` with a nicer
hydrating state — a centered spinner instead of bare "Loading..." text.

Behaviour matches the upstream decorator: render the page only once the client
is hydrated *and* authenticated; otherwise show the loading state, whose
`on_mount` triggers `LoginState.redir` (redirect to /login if unauthenticated).
"""

from __future__ import annotations

import reflex as rx
import reflex_local_auth
from reflex_local_auth.login import LoginState


def _hydrating() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text("Loading your workspace…", color_scheme="gray", size="2"),
            spacing="3",
            align="center",
        ),
        # When this mounts (i.e. not yet authenticated/hydrated), decide whether
        # to redirect to the login page.
        on_mount=LoginState.redir,
        width="100%",
        min_height="100vh",
    )


def require_login(page: rx.app.ComponentCallable) -> rx.app.ComponentCallable:
    def protected_page() -> rx.Component:
        return rx.fragment(
            rx.cond(
                LoginState.is_hydrated & LoginState.is_authenticated,  # type: ignore[operator]
                page(),
                _hydrating(),
            )
        )

    protected_page.__name__ = page.__name__
    return protected_page
