"""
App-layer PII encryption (R1 — ARCHITECTURE §15).

Company bank account numbers (R1) and PINFL (R3) are encrypted at the application
layer with Fernet (AES-128-CBC + HMAC) keyed by `settings.VERIFICATION_ENC_KEY`.
Only the ciphertext (`bytea`) and the last 4 digits (clear, for masking) are
persisted — the full number never appears in a response or a log line.

The Fernet instance is built lazily on first use so importing this module never
fails on a malformed key at collection time (Settings already validates length).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Build (and cache) the Fernet cipher from the configured key."""
    key = settings.VERIFICATION_ENC_KEY
    # Fernet expects urlsafe-base64 bytes; accept either str or bytes in the env.
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_pii(plain: str) -> bytes:
    """Encrypt a PII string, returning ciphertext bytes for a BYTEA column."""
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt_pii(token: bytes) -> str:
    """Decrypt ciphertext bytes produced by encrypt_pii back to the plaintext."""
    return _fernet().decrypt(token).decode("utf-8")
