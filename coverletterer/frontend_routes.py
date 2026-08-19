"""Serves the SPA shell for any request that doesn't match a real route.

Wired in as the Starlette Router's `.default` handler rather than a
registered `Route` — Reflex's own internal endpoints (`/ping`, `/_upload`,
etc.) are added lazily during `app._compile()`, which runs *after* this
module's top-level code, so a normal eagerly-registered wildcard route here
would incorrectly shadow them (confirmed: Starlette's `Router.app` matches
`self.routes` in registration order, first `Match.FULL` wins). `.default` is
different — Starlette only calls it once nothing in `self.routes` matched at
all, which is exactly "this is a client-side page route, not a real
endpoint" — order-independent by construction.

`static_shell/index.html` is staged by `deploy.sh` from Reflex's own
`__spa-fallback.html` output (identical to its `404.html`) — a route-agnostic
app shell with no page-specific preloads or title, unlike the *exported*
`index.html`, which is the pre-rendered `/` dashboard page specifically.
`deploy.sh` restages it fresh on every deploy; see DEPLOY.md.
"""

from __future__ import annotations

from pathlib import Path

import reflex as rx
from starlette.responses import FileResponse, PlainTextResponse
from starlette.types import Receive, Scope, Send

_SHELL_PATH = Path(__file__).parent.parent / "static_shell" / "index.html"


async def _spa_shell(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http" or scope["method"] != "GET" or not _SHELL_PATH.is_file():
        await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
        return
    await FileResponse(_SHELL_PATH, media_type="text/html")(scope, receive, send)


def register(app: rx.App) -> None:
    """Install the SPA-shell fallback as the backend's last-resort handler."""
    app._api.router.default = _spa_shell
