"""Personal access tokens for the browser extension.

Only the SHA-256 hash of the token is persisted; the raw token is shown to
the user once, at generation time. At most one token per user — generating a
new one invalidates the old (single-extension use case, no token list needed).
"""

from __future__ import annotations

import datetime
import hashlib
import secrets

import reflex as rx
from sqlmodel import select

from ..models import ApiToken


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate(user_id: int) -> str:
    """Mint a new token for `user_id`, replacing any existing one. Returns
    the raw token (only ever available at generation time)."""
    raw = secrets.token_urlsafe(32)
    with rx.session() as session:
        row = session.exec(
            select(ApiToken).where(ApiToken.user_id == user_id)
        ).one_or_none()
        if row is None:
            row = ApiToken(user_id=user_id)  # type: ignore[call-arg]
        row.token_hash = _hash(raw)
        session.add(row)
        session.commit()
    return raw


def resolve(raw: str) -> int | None:
    """Validate a bearer token. Returns the owning user_id, or None."""
    if not raw:
        return None
    with rx.session() as session:
        row = session.exec(
            select(ApiToken).where(ApiToken.token_hash == _hash(raw))
        ).one_or_none()
        return row.user_id if row is not None else None


def exists(user_id: int) -> bool:
    with rx.session() as session:
        row = session.exec(
            select(ApiToken).where(ApiToken.user_id == user_id)
        ).one_or_none()
        return row is not None


def created_at(user_id: int) -> datetime.datetime | None:
    with rx.session() as session:
        row = session.exec(
            select(ApiToken).where(ApiToken.user_id == user_id)
        ).one_or_none()
        return row.created_at if row is not None else None


def revoke(user_id: int) -> None:
    with rx.session() as session:
        row = session.exec(
            select(ApiToken).where(ApiToken.user_id == user_id)
        ).one_or_none()
        if row is not None:
            session.delete(row)
            session.commit()
