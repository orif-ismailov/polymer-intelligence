"""
Tests for upload validation in storage_service.py.

Covers:
- validate_upload returns "application/pdf" for %PDF magic bytes
- validate_upload returns xlsx MIME for PK\x03\x04 magic bytes
- validate_upload returns "image/jpeg" for \xff\xd8\xff magic bytes
- validate_upload raises ValueError("invalid_file_type") for unknown magic bytes
  regardless of extension (extension-spoofing attack)
- validate_upload raises ValueError("file_too_large") for content > 10 MB
- Size check happens before magic-byte check (size checked first)

T-03-04: magic-byte MIME validation (not extension)
T-03-05: 10 MB per-file limit; MAX_FILES=5 contract
T-03-06: upload_request_file builds traversal-safe S3 key (no raw user path)
"""

from __future__ import annotations

import pytest

# ── Magic bytes ────────────────────────────────────────────────────────────────

PDF_MAGIC = b"%PDF-1.7 rest of file..."
XLSX_MAGIC = b"PK\x03\x04 rest of xlsx file..."
JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 100

# A .txt or .exe header — definitely not in the allowlist
UNKNOWN_MAGIC = b"\x7fELF\x02\x01\x01" + b"\x00" * 100  # ELF binary


def test_validate_upload_pdf_magic_returns_pdf_mime() -> None:
    """Content starting with %PDF is recognized as application/pdf."""
    from app.services.storage_service import validate_upload

    mime = validate_upload(PDF_MAGIC, "document.pdf")
    assert mime == "application/pdf"


def test_validate_upload_xlsx_magic_returns_xlsx_mime() -> None:
    """Content starting with PK\\x03\\x04 is recognized as xlsx MIME."""
    from app.services.storage_service import validate_upload

    mime = validate_upload(XLSX_MAGIC, "prices.xlsx")
    assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_validate_upload_jpeg_magic_returns_image_jpeg() -> None:
    """Content starting with \\xff\\xd8\\xff is recognized as image/jpeg."""
    from app.services.storage_service import validate_upload

    mime = validate_upload(JPEG_MAGIC, "photo.jpg")
    assert mime == "image/jpeg"


def test_validate_upload_unknown_magic_raises_invalid_file_type() -> None:
    """Content with unknown magic bytes raises ValueError('invalid_file_type').

    Extension is ignored — a .pdf extension with ELF header is still rejected.
    This is the core T-03-04 mitigation: magic bytes decide, not extension.
    """
    from app.services.storage_service import validate_upload

    with pytest.raises(ValueError, match="invalid_file_type"):
        validate_upload(UNKNOWN_MAGIC, "malware_as_pdf.pdf")


def test_validate_upload_renamed_ext_rejected_by_magic_bytes() -> None:
    """A .pdf extension on ELF content is rejected because magic bytes don't match."""
    from app.services.storage_service import validate_upload

    # Attacker renamed an ELF binary to .pdf
    with pytest.raises(ValueError, match="invalid_file_type"):
        validate_upload(UNKNOWN_MAGIC, "definitely_not_a_virus.pdf")


def test_validate_upload_text_file_rejected() -> None:
    """Plain text content is not in the allowlist and is rejected."""
    from app.services.storage_service import validate_upload

    text_content = b"Hello, I am a plain text file. " * 100

    with pytest.raises(ValueError, match="invalid_file_type"):
        validate_upload(text_content, "report.txt")


def test_validate_upload_oversize_raises_file_too_large() -> None:
    """Content exceeding 10 MB raises ValueError('file_too_large')."""
    from app.services.storage_service import MAX_SIZE_BYTES, validate_upload

    # 10 MB + 1 byte — just over the limit
    oversized = b"%PDF" + b"\x00" * (MAX_SIZE_BYTES + 1 - 4)

    with pytest.raises(ValueError, match="file_too_large"):
        validate_upload(oversized, "bigfile.pdf")


def test_validate_upload_exactly_max_size_accepted() -> None:
    """Content exactly at the 10 MB limit is accepted (boundary check)."""
    from app.services.storage_service import MAX_SIZE_BYTES, validate_upload

    exactly_max = b"%PDF" + b"\x00" * (MAX_SIZE_BYTES - 4)
    assert len(exactly_max) == MAX_SIZE_BYTES

    mime = validate_upload(exactly_max, "maxfile.pdf")
    assert mime == "application/pdf"


def test_validate_upload_size_checked_before_magic() -> None:
    """Size check fires before magic-byte check (file_too_large, not invalid_file_type)."""
    from app.services.storage_service import MAX_SIZE_BYTES, validate_upload

    # Oversized content with unknown magic bytes — must raise file_too_large, not invalid_file_type
    oversized_unknown = UNKNOWN_MAGIC + b"\x00" * MAX_SIZE_BYTES  # clearly > 10 MB

    with pytest.raises(ValueError, match="file_too_large"):
        validate_upload(oversized_unknown, "huge_malware.pdf")


# ── Constants ──────────────────────────────────────────────────────────────────

def test_max_size_bytes_is_10mb() -> None:
    """MAX_SIZE_BYTES must be exactly 10 * 1024 * 1024."""
    from app.services.storage_service import MAX_SIZE_BYTES

    assert MAX_SIZE_BYTES == 10 * 1024 * 1024


def test_max_files_is_5() -> None:
    """MAX_FILES must be exactly 5 (D-08 authoritative limit)."""
    from app.services.storage_service import MAX_FILES

    assert MAX_FILES == 5


def test_magic_bytes_dict_has_all_three_types() -> None:
    """MAGIC_BYTES must contain PDF, xlsx, and JPEG keys."""
    from app.services.storage_service import MAGIC_BYTES

    assert b"%PDF" in MAGIC_BYTES
    assert b"PK\x03\x04" in MAGIC_BYTES
    assert b"\xff\xd8\xff" in MAGIC_BYTES


# ── upload_request_file key safety (T-03-06) ─────────────────────────────────

def test_upload_request_file_key_does_not_use_raw_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    """upload_request_file must not pass the raw user filename directly into the S3 key.

    T-03-06: path traversal prevention. A filename like '../../etc/passwd' must
    not result in an S3 key containing '..' components.
    """
    from unittest.mock import MagicMock, patch


    mock_s3 = MagicMock()
    mock_db = MagicMock()
    mock_db.flush = MagicMock()

    # Capture what key gets passed to put_object
    captured_key: list[str] = []

    def _fake_put_object(**kwargs: object) -> None:
        captured_key.append(str(kwargs.get("Key", "")))

    mock_s3.put_object.side_effect = _fake_put_object

    # Also need RequestFile insert to succeed (mock)
    new_rf = MagicMock()
    new_rf.id = 1

    # Patch s3_client on app.core.storage (where it lives as a module-level var)
    import app.core.storage as storage_module
    with patch.object(storage_module, "s3_client", mock_s3):
        from app.services.storage_service import upload_request_file

        traversal_filename = "../../etc/passwd"
        upload_request_file(
            db=mock_db,
            request_id=42,
            content=PDF_MAGIC,
            filename=traversal_filename,
        )

    assert len(captured_key) == 1
    key = captured_key[0]

    # The key must not contain '..' directory traversal components
    assert ".." not in key, f"S3 key contains traversal: {key!r}"

    # The raw traversal filename must not appear in the key verbatim
    assert "../../etc/passwd" not in key, f"Raw filename leaked into S3 key: {key!r}"

    # The key must still be rooted under requests/{request_id}/
    assert key.startswith("requests/42/"), f"Key not under requests/42/: {key!r}"
