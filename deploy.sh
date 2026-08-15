#!/usr/bin/env bash
#
# Deploy CoverLetterer to Fly.io as 3 tiers: Supabase Postgres (external) +
# backend + frontend. Idempotent: safe to re-run for repeated deployments.
#
# Overridable via env: PREFIX, REGION, ENV_FILE, ORG.
# Prereqs: `fly auth login`, a local .env containing DATABASE_URL (a Supabase
# connection string — see DEPLOY.md) plus ANTHROPIC_API_KEY / optional SMTP_*.
#
set -euo pipefail

PREFIX="${PREFIX:-coverletterer}"
REGION="${REGION:-syd}"
ENV_FILE="${ENV_FILE:-.env}"
ORG_ARG=""
[ -n "${ORG:-}" ] && ORG_ARG="--org ${ORG}"

BACKEND="${PREFIX}-backend"
FRONTEND="${PREFIX}-frontend"

# Fly-assigned URLs (always available, always have a valid cert).
FLY_BACKEND_URL="https://${BACKEND}.fly.dev"
FLY_FRONTEND_URL="https://${FRONTEND}.fly.dev"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- 0. Preflight ---------------------------------------------------------
FLY="$(command -v fly || command -v flyctl || true)"
[ -n "$FLY" ] || { echo "flyctl not found — install from https://fly.io/docs/flyctl/install/"; exit 1; }
"$FLY" auth whoami >/dev/null 2>&1 || { echo "Not logged in — run 'fly auth login'"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (needs DATABASE_URL, ANTHROPIC_API_KEY, optionally SMTP_*)"; exit 1; }

# Load .env early so FRONTEND_DOMAIN/BACKEND_DOMAIN (and secrets) are in scope.
# Preserve any command-line overrides of the domain knobs (shell env wins over
# .env), then source .env for everything else.
_cli_frontend_domain="${FRONTEND_DOMAIN:-}"
_cli_backend_domain="${BACKEND_DOMAIN:-}"
set -a; . "./$ENV_FILE"; set +a
[ -n "$_cli_frontend_domain" ] && FRONTEND_DOMAIN="$_cli_frontend_domain"
[ -n "$_cli_backend_domain" ] && BACKEND_DOMAIN="$_cli_backend_domain"

# --- Resolve public URLs --------------------------------------------------
# Custom domains are configured via FRONTEND_DOMAIN / BACKEND_DOMAIN (bare host
# or full URL). They CNAME to the fly.dev URLs and default to them when unset.
_norm() { local v="${1#http://}"; v="${v#https://}"; printf 'https://%s' "${v%%/}"; }
_host() { local v="${1#https://}"; v="${v#http://}"; printf '%s' "${v%%/*}"; }

PUBLIC_BACKEND_URL="$([ -n "${BACKEND_DOMAIN:-}" ] && _norm "$BACKEND_DOMAIN" || echo "$FLY_BACKEND_URL")"
PUBLIC_FRONTEND_URL="$([ -n "${FRONTEND_DOMAIN:-}" ] && _norm "$FRONTEND_DOMAIN" || echo "$FLY_FRONTEND_URL")"

# The browser SPA's data origin stays on fly.dev (always certed); the custom
# backend domain is used only for branded magic-link browser navigations.
SPA_API_URL="$FLY_BACKEND_URL"

# CORS: allow the custom frontend origin AND the fly.dev frontend origin (so the
# app works loaded from either). Dedup when no custom domain is set.
if [ "$PUBLIC_FRONTEND_URL" = "$FLY_FRONTEND_URL" ]; then
  CORS_ORIGINS="$FLY_FRONTEND_URL"
else
  CORS_ORIGINS="$PUBLIC_FRONTEND_URL,$FLY_FRONTEND_URL"
fi

# Dry-run: print the resolved wiring and exit (no Fly calls).
if [ -n "${PRINT_ONLY:-}" ]; then
  echo "PREFIX=$PREFIX  REGION=$REGION"
  echo "FLY_FRONTEND_URL=$FLY_FRONTEND_URL"
  echo "FLY_BACKEND_URL=$FLY_BACKEND_URL"
  echo "PUBLIC_FRONTEND_URL=$PUBLIC_FRONTEND_URL"
  echo "PUBLIC_BACKEND_URL=$PUBLIC_BACKEND_URL"
  echo "SPA REFLEX_API_URL=$SPA_API_URL"
  echo "REFLEX_DEPLOY_URL=$PUBLIC_FRONTEND_URL"
  echo "REFLEX_CORS_ALLOWED_ORIGINS=$CORS_ORIGINS"
  echo "DATABASE_URL set locally: $([ -n "${DATABASE_URL:-}" ] && echo yes || echo no)"
  [ "$PUBLIC_FRONTEND_URL" != "$FLY_FRONTEND_URL" ] && echo "cert (frontend): $(_host "$PUBLIC_FRONTEND_URL")"
  [ "$PUBLIC_BACKEND_URL"  != "$FLY_BACKEND_URL"  ] && echo "cert (backend):  $(_host "$PUBLIC_BACKEND_URL")"
  exit 0
fi

# --- 1. Apps (create if missing) -----------------------------------------
app_exists() { "$FLY" apps list 2>/dev/null | awk '{print $1}' | grep -qx "$1"; }
for app in "$BACKEND" "$FRONTEND"; do
  if app_exists "$app"; then log "App $app already exists"; else
    log "Creating app $app"; "$FLY" apps create "$app" $ORG_ARG
  fi
done

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

# --- 3. Object storage (Tigris) -------------------------------------------
# Resume PDFs live in object storage, so backend machines are stateless (no
# single-attach volume). NOTE: comes from Fly provisioning, NOT from .env
# (your .env holds the LOCAL MinIO values, which must not reach production).
if "$FLY" secrets list --app "$BACKEND" 2>/dev/null | grep -q "BUCKET_NAME"; then
  log "Object storage already configured on $BACKEND"
else
  log "Provisioning Tigris object storage for $BACKEND (sets AWS_*/BUCKET_NAME secrets)"
  "$FLY" storage create --app "$BACKEND" --name "${PREFIX}-media" --yes 2>/dev/null || \
    echo "   (provision Tigris manually: 'fly storage create --app $BACKEND'; see DEPLOY.md)"
fi

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

# --- 5. TLS certs for custom domains (skip when using fly.dev) ------------
# DNS (CNAME) is already set, so Fly auto-validates. Idempotent.
if [ "$PUBLIC_FRONTEND_URL" != "$FLY_FRONTEND_URL" ]; then
  log "Adding TLS cert for $(_host "$PUBLIC_FRONTEND_URL") on $FRONTEND"
  "$FLY" certs add "$(_host "$PUBLIC_FRONTEND_URL")" --app "$FRONTEND" || \
    echo "   (cert add reported an issue — it may already exist; continuing)"
fi
if [ "$PUBLIC_BACKEND_URL" != "$FLY_BACKEND_URL" ]; then
  log "Adding TLS cert for $(_host "$PUBLIC_BACKEND_URL") on $BACKEND"
  "$FLY" certs add "$(_host "$PUBLIC_BACKEND_URL")" --app "$BACKEND" || \
    echo "   (cert add reported an issue — it may already exist; continuing)"
fi

# --- 6. Deploy backend ----------------------------------------------------
# --env overrides keep URLs/CORS correct for custom domains (and any PREFIX).
# REFLEX_API_URL (the SPA's data origin) stays on the fly.dev backend; the
# custom backend domain is used for magic-link browser navigations.
log "Deploying backend ($BACKEND)"
"$FLY" deploy --app "$BACKEND" -c fly.backend.toml \
  --env "REFLEX_API_URL=$SPA_API_URL" \
  --env "REFLEX_DEPLOY_URL=$PUBLIC_FRONTEND_URL" \
  --env "REFLEX_CORS_ALLOWED_ORIGINS=$CORS_ORIGINS" \
  --env "BACKEND_URL=$PUBLIC_BACKEND_URL" \
  --env "FRONTEND_URL=$PUBLIC_FRONTEND_URL"

# --- 7. Deploy frontend (bake the SPA's backend URL into the static build) -
log "Deploying frontend ($FRONTEND) → REFLEX_API_URL=$SPA_API_URL"
"$FLY" deploy --app "$FRONTEND" -c fly.frontend.toml \
  --build-arg "REFLEX_API_URL=$SPA_API_URL" \
  --build-arg "REFLEX_DEPLOY_URL=$PUBLIC_FRONTEND_URL"

# --- Done -----------------------------------------------------------------
log "Deployment complete"
echo "  Frontend: $PUBLIC_FRONTEND_URL"
echo "  Backend:  $PUBLIC_BACKEND_URL"
if [ "$PUBLIC_FRONTEND_URL" != "$FLY_FRONTEND_URL" ] || [ "$PUBLIC_BACKEND_URL" != "$FLY_BACKEND_URL" ]; then
  echo "  Custom domains: watch cert issuance with 'fly certs show <domain> --app <app>'."
fi
echo "  Seed a QA user: fly ssh console --app $BACKEND -C 'uv run --no-sync python scripts/create_qa_user.py'"
