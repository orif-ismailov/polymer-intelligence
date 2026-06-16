"""
MinIO/S3 client — Phase 3 first real use of S3_* config.

Constructs a boto3 S3 client lazily (via get_s3_client()) so importing this
module does NOT open a network socket at collection time (mirrors the config
import-safety pattern: Settings() is called at module level but S3 connection
is deferred until first use).

Usage:
    from app.core.storage import s3_client, ensure_bucket
    s3_client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data)
    ensure_bucket()   # idempotent: creates the bucket if it does not exist
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    import boto3 as boto3_type  # noqa: F401

logger = logging.getLogger(__name__)


def get_s3_client() -> object:
    """Build and return a boto3 S3 client from S3_* settings.

    endpoint_url is set to settings.S3_ENDPOINT when non-empty (dev/MinIO);
    when empty (pure AWS), it falls back to None (boto3 default).

    region_name is fixed to "us-east-1" which is the MinIO default and
    sufficient for path-style MinIO access.

    Returns:
        A boto3.client("s3") instance.
    """
    import boto3  # noqa: PLC0415 — deferred import keeps collection socket-free

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name="us-east-1",
    )


# Module-level lazy s3_client accessor.
#
# Initialized to None at import time so that importing this module does NOT
# open a network socket at pytest collection time (mirrors config import-safety).
# _get_or_create_s3_client() builds the client on first real use.
#
# For production code, use the `s3_client` name directly — the module swaps
# in the real client the first time it is called.  Storage service functions
# call `from app.core.storage import s3_client` at use-time (deferred import),
# which also means tests can patch `app.core.storage.s3_client` after import.

_s3_client_instance: object = None


def _get_or_create_s3_client() -> object:
    """Return the cached S3 client, building it on first call."""
    global _s3_client_instance
    if _s3_client_instance is None:
        _s3_client_instance = get_s3_client()
    return _s3_client_instance


class _LazyS3Client:
    """Thin proxy that builds the real boto3 client on first attribute access.

    This makes `from app.core.storage import s3_client` safe at import time
    even when boto3 is not installed (e.g. during pytest collection).  The
    real boto3 client is built on the first call to any method.
    """

    def __getattr__(self, name: str) -> object:
        real = _get_or_create_s3_client()
        return getattr(real, name)


s3_client: object = _LazyS3Client()


def ensure_bucket() -> None:
    """Create settings.S3_BUCKET if it does not already exist.

    Idempotent: if the bucket already exists (HeadBucket succeeds), this is a
    no-op. On a fresh MinIO instance (e.g. first `docker compose up`), this
    creates the bucket automatically so the backend can start uploading files
    without any manual provisioning step.

    Called during application startup (or lazily before the first upload in tests).
    Does NOT raise on bucket-already-exists; logs a debug message instead.
    """
    import botocore.exceptions  # noqa: PLC0415

    bucket_name = settings.S3_BUCKET
    try:
        s3_client.head_bucket(Bucket=bucket_name)  # type: ignore[attr-defined]
        logger.debug("storage.ensure_bucket.exists", extra={"bucket": bucket_name})
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response["Error"]["Code"]  # type: ignore[index]
        if error_code in ("404", "NoSuchBucket"):
            s3_client.create_bucket(Bucket=bucket_name)  # type: ignore[attr-defined]
            logger.info("storage.ensure_bucket.created", extra={"bucket": bucket_name})
        else:
            # Re-raise unexpected errors (auth failure, etc.)
            raise
