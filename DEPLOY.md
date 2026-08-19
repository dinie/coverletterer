# Deploying CoverLetterer to Fly.io

This app deploys as **one Fly app** plus two external/managed pieces:

| Tier | Fly app | What it is |
|---|---|---|
| **Database** | Supabase Postgres (external — not a Fly app) | You create the Supabase project yourself and set its connection string as `DATABASE_URL`; `deploy.sh` only validates + stages that secret, it never creates a database. |
| **Static assets** | Tigris bucket `coverletterer-frontend` (not a Fly app — object storage) | The exported SPA's hashed JS/CSS, served straight from Tigris by **Fly's edge proxy** via `[[statics]]` in `fly.backend.toml` — bypasses the app entirely for these requests. |
| **Web / backend** | `coverletterer-backend` | Reflex Python backend (`reflex run --backend-only`). Serves the websocket/event API, the magic-link verify + browser-extension routes, **and** the SPA shell HTML for every page route (`coverletterer/frontend_routes.py`), and the headless-Chromium scraping fallback. |

```
                       ┌─▶ /assets/* ──▶ Tigris bucket (Fly proxy, bypasses the app)
browser ──https──▶ coverletterer-backend
                       └─▶ everything else ──▶ Reflex (page routes → SPA shell,
                                                 /api, /auth, /_event websocket)
                                                        │
                                                        ├──▶ Supabase Postgres
                                                        └──▶ Tigris (private): resume PDFs
```

There's no separate frontend app or nginx anymore — frontend and backend are
the same origin, so there's no cross-origin CORS split between them either.

---

## Prerequisites

