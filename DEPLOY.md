# Deploying CoverLetterer to Fly.io

This app deploys as **three tiers**:

| Tier | Fly app | What it is |
|---|---|---|
| **Database** | Supabase Postgres (external — not a Fly app) | You create the Supabase project yourself and set its connection string as `DATABASE_URL`; `deploy.sh` only validates + stages that secret, it never creates a database. |
| **Web / backend** | `coverletterer-backend` | Reflex Python backend (`reflex run --backend-only`). Serves the websocket/event API, the magic-link verify route, and (in-container) the headless-Chromium scraping fallback. |
| **Presentation / frontend** | `coverletterer-frontend` | Static SPA from `reflex export --frontend-only`, served by nginx. |

```
browser ──https──▶ coverletterer-frontend (nginx, static SPA)
   │                     │ (backend URL baked in at build time)
   └──wss / https──▶ coverletterer-backend (Reflex) ──▶ Supabase Postgres
                          │
                          └── Tigris (object storage): resume PDFs
```

The frontend is built with the backend's public URL baked in (`REFLEX_API_URL`),
so the SPA connects to `wss://coverletterer-backend.fly.dev/_event` and talks
to the backend for uploads/exports.

---

## Prerequisites

- [`flyctl`](https://fly.io/docs/flyctl/install/) installed and logged in: `fly auth login`
- A **Supabase project** with its connection string (see **Database (Supabase)**
  below) — `deploy.sh` refuses to deploy without this.
- A local **`.env`** (copy from `.env.example`) containing at least:
  - `DATABASE_URL` — the Supabase connection string (**required**)
  - `ANTHROPIC_API_KEY`
  - optional: `SMTP_HOSTNAME`/`SMTP_USERNAME`/`SMTP_PASSWORD` (passwordless
    email sign-in)
  - the `AWS_*`/`BUCKET_NAME` storage vars are **not** set here for
    production — Fly injects them when you attach Tigris. Those `.env`
    values are for **local dev** (MinIO) and must **not** reach prod.
- Docker is **not** required to deploy (Fly builds images remotely), but **is**
  required for local development (MinIO via `docker compose`).

### Headless Chromium in the backend image

CoverLetterer falls back to a headless-browser fetch when a job board blocks
a direct HTTP request (confirmed necessary for Indeed) and uses the same
fetch path for resume URLs. `Dockerfile.backend` runs `playwright install
--with-deps chromium`, which pulls in Chromium's apt dependencies — expect a
noticeably bigger image and a slower first build than a typical Reflex app.

---

## Database (Supabase)

1. Create a project at [supabase.com](https://supabase.com) (or use an
   existing one).
2. **Project Settings → Database → Connection string** → copy the
   **Session pooler** string (port `5432`, host
   `aws-0-<region>.pooler.supabase.com`, username `postgres.<project-ref>`).
   Use this one, not the others:
   - **Session pooler (recommended)** — behaves like a normal persistent
     Postgres connection, works fine with `psycopg`'s prepared statements out
     of the box. Right fit for a single long-lived Reflex backend process.
   - **Transaction pooler** (port `6543`) — for serverless/edge-function
     style ephemeral clients; needs extra SQLAlchemy tuning (disabling
     prepared-statement caching, `NullPool`) that this app doesn't set up.
     Skip unless you're intentionally scaling out to many short-lived
     connections.
   - **Direct connection** (`db.<project-ref>.supabase.co`) — IPv6-only
     unless you buy the IPv4 add-on; avoid for Fly.
3. Put it in `.env`:
   ```bash
   DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
4. `./deploy.sh` stages it as a Fly secret on first run. The backend
   container applies Alembic migrations against it on every boot
   (`entrypoint.sh` runs `reflex db migrate` before starting the server).

Free-tier Supabase projects **pause after a period of inactivity** — the
first request after a pause is slow while it wakes up; see Troubleshooting.

---

## One-command deploy

```bash
./deploy.sh
```

Defaults: prefix `coverletterer`, region `syd`. Override via env vars:

```bash
PREFIX=myapp REGION=lhr ORG=my-org ./deploy.sh
```

The script is **idempotent** — re-run it any time to redeploy.

### What `deploy.sh` does

1. Preflight: checks `flyctl`, login, and that `.env` exists.
2. Creates the two apps if missing (`coverletterer-backend`, `coverletterer-frontend`).
3. **Database**: requires `DATABASE_URL` to already be set (in `.env` or as
   an existing Fly secret on the backend) — **exits with instructions if
   it's missing**. Never provisions a database itself.
4. **Object storage**: provisions **Tigris** (`fly storage create` → sets
   `AWS_*`/`BUCKET_NAME`/`AWS_ENDPOINT_URL_S3` secrets). Skipped once the
   secrets exist.
5. **Secrets**: stages `ANTHROPIC_API_KEY` / SMTP creds from `.env`.
6. **Backend deploy**: `fly deploy -c fly.backend.toml` (URLs/CORS via
   `--env`). On boot the container applies migrations then starts the
   backend. This is the slow step — the image bundles headless Chromium.
7. **Frontend deploy**: `fly deploy -c fly.frontend.toml` with the backend
   URL baked in.
8. Prints both URLs.

#### Provisioning Tigris manually (if the CLI differs)

```bash
fly storage create --app coverletterer-backend
```

### Local development (MinIO)

```bash
docker compose up -d           # MinIO (object storage) + bucket init
# .env: the "Object storage" section (localhost values)
uv run reflex run
```
MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`).

---

## Custom domains (optional)

To serve the app on your own domains instead of the `*.fly.dev` URLs:

1. Create **CNAME** DNS records pointing your domains at the fly.dev URLs, e.g.
   `app.example.com → coverletterer-frontend.fly.dev` and
   `api.example.com → coverletterer-backend.fly.dev`.
