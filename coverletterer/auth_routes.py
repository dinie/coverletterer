"""Backend (Starlette) route for magic-link email sign-in, registered on
app._api.

Finds/creates a LocalUser by email, mints a LocalAuthSession token, and
redirects to the frontend /auth/complete/<token> page, which stores the token
in LocalStorage so reflex_local_auth recognizes the session.
"""

from __future__ import annotations

import datetime
import secrets

import reflex as rx
from reflex_local_auth.auth_session import LocalAuthSession
from reflex_local_auth.user import LocalUser
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import RedirectResponse

from . import config
from .services import magic_link

_SESSION_DAYS = 7


def _fail(reason: str) -> RedirectResponse:
    return RedirectResponse(f"{config.FRONTEND_URL}/login?error={reason}")


def login_user_by_email(email: str, days: int = _SESSION_DAYS) -> str:
    """Find or create a LocalUser by email, mint a LocalAuthSession, return its token.

    New emails auto-create an account with a random unusable password (they
    sign in via email only).
    """
    with rx.session() as session:
        user = session.exec(
            select(LocalUser).where(LocalUser.username == email)
        ).one_or_none()
        if user is None:
            user = LocalUser()  # type: ignore[call-arg]
            user.username = email
            user.password_hash = LocalUser.hash_password(secrets.token_urlsafe(32))
            user.enabled = True
            session.add(user)
            session.commit()
            session.refresh(user)
        user_id = user.id

        token = secrets.token_urlsafe(32)
        session.add(
            LocalAuthSession(  # type: ignore[call-arg]
                user_id=user_id,
                session_id=token,
                expiration=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=days),
            )
        )
        session.commit()
    return token


async def magic_verify(request: Request) -> RedirectResponse:
    """Verify an emailed magic-link token and sign the user in."""
    email = magic_link.consume_token(request.query_params.get("token", ""))
    if not email:
        return _fail("magic_invalid")
    token = login_user_by_email(email)
    return RedirectResponse(f"{config.FRONTEND_URL}/auth/complete/{token}")


def register(app: rx.App) -> None:
    """Attach the auth routes to the Reflex backend (Starlette)."""
    app._api.add_route("/auth/magic/verify", magic_verify, methods=["GET"])
