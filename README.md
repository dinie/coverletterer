# CoverLetterer

Generate tailored cover letters for software engineering job ads. Give it
your resume (a PDF upload or a URL) and a job ad URL and it scrapes the job 
description, drafts a cover letter with **Claude**, and lets you edit, save, 
and **export it as a PDF**, all from a personal dashboard.

Built using the [Reflex](https://reflex.dev) full-stack Python framework.

Register a username and password, or use the passwordless sign-in feature to
login and start experimenting.

Currently supports the following job ad sources:
- [x] LinkedIn
- [x] Indeed
- [x] SEEK

Also included is a Chrome browser extension to expedite user workflow even
further. More details found [here](browser-extension/README.md).

---

## How it works

```
resume (PDF upload or URL) ──┐
                              ├──▶ Claude ──▶ cover-letter draft ──▶ edit → save → export PDF
job ad URL ───────────────────┘
   scrape: direct fetch → headless-browser (Playwright) fallback → manual paste
```

> **Why the fallback chain?** SEEK and LinkedIn serve the job description as
> plain server-rendered HTML, so a direct `httpx` fetch works. Indeed blocks
> non-browser HTTP clients with a Cloudflare challenge, so that fetch fails
> over to a headless Chromium fetch (via Playwright). If *that* also fails —
> or a future, not-yet-supported site is pasted in — the app asks the user to
> paste the job description directly rather than blocking the flow entirely.

Each job board has its own small, independent parser
(`coverletterer/job_sources/`), so adding a new source or fixing one that
breaks doesn't touch the others.

---

## Features

- **Three job-ad sources** — SEEK, Indeed, LinkedIn — each with the
  direct-fetch → Playwright-fallback → manual-paste chain described above.
- **Resume ingestion** — upload a PDF or point at a URL. One account-level
  **default** resume, optionally **overridden per application** (e.g. a
  tailored resume for one specific role).
- **Claude-generated cover-letter drafts**, tailored to the job description
  and resume — editable, with multiple drafts per application.
- **Export to PDF**, generated on demand from the current draft text.
- **Per-user dashboard** — list, open, and delete job applications.
- **Authentication** — username/password
  ([`reflex-local-auth`](https://pypi.org/project/reflex-local-auth/)) and
  optional **passwordless sign-in** via an emailed magic link (SMTP).
- **Browser extension** — one-click "add this job" from any job-ad page,
  authenticated with a personal access token (see
  [`browser-extension/README.md`](browser-extension/README.md)).
- **Tests** — a `pytest` suite for the core logic.
- **Deployable** — 3-tier Fly.io setup with a Supabase-hosted database (see
  [DEPLOY.md](DEPLOY.md)).

---

## Tech stack

| Concern | Choice |
|---|---|
| Web framework | Reflex 0.9.x (Python frontend + backend) |
| Job-ad scraping | `httpx` + `BeautifulSoup` (direct fetch), Playwright/Chromium (fallback) |
| Resume parsing | `pypdf` (PDF uploads), generic HTML text extraction (URLs) |
| LLM | Claude via the `anthropic` SDK |
| PDF export | `reportlab` |
| Auth | `reflex-local-auth` + magic-link (SMTP) |
| Database | SQLite (dev) / PostgreSQL via SQLModel + Alembic (prod — Supabase) |
| Object storage | S3-compatible: MinIO (dev) / Tigris (prod) |
| Browser extension | Manifest V3, personal-access-token auth |
| Packaging | `uv` |

---

## Prerequisites

- **Python 3.12** (managed by [`uv`](https://docs.astral.sh/uv/)).
- **Node 22** — the repo pins it via `.nvmrc` (`nvm use`). Reflex needs it to
  compile the app.
- An **Anthropic** API key.
- **Docker** (for local object storage via `docker compose`).

---

## Setup & run (local dev)

```bash
# 1. Node version (Reflex needs 22.12+)
nvm use                       # reads .nvmrc → Node 22.13.1

# 2. Python deps
uv sync                       # creates .venv from pyproject.toml + uv.lock
uv run playwright install chromium   # headless-browser fallback for blocked job boards

# 3. Configure secrets
cp .env.example .env          # then fill in ANTHROPIC_API_KEY (see below)

# 4. Backing service: object storage (MinIO)
docker compose up -d          # MinIO + bucket init (see docker-compose.yml)

# 5. Database (SQLite by default; migrations are committed under alembic/)
uv run reflex db migrate

# 6. Run it
uv run reflex run
```

Then open **http://localhost:3000** (backend runs on `:8000`).

### Seed a QA user (optional)

```bash
uv run python scripts/create_qa_user.py     # → change_me / ChangeMe!2026
```

Or just register a new account in the UI.

---

## Configuration

Copy `.env.example` → `.env` and fill in:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude — generates each cover-letter draft |
| `SMTP_HOSTNAME` / `SMTP_USERNAME` / `SMTP_PASSWORD` | — | Enables passwordless magic-link sign-in (optional `SMTP_PORT`/`SMTP_FROM`/`SMTP_STARTTLS`) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_ENDPOINT_URL_S3` / `BUCKET_NAME` | ✅ | Object storage for resume PDFs (MinIO locally; Tigris in prod) |
| `DATABASE_URL` | — locally / ✅ to deploy | Postgres URL. Defaults to local SQLite when unset; **required** for the Fly.io deploy — a Supabase connection string, see [DEPLOY.md](DEPLOY.md) |
| `FRONTEND_URL` / `BACKEND_URL` | — | Used to build magic-link URLs |

`.env` is loaded automatically (via `python-dotenv` in `rxconfig.py`).

---

## Using the app

1. **Log in / register** (or use the QA account).
2. **Set your default resume** on the **Profile** page — upload a PDF or
   point at a URL.
3. **New application** → paste a job ad URL. The description is scraped
   automatically; if a site blocks that, you're prompted to paste it in.
4. On the application page: **override the resume** for just this
   application if you want, then **Generate draft** (Claude). Edit, save, and
   **export as PDF**.
5. Or skip 3–4 entirely: install the [browser extension](browser-extension/),
   generate a personal token on the Profile page, and one-click "capture" any
   job-ad page straight into your dashboard.

---

## Project structure

```
rxconfig.py                 # Reflex config (app name, DB URL, plugins)
coverletterer/
├── coverletterer.py         # app + page/route registration
├── config.py                # env-sourced settings
├── models.py                # SQLModel tables
├── schemas.py                # typed view-models for the UI
├── auth_routes.py             # Starlette route: magic-link verify
├── api_routes.py               # Starlette routes: browser-extension API
├── job_sources/                 # pluggable per-site job-ad parsers
│   ├── seek.py, indeed.py, linkedin.py, generic.py
│   └── __init__.py                # fetch_job_posting() dispatcher
├── services/                        # pure business logic (no Reflex state)
│   ├── application_ingest.py          # shared create+parse logic
│   ├── resume_ingest.py, cover_letter.py, pdf_export.py
│   ├── storage.py, browser_fetch.py
│   └── magic_link.py, email.py, api_tokens.py
├── state/                             # profile_state, applications_state,
│                                       #   draft_state (background events)
├── pages/                              # index, profile, new_application,
│                                        #   application/[id], auth_pages
└── components/                          # navbar, require_login
alembic/                     # DB migrations
tests/                       # pytest suite
browser-extension/           # Manifest V3 Chrome extension
Dockerfile.* / fly.*.toml / deploy.sh / DEPLOY.md   # Fly.io deployment
```

---

## Testing

```bash
uv run pytest
```

Covers job-ad parsing for SEEK/Indeed/LinkedIn (fixture HTML, no live
network) and the domain-routing dispatcher, resume ingestion + the
default-vs-override resolution logic, cover-letter prompt construction, PDF
export, magic-link tokens, the per-user unique-URL database constraint, and
the create/parse logic shared by the web UI and the browser extension.

---

## Deployment

A 3-tier Fly.io deployment (static frontend + Reflex backend + **Supabase**
Postgres) is fully scripted. See **[DEPLOY.md](DEPLOY.md)** — TL;DR:

```bash
fly auth login
./deploy.sh
```

`deploy.sh` **requires `DATABASE_URL`** (a Supabase connection string) to
already be set in `.env` — it never provisions a database itself, and exits
with setup instructions if it's missing. Custom domains are supported via
`FRONTEND_DOMAIN`/`BACKEND_DOMAIN`; see DEPLOY.md.

---

## Notes & limitations

- **Scraping is inherently fragile** — job boards can change their markup or
  bot-detection at any time. Each source is an independent parser with its
  own direct-fetch → Playwright → manual-paste fallback chain, so a break in
  one doesn't affect the others, and manual paste always keeps the flow
  unblocked.
- **Headless Chromium** (the Playwright fallback) adds real latency — several
  seconds — and a noticeably larger backend Docker image; it's only invoked
  when the direct fetch fails.
- **Single-process state** — no Redis yet, so the backend is designed to run
  as a single instance (see DEPLOY.md's Scaling section for the upgrade path
  if that's ever needed).