2. Set them in `.env` (read by `deploy.sh`, not the app) — bare host or full URL:
   ```bash
   FRONTEND_DOMAIN=app.example.com
   BACKEND_DOMAIN=api.example.com
   ```
3. `./deploy.sh` — it then:
   - runs `fly certs add` for each custom domain (Fly auto-validates via your DNS);
   - sets `REFLEX_DEPLOY_URL`, app `FRONTEND_URL`/`BACKEND_URL` to the custom domains;
   - sets `REFLEX_CORS_ALLOWED_ORIGINS` to **both** the custom and fly.dev frontend
     origins (so the app works loaded from either).

**How traffic flows:** the browser SPA always connects to the **fly.dev backend**
(`REFLEX_API_URL`, baked at build — always has a valid cert, no race). The custom
**backend** domain is used for branded **magic-link URLs** only. So a
not-yet-issued custom cert can't break the live app's websocket.

Watch cert issuance: `fly certs show app.example.com --app coverletterer-frontend`.
Preview the resolved wiring without deploying: `PRINT_ONLY=1 ./deploy.sh`.

Leave `FRONTEND_DOMAIN`/`BACKEND_DOMAIN` unset to keep using the fly.dev URLs.

---

## First-time post-deploy steps

### Seed a QA user (optional)
The database starts empty — register a user in the UI, or seed the QA account:

```bash
fly ssh console --app coverletterer-backend \
  -C "uv run --no-sync python scripts/create_qa_user.py"
# → change_me / ChangeMe!2026 (or pass your own username/password)
```

---

## Verifying a deployment

```bash
fly logs --app coverletterer-backend     # expect: "Applying database migrations" → "App Running"
curl -s -o /dev/null -w '%{http_code}\n' https://coverletterer-backend.fly.dev/ping   # 200
open https://coverletterer-frontend.fly.dev
```

Then in the browser: register/login → set a resume on the Profile page →
create an application with the **Indeed** sample URL specifically (exercises
the in-container Playwright fallback — the highest-risk new path) → generate
a draft → export PDF.

---

## Redeploying after code changes

Just re-run `./deploy.sh`. Notes:

- **Schema changes**: create the migration locally first
  (`uv run reflex db makemigrations --message "…"`), commit it under `alembic/`,
  then deploy — the backend entrypoint applies pending migrations on boot.
- **Frontend-only change**: the frontend is rebuilt each deploy with the backend
  URL baked in; no manual step needed.
- **New secret**: add it to `.env` and re-run `./deploy.sh` (or
  `fly secrets set --app coverletterer-backend KEY=value`).

---

## Configuration reference

Set in `fly.backend.toml` `[env]` (overridden by `deploy.sh` per `PREFIX` and
custom domains). The values below are the fly.dev defaults:

| Variable | Value | Why |
|---|---|---|
| `REFLEX_API_URL` | `https://coverletterer-backend.fly.dev` | Backend origin the SPA uses (**stays fly.dev** even with a custom backend domain) |
| `REFLEX_DEPLOY_URL` | custom or fly.dev frontend | Frontend public URL |
| `REFLEX_CORS_ALLOWED_ORIGINS` | custom + fly.dev frontend | Allows the SPA's websocket/API calls from either origin |
| `BACKEND_URL` / `FRONTEND_URL` | custom or fly.dev URLs | Magic-link browser navigations |

Deploy-time only (read by `deploy.sh`, not the app): `FRONTEND_DOMAIN`,
`BACKEND_DOMAIN` — the custom domains (default to fly.dev). See **Custom domains**.

Secrets (never in toml): `ANTHROPIC_API_KEY`,
`SMTP_HOSTNAME`/`SMTP_USERNAME`/`SMTP_PASSWORD` (+ optional `SMTP_PORT`/`SMTP_FROM`/`SMTP_STARTTLS`),
`DATABASE_URL` (a Supabase connection string — **you** set this in `.env`; `deploy.sh` stages it, it does not create it),
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_ENDPOINT_URL_S3`/`BUCKET_NAME`
(via `fly storage create` — Tigris).

---

## Troubleshooting

- **`DATABASE_URL is not set` and `deploy.sh` exits**: expected — see
  **Database (Supabase)** above. Set it in `.env` and re-run.
- **Prepared-statement / "cached plan must not change result type" errors**:
  you're likely on the Supabase **Transaction pooler** (port `6543`) instead
  of the **Session pooler** (port `5432`). Switch the connection string.
- **Connection refused / timeouts to Supabase**: free-tier projects
  auto-pause after inactivity — open the Supabase dashboard once to wake it,
  or upgrade to avoid pausing.
- **`fly deploy` for the backend is slow / image is large**: expected —
  `playwright install --with-deps chromium` in `Dockerfile.backend` adds real
  size and build time. Not a bug.
- **Job-ad scraping errors in `fly logs`**: check whether the failure is
  "manual paste" (expected — both the direct fetch and the Chromium fallback
  failed for that specific URL) versus a genuine Chromium/Playwright crash
  (would show a Python traceback from `services/browser_fetch.py`).
- **App name taken**: Fly names are global — re-run with `PREFIX=…`.

---

## Scaling

Currently a **single always-on machine** (`min_machines_running = 1`, no
Redis) — CoverLetterer's Reflex state is in-memory, which is fine at this
traffic level, and there's no persistent volume (resume PDFs live in Tigris).

To scale the backend to multiple machines later, mirror `~/web/reflex`'s
recipe: provision Redis (`fly redis create`, set `REDIS_URL`) so Reflex
switches to its Redis-backed state manager, then `fly scale count N --app
coverletterer-backend`. Not needed yet — this is a pointer for later, not
part of the current deploy.
