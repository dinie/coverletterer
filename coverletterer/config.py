"""Runtime settings sourced from the environment.

Keys are read lazily so the app can boot (and show friendly errors) even when
some are missing. See `.env.example` for the full list.
"""

from __future__ import annotations

import os

# --- LLM ---
ANTHROPIC_MODEL = "claude-opus-4-8"


def anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


# --- Frontend/backend URLs (used to build the magic-link verify URL) ---
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


# --- Passwordless email sign-in (SMTP) ---
def smtp_hostname() -> str | None:
    return os.environ.get("SMTP_HOSTNAME") or None


def smtp_username() -> str | None:
    return os.environ.get("SMTP_USERNAME") or None


def smtp_password() -> str | None:
    return os.environ.get("SMTP_PASSWORD") or None


def smtp_from() -> str:
    return os.environ.get("SMTP_FROM") or (smtp_username() or "")


def smtp_enabled() -> bool:
    return bool(smtp_hostname() and smtp_username() and smtp_password())


SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() != "false"
# How long an emailed magic link stays valid.
MAGIC_LINK_TTL_MINUTES = int(os.environ.get("MAGIC_LINK_TTL_MINUTES", "15"))


# --- Object storage (S3-compatible: MinIO local) ---
def s3_bucket() -> str | None:
    return os.environ.get("BUCKET_NAME") or os.environ.get("S3_BUCKET") or None


def s3_endpoint_url() -> str | None:
    return (
        os.environ.get("AWS_ENDPOINT_URL_S3")
        or os.environ.get("S3_ENDPOINT_URL")
        or None
    )


def s3_access_key() -> str | None:
    return os.environ.get("AWS_ACCESS_KEY_ID") or None


def s3_secret_key() -> str | None:
    return os.environ.get("AWS_SECRET_ACCESS_KEY") or None


S3_REGION = os.environ.get("AWS_REGION") or os.environ.get("S3_REGION") or "auto"
# How long presigned resume-file URLs stay valid.
PRESIGN_TTL_SECONDS = int(os.environ.get("PRESIGN_TTL_SECONDS", "3600"))


def storage_enabled() -> bool:
    return bool(s3_bucket() and s3_access_key() and s3_secret_key())


# --- Uploads ---
RESUME_PDF_EXTENSIONS = [".pdf"]

# --- Headless browser fetch (Playwright fallback for blocked sources) ---
BROWSER_FETCH_TIMEOUT_MS = int(os.environ.get("BROWSER_FETCH_TIMEOUT_MS", "20000"))
