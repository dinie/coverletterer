"""Seed a QA / superuser login account.

`reflex_local_auth` has no role column, so this just creates an *enabled*
LocalUser with known credentials for QA testing. Idempotent: re-running resets
the password and ensures the account is enabled.

Usage:
    python scripts/create_qa_user.py [username] [password]

Defaults: username=change_me, password=ChangeMe!2026
Env overrides: QA_USERNAME, QA_PASSWORD
"""

from __future__ import annotations

import os
import sys

import reflex as rx
from sqlmodel import select

from reflex_local_auth.user import LocalUser

DEFAULT_USERNAME = "change_me"
DEFAULT_PASSWORD = "ChangeMe!2026"


def main() -> None:
    username = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("QA_USERNAME", DEFAULT_USERNAME)
    )
    password = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.environ.get("QA_PASSWORD", DEFAULT_PASSWORD)
    )

    with rx.session() as session:
        user = session.exec(
            select(LocalUser).where(LocalUser.username == username)
        ).one_or_none()
        action = "Updated existing"
        if user is None:
            user = LocalUser()  # type: ignore[call-arg]
            user.username = username
            action = "Created"
        user.password_hash = LocalUser.hash_password(password)
        user.enabled = True
        session.add(user)
        session.commit()
        session.refresh(user)

    print(f"{action} QA account:")
    print(f"  id:       {user.id}")
    print(f"  username: {username}")
    print(f"  password: {password}")
    print(f"  enabled:  {user.enabled}")


if __name__ == "__main__":
    main()
