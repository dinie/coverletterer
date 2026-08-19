"""Upload the exported frontend's hashed JS/CSS bundle to the Tigris bucket
`[[statics]]` serves `/assets/*` from (see `fly.backend.toml`).

Fly's docs don't describe any `fly deploy`-time sync for a `[[statics]]`
`tigris_bucket`, so `deploy.sh` runs this itself, right after `reflex export
--frontend-only` and before `fly deploy` — see DEPLOY.md "Static assets
(Tigris)". Uses the same boto3 S3-compatible-client pattern as
`coverletterer/services/storage.py`, but pointed at the *frontend* bucket's
own credentials (FRONTEND_* env vars), deliberately separate from the app's
runtime AWS_*/BUCKET_NAME (which stay pointed at the private resume-PDF
bucket).

Skips the `.gz` precompressed variants Reflex also produces alongside each
file — `[[statics]]` doesn't document any Accept-Encoding negotiation, so
serving those under their literal `.js.gz` keys would just be dead weight.

Usage:
    uv run python scripts/upload_static_assets.py [assets_dir] [key_prefix]

Reads FRONTEND_BUCKET_NAME, FRONTEND_AWS_ACCESS_KEY_ID,
FRONTEND_AWS_SECRET_ACCESS_KEY, FRONTEND_AWS_ENDPOINT_URL_S3 (+ optional
FRONTEND_AWS_REGION, default "auto") from the environment.
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path

DEFAULT_ASSETS_DIR = ".web/build/client/assets"
DEFAULT_KEY_PREFIX = "assets"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    # mimetypes doesn't always know modern JS/CSS extensions on every OS.
    return {".js": "application/javascript", ".css": "text/css"}.get(
        path.suffix, "application/octet-stream"
    )


def main() -> None:
    assets_dir = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ASSETS_DIR)
    key_prefix = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_KEY_PREFIX

    if not assets_dir.is_dir():
        print(f"Assets directory not found: {assets_dir}", file=sys.stderr)
        print("Run `uv run reflex export --frontend-only --no-zip` first.", file=sys.stderr)
        sys.exit(1)

    bucket = _require_env("FRONTEND_BUCKET_NAME")
    access_key = _require_env("FRONTEND_AWS_ACCESS_KEY_ID")
    secret_key = _require_env("FRONTEND_AWS_SECRET_ACCESS_KEY")
    endpoint_url = _require_env("FRONTEND_AWS_ENDPOINT_URL_S3")
    region = os.environ.get("FRONTEND_AWS_REGION", "auto")

    import boto3
    from botocore.config import Config as BotoConfig

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(s3={"addressing_style": "path"}),
    )

    files = sorted(p for p in assets_dir.rglob("*") if p.is_file() and p.suffix != ".gz")
    if not files:
        print(f"No files found under {assets_dir} (excluding .gz)", file=sys.stderr)
        sys.exit(1)

    for path in files:
        key = f"{key_prefix}/{path.relative_to(assets_dir).as_posix()}"
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=path.read_bytes(),
            ContentType=_content_type(path),
        )
        print(f"  uploaded {key} ({path.stat().st_size} bytes)")

    print(f"Done — {len(files)} file(s) uploaded to bucket '{bucket}'.")


if __name__ == "__main__":
    main()
