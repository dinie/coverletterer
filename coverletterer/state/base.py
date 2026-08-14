"""Auth-aware base state.

Inheriting from `reflex_local_auth.LocalAuthState` gives every app substate
access to `self.authenticated_user` and `self.is_authenticated`.
"""

from __future__ import annotations

import reflex_local_auth


class AppState(reflex_local_auth.LocalAuthState):
    """Shared base for all application states."""

    @property
    def user_id(self) -> int:
        """The current user's id, or -1 when unauthenticated."""
        uid = self.authenticated_user.id
        return uid if uid is not None else -1
