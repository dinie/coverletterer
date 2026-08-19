#!/usr/bin/env bash
#
# Deploy CoverLetterer to Fly.io as a single app: the Reflex backend also
# serves the SPA shell (frontend_routes.py); the hashed JS/CSS bundle is
# served straight from Tigris via [[statics]] in fly.backend.toml, bypassing
# the app entirely for those requests. Database is Supabase Postgres
# (external). Idempotent: safe to re-run for repeated deployments.
#
# Overridable via env: PREFIX, REGION, ENV_FILE, ORG.
# Prereqs: `fly auth login`, a local .env containing DATABASE_URL (a Supabase
# connection string — see DEPLOY.md) plus ANTHROPIC_API_KEY / optional
# SMTP_* / the FRONTEND_* static-bucket vars (see DEPLOY.md "Static assets").
#
set -euo pipefail

PREFIX="${PREFIX:-coverletterer}"
REGION="${REGION:-syd}"
ENV_FILE="${ENV_FILE:-.env}"
ORG_ARG=""
[ -n "${ORG:-}" ] && ORG_ARG="--org ${ORG}"

BACKEND="${PREFIX}-backend"

# Fly-assigned URL (always available, always has a valid cert).
FLY_APP_URL="https://${BACKEND}.fly.dev"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- 0. Preflight ---------------------------------------------------------
FLY="$(command -v fly || command -v flyctl || true)"
[ -n "$FLY" ] || { echo "flyctl not found — install from https://fly.io/docs/flyctl/install/"; exit 1; }
"$FLY" auth whoami >/dev/null 2>&1 || { echo "Not logged in — run 'fly auth login'"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (needs DATABASE_URL, ANTHROPIC_API_KEY, optionally SMTP_*)"; exit 1; }

# Load .env early so APP_DOMAIN (and secrets) are in scope. Preserve any
# command-line override of the domain knob (shell env wins over .env), then
# source .env for everything else.
_cli_app_domain="${APP_DOMAIN:-}"
set -a; . "./$ENV_FILE"; set +a
[ -n "$_cli_app_domain" ] && APP_DOMAIN="$_cli_app_domain"

# --- Resolve the public URL ------------------------------------------------
# A custom domain is configured via APP_DOMAIN (bare host or full URL). It
# CNAMEs to the fly.dev URL and defaults to it when unset.
_norm() { local v="${1#http://}"; v="${v#https://}"; printf 'https://%s' "${v%%/}"; }
_host() { local v="${1#https://}"; v="${v#http://}"; printf '%s' "${v%%/*}"; }

PUBLIC_URL="$([ -n "${APP_DOMAIN:-}" ] && _norm "$APP_DOMAIN" || echo "$FLY_APP_URL")"

# The SPA's data origin (websocket/API) always stays on the fly.dev URL —
# always has a valid cert, no race with a not-yet-issued custom-domain cert.
SPA_API_URL="$FLY_APP_URL"

# CORS: allow the custom domain AND the fly.dev URL (so the app works loaded
# from either). Dedup when no custom domain is set.
if [ "$PUBLIC_URL" = "$FLY_APP_URL" ]; then
  CORS_ORIGINS="$FLY_APP_URL"
else
  CORS_ORIGINS="$PUBLIC_URL,$FLY_APP_URL"
fi

# Dry-run: print the resolved wiring and exit (no Fly calls).
if [ -n "${PRINT_ONLY:-}" ]; then
  echo "PREFIX=$PREFIX  REGION=$REGION"
  echo "FLY_APP_URL=$FLY_APP_URL"
  echo "PUBLIC_URL=$PUBLIC_URL"
  echo "SPA REFLEX_API_URL=$SPA_API_URL"
  echo "REFLEX_DEPLOY_URL=$PUBLIC_URL"
  echo "REFLEX_CORS_ALLOWED_ORIGINS=$CORS_ORIGINS"
  echo "DATABASE_URL set locally: $([ -n "${DATABASE_URL:-}" ] && echo yes || echo no)"
  echo "Frontend bucket configured locally: $([ -n "${FRONTEND_BUCKET_NAME:-}" ] && echo yes || echo no)"
  [ "$PUBLIC_URL" != "$FLY_APP_URL" ] && echo "cert: $(_host "$PUBLIC_URL")"
  exit 0
fi

# --- 1. App (create if missing) -------------------------------------------
app_exists() { "$FLY" apps list 2>/dev/null | awk '{print $1}' | grep -qx "$1"; }
if app_exists "$BACKEND"; then log "App $BACKEND already exists"; else
  log "Creating app $BACKEND"; "$FLY" apps create "$BACKEND" $ORG_ARG
fi

# --- 2. Database (Supabase) — required, never auto-provisioned -----------
# Unlike a Fly-hosted Postgres app, Supabase is external: you create the
# project and grab its connection string yourself (see DEPLOY.md — use the
# "Session pooler" string, port 5432). This step only validates DATABASE_URL
# is available and stages it as a Fly secret; it never creates a database.
if "$FLY" secrets list --app "$BACKEND" 2>/dev/null | grep -q "DATABASE_URL"; then
  log "DATABASE_URL already set on $BACKEND"
elif [ -n "${DATABASE_URL:-}" ]; then
  log "Staging DATABASE_URL from $ENV_FILE"
  "$FLY" secrets set --app "$BACKEND" --stage "DATABASE_URL=$DATABASE_URL"
else
  echo "DATABASE_URL is not set (checked $ENV_FILE and existing Fly secrets on $BACKEND)."
  echo "  Get it from Supabase: Project Settings -> Database -> Connection string"
  echo "  -> use the 'Session pooler' string (port 5432) — see DEPLOY.md."
  echo "  Then set DATABASE_URL=postgresql://... in $ENV_FILE and re-run ./deploy.sh."
  exit 1
fi

# --- 3a. Object storage (Tigris) — private resume-PDF bucket --------------
# Resume PDFs live in object storage, so backend machines are stateless (no
# single-attach volume). NOTE: comes from Fly provisioning, NOT from .env
# (your .env holds the LOCAL MinIO values, which must not reach production).
if "$FLY" secrets list --app "$BACKEND" 2>/dev/null | grep -q "BUCKET_NAME"; then
  log "Resume-PDF object storage already configured on $BACKEND"
else
  log "Provisioning Tigris object storage for resume PDFs (sets AWS_*/BUCKET_NAME secrets)"
  "$FLY" storage create --app "$BACKEND" --name "${PREFIX}-media" --yes 2>/dev/null || \
    echo "   (provision manually: 'fly storage create --app $BACKEND'; see DEPLOY.md)"
fi

# --- 3b. Object storage (Tigris) — public frontend-assets bucket ----------
# Deliberately NOT auto-provisioned like 3a: running `fly storage create` a
# second time on the same app risks clobbering 3a's AWS_*/BUCKET_NAME
# secrets (unconfirmed exact behavior across flyctl versions), and this
# bucket's credentials don't need to be app secrets at all — only this
# script (not the running app) ever uploads to it. So, like DATABASE_URL,
# this is a "you provision it once, deploy.sh validates + uses it" step.
if [ -z "${FRONTEND_BUCKET_NAME:-}" ] || [ -z "${FRONTEND_AWS_ACCESS_KEY_ID:-}" ] || \
   [ -z "${FRONTEND_AWS_SECRET_ACCESS_KEY:-}" ] || [ -z "${FRONTEND_AWS_ENDPOINT_URL_S3:-}" ]; then
  echo "Frontend static-assets bucket is not configured."
  echo "  Create it once: fly storage create --app $BACKEND --name ${PREFIX}-frontend"
  echo "  Then copy the printed credentials into $ENV_FILE as FRONTEND_BUCKET_NAME,"
  echo "  FRONTEND_AWS_ACCESS_KEY_ID, FRONTEND_AWS_SECRET_ACCESS_KEY, and"
  echo "  FRONTEND_AWS_ENDPOINT_URL_S3 — see DEPLOY.md 'Static assets (Tigris)'."
  exit 1
fi
log "Frontend static-assets bucket: $FRONTEND_BUCKET_NAME"

# --- 4. Backend secrets from .env (already sourced above) -----------------
log "Staging backend secrets from $ENV_FILE"
SECRETS=()
for key in ANTHROPIC_API_KEY \
           SMTP_HOSTNAME SMTP_USERNAME SMTP_PASSWORD SMTP_PORT SMTP_FROM SMTP_STARTTLS; do
  val="${!key:-}"
  [ -n "$val" ] && SECRETS+=("$key=$val")
done
if [ "${#SECRETS[@]}" -gt 0 ]; then
  "$FLY" secrets set --app "$BACKEND" --stage "${SECRETS[@]}"
else
  echo "   (no recognized secrets found in $ENV_FILE)"
fi

# --- 5. Export the frontend, upload assets to Tigris, stage the SPA shell -
# One local export feeds both the upload and the staged shell, so they can
# never disagree about asset hashes — see DEPLOY.md "Static assets (Tigris)".
log "Exporting the frontend (reflex export --frontend-only)"
uv run reflex export --frontend-only --no-zip

log "Uploading hashed assets to Tigris bucket $FRONTEND_BUCKET_NAME"
FRONTEND_BUCKET_NAME="$FRONTEND_BUCKET_NAME" \
FRONTEND_AWS_ACCESS_KEY_ID="$FRONTEND_AWS_ACCESS_KEY_ID" \
FRONTEND_AWS_SECRET_ACCESS_KEY="$FRONTEND_AWS_SECRET_ACCESS_KEY" \
FRONTEND_AWS_ENDPOINT_URL_S3="$FRONTEND_AWS_ENDPOINT_URL_S3" \
FRONTEND_AWS_REGION="${FRONTEND_AWS_REGION:-auto}" \
uv run python scripts/upload_static_assets.py

log "Staging the SPA shell for the backend image"
mkdir -p static_shell
cp .web/build/client/__spa-fallback.html static_shell/index.html

# --- 6. TLS cert for a custom domain (skip when using fly.dev) ------------
# DNS (CNAME) is already set, so Fly auto-validates. Idempotent.
if [ "$PUBLIC_URL" != "$FLY_APP_URL" ]; then
  log "Adding TLS cert for $(_host "$PUBLIC_URL") on $BACKEND"
  "$FLY" certs add "$(_host "$PUBLIC_URL")" --app "$BACKEND" || \
    echo "   (cert add reported an issue — it may already exist; continuing)"
fi

# --- 7. Deploy ---------------------------------------------------------
# --env overrides keep URLs/CORS correct for a custom domain (and any
# PREFIX). REFLEX_API_URL (the SPA's data origin) stays on the fly.dev app;
# a custom domain is used for magic-link browser navigations only.
log "Deploying $BACKEND"
"$FLY" deploy --app "$BACKEND" -c fly.backend.toml \
  --env "REFLEX_API_URL=$SPA_API_URL" \
  --env "REFLEX_DEPLOY_URL=$PUBLIC_URL" \
  --env "REFLEX_CORS_ALLOWED_ORIGINS=$CORS_ORIGINS" \
  --env "BACKEND_URL=$PUBLIC_URL" \
  --env "FRONTEND_URL=$PUBLIC_URL"

# --- Done -----------------------------------------------------------------
log "Deployment complete"
echo "  App: $PUBLIC_URL"
if [ "$PUBLIC_URL" != "$FLY_APP_URL" ]; then
  echo "  Custom domain: watch cert issuance with 'fly certs show <domain> --app $BACKEND'."
fi
echo "  Seed a QA user: fly ssh console --app $BACKEND -C 'uv run --no-sync python scripts/create_qa_user.py'"
