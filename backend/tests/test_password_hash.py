"""
Tests for argon2 password hashing helpers in app.core.security.

Covers:
- hash_password produces an argon2 hash (starts with $argon2)
- verify_password returns True for correct password, False for wrong one
- Same plaintext hashed twice yields different hashes (salted) but both verify
- Plaintext never appears in the hash string
"""

from __future__ import annotations


def test_hash_password_returns_argon2_format():
    """hash_password output starts with $argon2 identifier."""
    from app.core.security import hash_password

    result = hash_password("secret123")
    assert result.startswith("$argon2"), f"Expected argon2 hash, got: {result[:20]}"


def test_hash_password_does_not_contain_plaintext():
    """The plaintext password must not appear in the hash output."""
    from app.core.security import hash_password

    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert plain not in hashed, "Plaintext password leaked into the hash!"


def test_verify_password_correct_password_returns_true():
    """verify_password returns True for the correct password."""
    from app.core.security import hash_password, verify_password

    plain = "correct_password"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong_password_returns_false():
    """verify_password returns False for an incorrect password."""
    from app.core.security import hash_password, verify_password

    hashed = hash_password("correct_password")
    assert verify_password("wrong_password", hashed) is False


def test_hash_password_is_salted_unique():
    """Same plaintext hashed twice yields different hashes (salted)."""
    from app.core.security import hash_password

    plain = "same_password"
    hash1 = hash_password(plain)
    hash2 = hash_password(plain)
    assert hash1 != hash2, "Hashes should be unique due to salting"


def test_both_salted_hashes_verify():
    """Both salted hashes of the same plaintext verify correctly."""
    from app.core.security import hash_password, verify_password

    plain = "same_password"
    hash1 = hash_password(plain)
    hash2 = hash_password(plain)
    assert verify_password(plain, hash1) is True
    assert verify_password(plain, hash2) is True


def test_verify_password_empty_plain_returns_false():
    """An empty-string password does not verify against a real hash."""
    from app.core.security import hash_password, verify_password

    hashed = hash_password("not_empty")
    assert verify_password("", hashed) is False
