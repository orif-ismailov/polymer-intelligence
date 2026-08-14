"""Portal news API tests (R2 W3 T3.4).

Route reg + response-model parity vs the webapp news surface are DB-free. A real-DB
smoke confirms portal auth reaches the shared news service (empty feed → []).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/news"


def _routes(router):  # noqa: ANN001, ANN202
    return {r.path: r for r in router.routes}  # type: ignore[attr-defined]


def test_news_routes_registered() -> None:
    from app.domains.news.api_portal import router  # noqa: PLC0415

    paths = set(_routes(router))
    assert "/portal/news/articles" in paths
    assert "/portal/news/articles/{signal_id}" in paths
    assert "/portal/news/articles/filters" in paths
    assert "/portal/news" in paths
    assert "/portal/news/{report_id}" in paths


def test_response_models_match_webapp() -> None:
    """Parity: every portal news endpoint returns the SAME response model as its
    webapp twin — the surface cannot drift from the Mini App."""
    from app.domains.news.api_portal import router as portal_router  # noqa: PLC0415
    from app.domains.news.api_webapp import router as webapp_router  # noqa: PLC0415

    def models(router, prefix):  # noqa: ANN001, ANN202
        out = {}
        for r in router.routes:  # type: ignore[attr-defined]
            suffix = r.path.replace(prefix, "", 1)
            out[(suffix, tuple(sorted(r.methods)))] = getattr(r, "response_model", None)
        return out

    portal = models(portal_router, "/portal/news")
    webapp = models(webapp_router, "/webapp/news")
    assert portal == webapp, f"portal↔webapp news surface drift: {portal} != {webapp}"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
def test_articles_requires_portal_auth_and_returns_list(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        account = make_account(db, "+998900007001")
        db.commit()
        account_id = account.id

    # unauthenticated → 401
    assert client.get(f"{_BASE}/articles").status_code == 401
    # authenticated portal account → 200 with a (possibly empty) list
    resp = client.get(f"{_BASE}/articles", headers=_auth(account_id))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
