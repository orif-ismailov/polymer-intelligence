"""The API docs have their own switch (audit IMEX-08).

They used to ride on DEBUG, which the internet-facing dev server keeps on for its
E-IMZO stub — so dev-api.ai-imex.com published every endpoint to anyone. DEBUG must
no longer reveal them; only API_DOCS_ENABLED does.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


def _client(*, debug: bool, docs: bool) -> TestClient:
    from app.core.config import settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    with patch.object(settings, "DEBUG", debug), patch.object(settings, "API_DOCS_ENABLED", docs):
        return TestClient(create_app())


@pytest.mark.parametrize("path", _DOC_PATHS)
def test_debug_alone_does_not_publish_the_docs(path: str) -> None:
    assert _client(debug=True, docs=False).get(path).status_code == 404


@pytest.mark.parametrize("path", _DOC_PATHS)
def test_the_docs_flag_publishes_them(path: str) -> None:
    assert _client(debug=False, docs=True).get(path).status_code == 200
