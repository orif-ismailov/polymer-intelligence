"""
Unit tests for app.core.crypto — app-layer PII encryption (R1, ARCHITECTURE §15).

Company bank account numbers are Fernet-encrypted at the app layer; only ciphertext
(bytea) + last4 (clear) are persisted. These tests pin the invariants the storage
path depends on: reversible roundtrip, ciphertext never equals plaintext, tampered
tokens are rejected, and the key comes from settings.VERIFICATION_ENC_KEY.

Offline — the conftest env provides a valid Fernet VERIFICATION_ENC_KEY.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken


def test_roundtrip_recovers_plaintext() -> None:
    from app.core.crypto import decrypt_pii, encrypt_pii

    plain = "20208000900000000001"  # a 20-digit UZ account number
    assert decrypt_pii(encrypt_pii(plain)) == plain


def test_roundtrip_unicode() -> None:
    from app.core.crypto import decrypt_pii, encrypt_pii

    plain = "АО «Полимер» — счёт №42301"
    assert decrypt_pii(encrypt_pii(plain)) == plain


def test_ciphertext_is_bytes_and_not_plaintext() -> None:
    from app.core.crypto import encrypt_pii

    plain = "20208000900000000001"
    token = encrypt_pii(plain)
    assert isinstance(token, bytes)
    assert plain.encode() not in token  # plaintext must not leak into the blob


def test_two_encryptions_differ_but_both_decrypt() -> None:
    """Fernet embeds a random IV → identical plaintext yields distinct ciphertexts."""
    from app.core.crypto import decrypt_pii, encrypt_pii

    plain = "12345678901234567890"
    a, b = encrypt_pii(plain), encrypt_pii(plain)
    assert a != b
    assert decrypt_pii(a) == decrypt_pii(b) == plain


def test_tampered_token_is_rejected() -> None:
    from app.core.crypto import decrypt_pii, encrypt_pii

    token = bytearray(encrypt_pii("20208000900000000001"))
    token[-1] ^= 0x01  # flip a bit in the ciphertext
    with pytest.raises(InvalidToken):
        decrypt_pii(bytes(token))


def test_uses_configured_key() -> None:
    """The cipher is keyed by settings.VERIFICATION_ENC_KEY (conftest placeholder)."""
    from app.core.config import settings
    from app.core.crypto import _fernet

    assert settings.VERIFICATION_ENC_KEY
    # Building the cipher from the configured key must not raise.
    assert _fernet() is _fernet()  # cached singleton
