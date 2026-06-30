"""
Tests for GET /api/v1/webapp/requests/{id}/files/{file_id} — owner-only file stream.

Covers: owner gets bytes (mocked S3), request not owned → 404, file missing → 404,
no initData → 401. Fully mocked (MagicMock db + dependency overrides).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(mock_db: MagicMock, *, authed: bool = True) -> TestClient:
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    def _override_db() -> Generator[Any, None, None]:
        yield mock_db

    application.dependency_overrides[get_db] = _override_db
    if authed:
        c = MagicMock()
        c.id = 1
        application.dependency_overrides[get_current_client] = lambda: c
    return TestClient(application, raise_server_exceptions=True)


def _file(storage_path: str | None = "req/1/a.jpg", mime: str = "image/jpeg", name: str = "a.jpg") -> MagicMock:
    f = MagicMock()
    f.storage_path = storage_path
    f.mime_type = mime
    f.file_name = name
    return f


def test_owner_gets_file_bytes_200():
    mock_db = MagicMock()
    # 1st query().filter().first() → the owned Request; 2nd → the RequestFile
    mock_db.query.return_value.filter.return_value.first.side_effect = [MagicMock(), _file()]
    client = _client(mock_db)
    with patch("app.api.health._check_redis", return_value="ok"), patch("app.core.storage.s3_client") as s3:
        s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"JPEGBYTES"))}
        resp = client.get("/api/v1/webapp/requests/42/files/1")
    assert resp.status_code == 200
    assert resp.content == b"JPEGBYTES"
    assert resp.headers["content-type"].startswith("image/jpeg")


def test_request_not_owned_404():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [None]
    client = _client(mock_db)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/webapp/requests/99/files/1")
    assert resp.status_code == 404


def test_file_missing_404():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [MagicMock(), None]
    client = _client(mock_db)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/webapp/requests/42/files/999")
    assert resp.status_code == 404


def test_no_init_data_401():
    mock_db = MagicMock()
    client = _client(mock_db, authed=False)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/webapp/requests/42/files/1")
    assert resp.status_code == 401
