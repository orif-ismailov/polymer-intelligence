"""Portal reference data — the product catalog behind «Название товара».

The cabinet's own door onto `products`: the webapp twin authenticates a Telegram
`Client`, which a portal account is not.
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

_PATH = "/api/v1/portal/reference/products"


def test_reference_route_registered() -> None:
    from app.api.portal.reference import router

    assert "/portal/reference/products" in {r.path for r in router.routes}  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from app.core.db import get_db
    from app.main import create_app

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
    from unittest.mock import patch

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
def test_products_require_a_portal_account(api) -> None:  # noqa: ANN001
    client, _session = api
    assert client.get(_PATH).status_code == 401


@requires_real_db
def test_active_products_are_listed_in_sort_order(api) -> None:  # noqa: ANN001
    from app.models.reference import Product

    client, session = api
    with session() as db:
        account = make_account(db, "+998900000001")
        db.add_all(
            [
                Product(code="HDPE", name_ru="ПНД", category="polymer", sort_order=2),
                Product(code="PP", name_ru="Полипропилен", category="polymer", sort_order=1),
                Product(
                    code="OLD", name_ru="Снят", category="polymer", sort_order=0, is_active=False
                ),
            ]
        )
        db.commit()
        account_id = account.id

    resp = client.get(_PATH, headers=_auth(account_id))
    assert resp.status_code == 200
    # Inactive rows never reach a selector, and the order is the operator's.
    assert [row["code"] for row in resp.json()] == ["PP", "HDPE"]
