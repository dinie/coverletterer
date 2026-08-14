"""Resume + job ad -> tailored cover letter drafts.

Pipeline: user supplies a resume (PDF upload or URL) and a job ad URL -> the
app scrapes the job description (direct fetch, falling back to a headless
browser, falling back to manual paste) -> Claude drafts a cover letter from
the resume + description -> the user edits, saves, and exports drafts as PDF.
"""

import reflex as rx
import reflex_local_auth

from . import auth_routes, models  # noqa: F401  (models registers tables)
from .pages.application import application_page
from .pages.auth_pages import auth_complete_page, login_page
from .pages.index import index
from .pages.new_application import new_application_page
from .pages.profile import profile_page
from .state.applications_state import ApplicationsState
from .state.auth_state import AuthCompleteState
from .state.draft_state import DraftState
from .state.profile_state import ProfileState

app = rx.App()

# Application pages (all gated by our require_login wrapper in components/auth.py).
app.add_page(index, route="/", title="Dashboard", on_load=ApplicationsState.load_applications)
app.add_page(profile_page, route="/profile", title="Resume", on_load=ProfileState.load_resume)
app.add_page(new_application_page, route="/new", title="New Application")
app.add_page(
    application_page,
    route="/application/[application_id]",
    title="Application",
    on_load=DraftState.load_application,
)

# Authentication: custom login (username/password + magic link) and the
# package's register page.
app.add_page(
    login_page,
    route=reflex_local_auth.routes.LOGIN_ROUTE,
    title="Login",
)
app.add_page(
    reflex_local_auth.pages.register_page,
    route=reflex_local_auth.routes.REGISTER_ROUTE,
    title="Register",
)
app.add_page(
    auth_complete_page,
    route="/auth/complete/[token]",
    title="Signing in…",
    on_load=AuthCompleteState.complete,
)

# Backend (Starlette) route for the magic-link verify flow.
auth_routes.register(app)
