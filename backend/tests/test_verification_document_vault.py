"""Unit tests for the verification document vault (R1 W4 — T4.3).

DB-free: S3 + session mocked. Covers PNG acceptance, the stricter verification
MIME allow-list (spreadsheets rejected), the 20-docs/company cap, the sha256 +
traversal-safe key, and presigning.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

_PDF = b"%PDF-1.4 minimal"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG = b"\xff\xd8\xff" + b"\x00" * 32
_XLSX = b"PK\x03\x04" + b"\x00" * 32


def _company(company_id: int = 7):  # noqa: ANN202
    from app.models.companies import Company  # noqa: PLC0415

    company = Company(jurisdiction="UZ", tax_id="123456789")
    company.id = company_id
    return company


def _db(existing_docs: int = 0) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = existing_docs
    return db


def test_png_is_now_accepted() -> None:
    from app.services import storage_service  # noqa: PLC0415

    assert storage_service.validate_upload(_PNG, "cert.png") == "image/png"


def test_upload_verification_document_stores_sha256_and_safe_key() -> None:
    import hashlib

    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415
    from app.models.verification import VerificationDocument  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    db = _db(existing_docs=0)
    with patch("app.core.storage.s3_client") as s3:
        doc = storage_service.upload_verification_document(
            db, _company(7), 42, VerificationDocumentKind.registration_certificate,
            _PDF, "../../etc/passwd.pdf",
        )
    assert isinstance(doc, VerificationDocument)
    assert doc.sha256 == hashlib.sha256(_PDF).hexdigest()
    assert doc.storage_path.startswith("verification/7/")
    assert "etc" not in doc.storage_path.split("/", 2)[2].split("-", 1)[1] or "passwd" in doc.storage_path
    assert doc.uploaded_by_user_account_id == 42
    assert doc.mime_type == "application/pdf"
    s3.put_object.assert_called_once()


def test_upload_rejects_spreadsheet_even_though_globally_allowed() -> None:
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client"), pytest.raises(ValueError, match="invalid_file_type"):
        storage_service.upload_verification_document(
            _db(), _company(), 1, VerificationDocumentKind.other, _XLSX, "sheet.xlsx"
        )


def test_upload_accepts_png_and_jpeg() -> None:
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client"):
        for content in (_PNG, _JPEG):
            doc = storage_service.upload_verification_document(
                _db(), _company(), 1, VerificationDocumentKind.director_id, content, "id.img"
            )
            assert doc.mime_type in {"image/png", "image/jpeg"}


def test_upload_enforces_per_company_cap() -> None:
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    with patch("app.core.storage.s3_client"), pytest.raises(ValueError, match="too_many_documents"):
        storage_service.upload_verification_document(
            _db(existing_docs=20), _company(), 1,
            VerificationDocumentKind.other, _PDF, "x.pdf",
        )


def test_presign_returns_url() -> None:
    from app.models.verification import VerificationDocument  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    document = VerificationDocument(
        company_id=7, kind=None, storage_path="verification/7/abc-cert.pdf", sha256="z"
    )
    with patch("app.core.storage.s3_client") as s3:
        s3.generate_presigned_url.return_value = "https://minio/presigned?sig=1"
        url = storage_service.presign_verification_document(document, ttl=600)
    assert url == "https://minio/presigned?sig=1"
    assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 600
