"""Backend (Starlette) API routes for the browser extension.

Bearer-token auth (`Authorization: Bearer <token>`), entirely decoupled from
the `reflex_local_auth` browser session — see `services/api_tokens.py`. The
extension never touches the Reflex websocket/session machinery.
"""

from __future__ import annotations

import asyncio

import reflex as rx
from reflex_local_auth.user import LocalUser
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import Status
from .services import api_tokens, application_ingest


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[len("bearer "):].strip()
    return ""


async def _authenticate(request: Request) -> int | None:
    token = _bearer_token(request)
    if not token:
        return None
    return await asyncio.to_thread(api_tokens.resolve, token)


async def me(request: Request) -> JSONResponse:
    """Validate the bearer token. Used by the extension's options page to
    confirm a token + backend URL are correctly configured."""
    user_id = await _authenticate(request)
    if user_id is None:
        return JSONResponse({"error": "invalid or missing token"}, status_code=401)

    def _lookup() -> str | None:
        with rx.session() as session:
            user = session.get(LocalUser, user_id)
            return user.username if user else None

    username = await asyncio.to_thread(_lookup)
    if username is None:
        return JSONResponse({"error": "user not found"}, status_code=401)
    return JSONResponse({"username": username})


async def create_application(request: Request) -> JSONResponse:
    """Create (or return the existing) JobApplication for a URL.

    Idempotent: a URL already tracked by this user is returned as-is (no
    re-parse) rather than treated as an error — the extension shows this as
    "already added".
    """
    user_id = await _authenticate(request)
    if user_id is None:
        return JSONResponse({"error": "invalid or missing token"}, status_code=401)

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)

    app, created = await asyncio.to_thread(application_ingest.get_or_create, user_id, url)
    if created and app.status == Status.PARSING:
        parsed = await asyncio.to_thread(application_ingest.parse_and_persist, app.id)
        if parsed is not None:
            app = parsed

    return JSONResponse(
        {
            "application_id": app.id,
            "job_title": app.job_title,
            "company": app.company,
            "site": app.site,
            "status": app.status,
            "already_existed": not created,
        }
    )


def register(app: rx.App) -> None:
    """Attach the browser-extension API routes to the Reflex backend (Starlette)."""
    app._api.add_route("/api/me", me, methods=["GET"])
    app._api.add_route("/api/applications", create_application, methods=["POST"])
