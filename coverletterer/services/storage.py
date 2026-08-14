"""Object storage for resume PDFs (S3-compatible: MinIO local).

Uploaded/overridden resume PDFs live in a private bucket; the UI serves the
current resume as extracted text, not the file itself, so no presigned URLs
are needed for display — `presigned_url` exists for the rare case of wanting
to re-download the original file.

Pure module — no Reflex imports.
"""

from __future__ import annotations

import os
import tempfile

from .. import config


class StorageConfigError(RuntimeError):
    """Raised when object storage is not configured."""


_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.storage_enabled():
            raise StorageConfigError(
                "Object storage is not configured "
                "(BUCKET_NAME / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)."
            )
        import boto3
        from botocore.config import Config as BotoConfig

        _client = boto3.client(
            "s3",
            endpoint_url=config.s3_endpoint_url(),
            region_name=config.S3_REGION,
            aws_access_key_id=config.s3_access_key(),
            aws_secret_access_key=config.s3_secret_key(),
            # Path-style addressing works with both MinIO and Tigris.
            config=BotoConfig(s3={"addressing_style": "path"}),
        )
    return _client


def _content_type(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    return {".pdf": "application/pdf"}.get(ext, "application/octet-stream")


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    _get_client().put_object(
        Bucket=config.s3_bucket(),
        Key=key,
        Body=data,
        ContentType=content_type or _content_type(key),
    )


def download_bytes(key: str) -> bytes:
    fd, path = tempfile.mkstemp(suffix=os.path.splitext(key)[1], prefix="resume_")
    os.close(fd)
    _get_client().download_file(config.s3_bucket(), key, path)
    try:
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def presigned_url(key: str, ttl: int | None = None) -> str:
    """A short-lived GET URL for downloading the original object."""
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": config.s3_bucket(), "Key": key},
        ExpiresIn=ttl or config.PRESIGN_TTL_SECONDS,
    )


def delete(key: str) -> None:
    try:
        _get_client().delete_object(Bucket=config.s3_bucket(), Key=key)
    except Exception:  # noqa: BLE001 — deletion is best-effort
        pass
