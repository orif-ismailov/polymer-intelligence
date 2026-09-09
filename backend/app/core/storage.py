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


def _build_client(endpoint: str, *, sigv4: bool = False) -> object:
    """Build a boto3 S3 client against `endpoint` (empty → boto3's AWS default).

    region_name is fixed to "us-east-1" which is the MinIO default and
    sufficient for path-style MinIO access.

    `sigv4` pins the SIGNATURE VERSION, and only the presigning client asks for it.
    Left to itself botocore emits SigV2 presigned URLs here (`AWSAccessKeyId` +
    `Signature` + `Expires`, HMAC-SHA1) even though `meta.config.signature_version`
    reads `s3v4` — verified against the MinIO this repo runs. V2 does not sign the
    Host header, so the URL is valid against ANY host that can reach the bucket;
    v4 does, so it is valid only against the host it was signed for. That is the
    property worth having on a link we hand to a browser over the public internet,
    and it is what makes `proxy_set_header Host $host` in the nginx bucket location
    load-bearing rather than incidental (without it MinIO answers 403
    SignatureDoesNotMatch — also verified, both directions).
    """
    import boto3  # noqa: PLC0415 — deferred import keeps collection socket-free
    from botocore.config import Config  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name="us-east-1",
        config=Config(signature_version="s3v4") if sigv4 else None,
    )


def get_s3_client() -> object:
    """The I/O client: put/get/head, over the INTERNAL endpoint.

    endpoint_url is set to settings.S3_ENDPOINT when non-empty (dev/MinIO);
    when empty (pure AWS), it falls back to None (boto3 default).

    Returns:
        A boto3.client("s3") instance.
    """
    return _build_client(settings.S3_ENDPOINT)


def get_s3_presign_client() -> object:
    """The signing client: presigned URLs a BROWSER has to be able to open.

    A second client rather than a second endpoint on the first one, because a
    presigned URL cannot be rewritten after the fact. SigV4 lists `host` in
    `X-Amz-SignedHeaders`, so the host is part of what the signature covers —
    swapping `minio:9000` for a public name in the returned string produces a URL
    the object store answers 403 to. The endpoint has to be right at signing time,
    which means a client built with it.

    `S3_PUBLIC_ENDPOINT` empty → falls back to `S3_ENDPOINT`, i.e. exactly the old
    behaviour. That is deliberate: the fallback keeps every deployment that has not
    set the new variable working precisely as before, at the cost of continuing to
    emit URLs only reachable inside the docker network (which is the bug this
    exists to fix — see the note on `S3_PUBLIC_ENDPOINT` in `core/config.py`).
    """
    return _build_client(settings.S3_PUBLIC_ENDPOINT or settings.S3_ENDPOINT, sigv4=True)


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
_s3_presign_client_instance: object = None


def _get_or_create_s3_client() -> object:
    """Return the cached S3 client, building it on first call."""
    global _s3_client_instance
    if _s3_client_instance is None:
        _s3_client_instance = get_s3_client()
    return _s3_client_instance


def _get_or_create_s3_presign_client() -> object:
    """Return the cached presigning client, building it on first call."""
    global _s3_presign_client_instance
    if _s3_presign_client_instance is None:
        _s3_presign_client_instance = get_s3_presign_client()
    return _s3_presign_client_instance


class _LazyS3Client:
    """Thin proxy that builds the real boto3 client on first attribute access.

    This makes `from app.core.storage import s3_client` safe at import time
    even when boto3 is not installed (e.g. during pytest collection).  The
    real boto3 client is built on the first call to any method.
    """

    def __getattr__(self, name: str) -> object:
        real = _get_or_create_s3_client()
        return getattr(real, name)


class _LazyS3PresignClient:
    """The same proxy for the presigning client. Patch this one in tests that
    exercise a `presign_*` helper — `s3_client` no longer signs anything."""

    def __getattr__(self, name: str) -> object:
        real = _get_or_create_s3_presign_client()
        return getattr(real, name)


s3_client: object = _LazyS3Client()
s3_presign_client: object = _LazyS3PresignClient()


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
        error_code = exc.response["Error"]["Code"]
        if error_code in ("404", "NoSuchBucket"):
            s3_client.create_bucket(Bucket=bucket_name)  # type: ignore[attr-defined]
            logger.info("storage.ensure_bucket.created", extra={"bucket": bucket_name})
        else:
            # Re-raise unexpected errors (auth failure, etc.)
            raise
