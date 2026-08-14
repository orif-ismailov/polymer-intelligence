"""Unit tests for the company-logo storage service (P1 W1 — T1.2).

DB-free: S3 + session mocked. Covers the tighter logo rules (images only, 5 MB —
both stricter than the generic 10 MB / PDF-and-spreadsheet allow-list), the
traversal-safe key, replace-deletes-the-old-object, the fail-soft behaviour when
that delete fails, and delete_company_logo.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG = b"\xff\xd8\xff" + b"\x00" * 32
_PDF = b"%PDF-1.4 minimal"
_XLSX = b"PK\x03\x04" + b"\x00" * 32


def _company(company_id: int = 7, logo: str | None = None):  # noqa: ANN202
    from app.domains.companies.models import Company  # noqa: PLC0415

    company = Company(jurisdiction="UZ", tax_id="123456789")
    company.id = company_id
    company.logo_storage_path = logo
    return company


# ── Accepted types ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("content", "filename", "expected_mime"),
    [(_PNG, "logo.png", "image/png"), (_JPEG, "logo.jpg", "image/jpeg")],
)
def test_upload_accepts_jpeg_and_png(content: bytes, filename: str, expected_mime: str) -> None:
    from app.services import storage_service  # noqa: PLC0415

    db = MagicMock()
    company = _company(7)
    with patch("app.core.storage.s3_client") as s3:
        storage_service.upload_company_logo(db, company, content, filename)

    assert company.logo_storage_path is not None
    assert company.logo_storage_path.startswith("companies/7/logo/")
    assert company.logo_storage_path.endswith(".png" if expected_mime == "image/png" else ".jpg")
    s3.put_object.assert_called_once()
    assert s3.put_object.call_args.kwargs["ContentType"] == expected_mime


# ── Rejected types: a logo is an image, not any old allowed document ──────────


@pytest.mark.parametrize(("content", "filename"), [(_PDF, "logo.pdf"), (_XLSX, "logo.xlsx")])
def test_upload_rejects_non_images_even_though_globally_allowed(
    content: bytes, filename: str
) -> None:
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client") as s3, pytest.raises(
        ValueError, match="invalid_file_type"
    ):
        storage_service.upload_company_logo(MagicMock(), _company(), content, filename)
    s3.put_object.assert_not_called()


def test_upload_rejects_a_pdf_masquerading_as_jpg() -> None:
    """Extension is cosmetic — the magic bytes decide (T-03-04)."""
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client"), pytest.raises(ValueError, match="invalid_file_type"):
        storage_service.upload_company_logo(MagicMock(), _company(), _PDF, "sneaky.jpg")


# ── Size: 5 MB, stricter than the generic 10 MB ──────────────────────────────


def test_upload_rejects_over_5mb_even_though_generic_limit_is_10mb() -> None:
    from app.services import storage_service  # noqa: PLC0415

    oversized = _PNG + b"\x00" * (5 * 1024 * 1024)
    assert len(oversized) < storage_service.MAX_SIZE_BYTES, "must be under the generic cap"

    with patch("app.core.storage.s3_client") as s3, pytest.raises(
        ValueError, match="file_too_large"
    ):
        storage_service.upload_company_logo(MagicMock(), _company(), oversized, "big.png")
    s3.put_object.assert_not_called()


def test_upload_accepts_just_under_5mb() -> None:
    from app.services import storage_service  # noqa: PLC0415

    content = _PNG + b"\x00" * (storage_service.MAX_LOGO_SIZE_BYTES - len(_PNG) - 1)
    with patch("app.core.storage.s3_client"):
        storage_service.upload_company_logo(MagicMock(), _company(), content, "ok.png")


# ── Replace deletes the previous object ──────────────────────────────────────


def test_replace_deletes_the_previous_object() -> None:
    from app.services import storage_service  # noqa: PLC0415

    old_key = "companies/7/logo/deadbeef.png"
    company = _company(7, logo=old_key)
    with patch("app.core.storage.s3_client") as s3:
        storage_service.upload_company_logo(MagicMock(), company, _PNG, "new.png")

    s3.delete_object.assert_called_once()
    assert s3.delete_object.call_args.kwargs["Key"] == old_key
    assert company.logo_storage_path != old_key


def test_replace_is_fail_soft_when_deleting_the_old_object_fails() -> None:
    """A stale object in S3 must not fail the user's upload (FR-M1)."""
    from app.services import storage_service  # noqa: PLC0415

    company = _company(7, logo="companies/7/logo/old.png")
    with patch("app.core.storage.s3_client") as s3:
        s3.delete_object.side_effect = RuntimeError("s3 down")
        storage_service.upload_company_logo(MagicMock(), company, _PNG, "new.png")

    # New logo still took effect despite the failed cleanup.
    assert company.logo_storage_path is not None
    assert company.logo_storage_path != "companies/7/logo/old.png"


def test_first_upload_does_not_try_to_delete_anything() -> None:
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client") as s3:
        storage_service.upload_company_logo(MagicMock(), _company(logo=None), _PNG, "logo.png")
    s3.delete_object.assert_not_called()


# ── Delete ───────────────────────────────────────────────────────────────────


def test_delete_removes_the_object_and_clears_the_column() -> None:
    from app.services import storage_service  # noqa: PLC0415

    company = _company(7, logo="companies/7/logo/x.png")
    with patch("app.core.storage.s3_client") as s3:
        storage_service.delete_company_logo(MagicMock(), company)

    s3.delete_object.assert_called_once()
    assert company.logo_storage_path is None


def test_delete_is_a_no_op_without_a_logo() -> None:
    from app.services import storage_service  # noqa: PLC0415

    company = _company(logo=None)
    with patch("app.core.storage.s3_client") as s3:
        storage_service.delete_company_logo(MagicMock(), company)
    s3.delete_object.assert_not_called()
    assert company.logo_storage_path is None


def test_delete_is_fail_soft_when_s3_delete_fails() -> None:
    """The column must still clear, or the user can never replace a broken logo."""
    from app.services import storage_service  # noqa: PLC0415

    company = _company(7, logo="companies/7/logo/x.png")
    with patch("app.core.storage.s3_client") as s3:
        s3.delete_object.side_effect = RuntimeError("s3 down")
        storage_service.delete_company_logo(MagicMock(), company)
    assert company.logo_storage_path is None


# ── Traversal safety ─────────────────────────────────────────────────────────


def test_key_is_traversal_safe_and_ignores_the_client_filename() -> None:
    from app.services import storage_service  # noqa: PLC0415

    company = _company(7)
    with patch("app.core.storage.s3_client"):
        storage_service.upload_company_logo(
            MagicMock(), company, _PNG, "../../../etc/passwd.png"
        )
    key = company.logo_storage_path
    assert key is not None
    assert ".." not in key
    assert key.startswith("companies/7/logo/")
    # The logo key is derived from a random token, not the client's name at all.
    assert "passwd" not in key