- [`flyctl`](https://fly.io/docs/flyctl/install/) installed and logged in: `fly auth login`
- A **Supabase project** with its connection string (see **Database
  (Supabase)** below) — `deploy.sh` refuses to deploy without this.
- A **Tigris bucket for static assets** (see **Static assets (Tigris)**
  below) — same deal, `deploy.sh` refuses to deploy without this too.
- A local **`.env`** (copy from `.env.example`) containing at least:
  - `DATABASE_URL` — the Supabase connection string (**required**)
  - `FRONTEND_BUCKET_NAME` / `FRONTEND_AWS_ACCESS_KEY_ID` /
    `FRONTEND_AWS_SECRET_ACCESS_KEY` / `FRONTEND_AWS_ENDPOINT_URL_S3` — the
    static-assets Tigris bucket's credentials (**required**)
  - `ANTHROPIC_API_KEY`
  - optional: `SMTP_HOSTNAME`/`SMTP_USERNAME`/`SMTP_PASSWORD` (passwordless
    email sign-in)
  - the plain `AWS_*`/`BUCKET_NAME` vars (no `FRONTEND_` prefix) are **not**
    set here for production — Fly injects them onto the app when you attach
    the private resume-PDF Tigris bucket. Those `.env` values are for
    **local dev** (MinIO) and must **not** reach prod.
- **Node + `uv` locally** — `deploy.sh` runs `reflex export --frontend-only`
  on your machine (not inside the Docker build) so the uploaded assets and
  the image's baked-in SPA shell always come from the same export; see
  below. Docker itself is **not** required (Fly builds the backend image
  remotely), but is required for local development (MinIO via `docker
  compose`).

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

## Static assets (Tigris)

Fly's `[[statics]]` config can serve files straight from a Tigris bucket
(docs: [fly.io/docs/reference/configuration/#the-statics-sections](https://fly.io/docs/reference/configuration/#the-statics-sections)),
bypassing the app process entirely — no separate frontend container needed.
Two things worth knowing before relying on this:

- **It has no SPA-routing fallback.** `[[statics]]`/`index_document` only
  serves `index.html` for exact directory-style paths ending in `/` — a
  request to `/application/42` isn't covered. That's why
  `coverletterer/frontend_routes.py` exists: it's wired in as the backend's
  Starlette **`Router.default`** handler (not a normal route — see that
  file's docstring for why: Reflex's own internal endpoints like `/ping`
  register *after* our module's code runs, so a naively-registered wildcard
  route would shadow them; `.default` only fires when nothing else matched
  at all, so it's immune to that ordering issue) and serves the app shell
  for every page-route request. Confirmed by direct testing: before this
  fallback, `/application/<id>` returned an HTTP 404 (with usable HTML in
  the body — browsers render it fine, which is why this was easy to miss);
  it's a real 200 now.
- **Fly doesn't document how files get *into* a `[[statics]]` bucket** — no
  `fly deploy`-time sync exists. `deploy.sh` uploads them itself via
  `scripts/upload_static_assets.py` (`boto3`, same pattern as
  `coverletterer/services/storage.py`), **before** every `fly deploy`, so a
  freshly-deployed SPA shell never references not-yet-uploaded asset hashes.
  Old hashed files are never deleted (cheap, content-addressed, keeps
  rollback safe).
- **`[[statics]]` cannot set `Cache-Control` or any other response header**
  on served assets. Minor: filenames are already content-hashed, so this is
  a smaller caching win lost, not a correctness issue.

### One-time setup

```bash
fly storage create --name coverletterer-frontend
```

**Don't pass `--app`.** `fly storage create` ties at most **one** Tigris
bucket to a given app (confirmed: passing `--app coverletterer-backend` here
fails with `A Tigris project named coverletterer-media already exists for
app coverletterer-backend`, since that app already has the private
resume-PDF bucket attached) — this is a hard platform limit, not something
to work around in our own scripting. Omitting `--app` creates a **standalone
bucket, not attached to any app**, which sidesteps that limit entirely: no
risk of clobbering the resume-PDF bucket's `AWS_*`/`BUCKET_NAME` secrets,
and a clean separation between "public build artifacts" and "private user
files" (different privacy requirements, so worth keeping as genuinely
separate buckets rather than one bucket with key prefixes). Copy the
credentials it prints into `.env`:

```bash
FRONTEND_BUCKET_NAME=coverletterer-frontend
FRONTEND_AWS_ACCESS_KEY_ID=...
FRONTEND_AWS_SECRET_ACCESS_KEY=...
FRONTEND_AWS_ENDPOINT_URL_S3=...
```

These are **deploy-time-only** values — `deploy.sh` reads them locally to
run the upload script; they're never staged as Fly app secrets, since the
running app itself never needs to read this bucket (Fly's proxy serves it
directly).

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
2. Creates the app if missing (`coverletterer-backend`).
3. **Database**: requires `DATABASE_URL` to already be set (in `.env` or as
   an existing Fly secret) — **exits with instructions if it's missing**.
   Never provisions a database itself.
4. **Resume-PDF object storage**: provisions **Tigris** (`fly storage
   create` → sets `AWS_*`/`BUCKET_NAME` secrets). Skipped once the secrets
   exist.
5. **Frontend static-assets bucket**: requires `FRONTEND_BUCKET_NAME` +
   credentials to already be set in `.env` (see **Static assets** above) —
   **exits with instructions if missing**. Never provisions this bucket
   itself.
6. **Secrets**: stages `ANTHROPIC_API_KEY` / SMTP creds from `.env`.
7. **Export + upload**: `reflex export --frontend-only` locally, uploads the
   hashed assets to the Tigris bucket, stages the SPA shell at
   `static_shell/index.html` for the Docker build to `COPY` in.
8. **TLS cert** for a custom domain, if `APP_DOMAIN` is set (idempotent).
9. **Deploy**: `fly deploy -c fly.backend.toml` (URLs/CORS via `--env`). On
   boot the container applies migrations then starts the backend. This is
   the slow step — the image bundles headless Chromium.
10. Prints the app URL.

### Local development (MinIO)

```bash
docker compose up -d           # MinIO (object storage) + bucket init
# .env: the "Object storage" section (localhost values)
uv run reflex run
```
MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`).

Locally, static assets are served by Reflex's own dev server (or
`reflex run --env prod --single-port`, which mounts the compiled frontend
directly) — the Tigris/`[[statics]]` split only applies to the Fly
deployment.

---

## Custom domain (optional)

To serve the app on your own domain instead of the `*.fly.dev` URL:

1. Create a **CNAME** DNS record pointing your domain at the fly.dev URL,
   e.g. `app.example.com → coverletterer-backend.fly.dev`.
2. Set it in `.env` (read by `deploy.sh`, not the app) — bare host or full URL:
   ```bash
   APP_DOMAIN=app.example.com
   ```
3. `./deploy.sh` — it then:
   - runs `fly certs add` for the domain (Fly auto-validates via your DNS);
   - sets `REFLEX_DEPLOY_URL`, `BACKEND_URL`/`FRONTEND_URL` to the custom domain;
   - sets `REFLEX_CORS_ALLOWED_ORIGINS` to **both** the custom and fly.dev
     origins (so the app works loaded from either).

**How traffic flows:** the browser SPA's websocket/data connection
(`REFLEX_API_URL`, baked at build) always stays on the **fly.dev URL** —
always has a valid cert, no race. The custom domain is used for the page
load itself and for branded **magic-link URLs**. So a not-yet-issued custom
cert can't break the live app's websocket.

Watch cert issuance: `fly certs show app.example.com --app coverletterer-backend`.
Preview the resolved wiring without deploying: `PRINT_ONLY=1 ./deploy.sh`.

Leave `APP_DOMAIN` unset to keep using the fly.dev URL.

### Using Cloudflare for DNS

If your domain's DNS is on Cloudflare, the CNAME record's **proxy status**
matters for cert issuance:

- **DNS only ("grey cloud") — recommended, simplest.** Fly issues its cert
  via an HTTP-01 challenge, which needs the domain to resolve straight to
  Fly's edge. Set the record to DNS-only, run `./deploy.sh` (or `fly certs
  add app.example.com --app coverletterer-backend` directly), and wait for
  `fly certs show` to report the cert as issued.
- **Proxied ("orange cloud")** works too, but needs one extra step: with the
  proxy on, Cloudflare masks the origin IP, so Fly can't complete the normal
  HTTP-01 challenge — verify domain ownership instead by adding the
  `_fly-ownership` TXT record Fly's dashboard/`fly certs add` output gives
  you. Also set Cloudflare's SSL/TLS mode to **Full (strict)**, not
  Flexible, or the Cloudflare→Fly hop will be unencrypted/broken. This app's
  websocket connection (`REFLEX_API_URL`) always stays pinned to the
  fly.dev URL regardless of this choice (see "How traffic flows" above), so
  Cloudflare's proxy never sits in front of the live websocket either
  way — only page loads and static assets would be proxied.

**Migrating an existing record** (e.g. reusing a domain from before this
app's frontend/backend merge, when it pointed at a since-removed
`*-frontend.fly.dev` app): just update the CNAME's **target** to
`coverletterer-backend.fly.dev` and re-run `fly certs add`/`./deploy.sh` —
the domain's ownership/ACME history isn't tied to the old target, so this is
a normal DNS edit, not a teardown-and-recreate. If the old record was
proxied (orange cloud), leave it proxied; if it was DNS-only, leave it
DNS-only — no need to change that as part of the migration.

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
open https://coverletterer-backend.fly.dev
```

Then in the browser: register/login → set a resume on the Profile page →
create an application with the **Indeed** sample URL specifically (exercises
the in-container Playwright fallback — the highest-risk scraping path) →
generate a draft → export PDF. Also **hard-refresh** (not just client-side
navigate) a `/application/<id>` URL directly — the highest-risk *routing*
path, since it has no pre-rendered HTML at all — and confirm it loads
correctly with a `200`, and that its JS/CSS load from the Tigris-backed
`/assets/*` URLs (check the Network tab).

---

## Redeploying after code changes

Just re-run `./deploy.sh`. Notes:

- **Schema changes**: create the migration locally first
  (`uv run reflex db makemigrations --message "…"`), commit it under `alembic/`,
  then deploy — the backend entrypoint applies pending migrations on boot.
- **Frontend-only change**: `deploy.sh` always re-exports, re-uploads, and
  re-stages the shell, so this is handled automatically — no manual step.
- **New secret**: add it to `.env` and re-run `./deploy.sh` (or
  `fly secrets set --app coverletterer-backend KEY=value`).

---

## Configuration reference

Set in `fly.backend.toml` `[env]` (overridden by `deploy.sh` per `PREFIX` and
`APP_DOMAIN`). The values below are the fly.dev defaults:

| Variable | Value | Why |
|---|---|---|
| `REFLEX_API_URL` | `https://coverletterer-backend.fly.dev` | The SPA's websocket/data origin (**stays fly.dev** even with a custom domain) |
| `REFLEX_DEPLOY_URL` | custom domain or fly.dev | Public app URL |
| `REFLEX_CORS_ALLOWED_ORIGINS` | custom + fly.dev | Allows the SPA's websocket/API calls from either origin |
| `BACKEND_URL` / `FRONTEND_URL` | custom domain or fly.dev | Magic-link browser navigations |

Deploy-time only (read by `deploy.sh`, not the app): `APP_DOMAIN` (defaults
to the fly.dev URL — see **Custom domain**), `FRONTEND_BUCKET_NAME` /
`FRONTEND_AWS_*` (the static-assets bucket — see **Static assets**).

Secrets (never in toml): `ANTHROPIC_API_KEY`,
`SMTP_HOSTNAME`/`SMTP_USERNAME`/`SMTP_PASSWORD` (+ optional `SMTP_PORT`/`SMTP_FROM`/`SMTP_STARTTLS`),
`DATABASE_URL` (a Supabase connection string — **you** set this in `.env`; `deploy.sh` stages it, it does not create it),
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_ENDPOINT_URL_S3`/`BUCKET_NAME`
(the private resume-PDF bucket, via `fly storage create` — Tigris).

---

## Troubleshooting

- **`DATABASE_URL is not set` and `deploy.sh` exits**: expected — see
  **Database (Supabase)** above. Set it in `.env` and re-run.
- **`Frontend static-assets bucket is not configured` and `deploy.sh`
  exits**: expected — see **Static assets (Tigris)** above.
- **Prepared-statement / "cached plan must not change result type" errors**:
  you're likely on the Supabase **Transaction pooler** (port `6543`) instead
  of the **Session pooler** (port `5432`). Switch the connection string.
- **Connection refused / timeouts to Supabase**: free-tier projects
  auto-pause after inactivity — open the Supabase dashboard once to wake it,
  or upgrade to avoid pausing.
- **A page loads blank / a JS console error like "Unexpected token '<'"**:
  the deployed SPA shell and the uploaded assets are out of sync (an asset
  upload failed partway, or the bucket in `fly.backend.toml`'s `[[statics]]`
  doesn't match `FRONTEND_BUCKET_NAME`). Note this **won't** show as a clean
  404 in the Network tab — confirmed locally that a request for a
  `/assets/*` path Fly's proxy can't find in the bucket falls through to the
  app's own catch-all, which returns the SPA shell's **HTML** with a `200`;
  the browser then fails trying to parse that as JS. Re-run `./deploy.sh` —
  it always uploads before deploying, so this should self-heal; if it
  doesn't, check `scripts/upload_static_assets.py`'s output for errors.
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
traffic level, and there's no persistent volume (resume PDFs live in Tigris;
static assets are served independently of the app machine entirely via
`[[statics]]`).

To scale the backend to multiple machines later: provision Redis
(`fly redis create`, set `REDIS_URL`) so Reflex switches to its Redis-backed
state manager, then `fly scale count N --app coverletterer-backend`.
Not needed yet — this is a pointer for later, not part of the current deploy.
