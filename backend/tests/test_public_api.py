"""The anonymous marketplace storefront (/api/v1/public).

The point of this suite is not that the endpoints return data. It is that they
return data to a caller with NO credentials, and that the things which must
never be public still are not. The catalog and directory filters are covered by
their own suites; what is tested here is the boundary.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/public"


# ── Registration + no-auth contract (no DB needed) ───────────────────────────


def test_public_routes_registered() -> None:
    from app.api.public import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/public/offers" in paths
    assert "/public/offers/{offer_id}" in paths
    assert "/public/categories" in paths
    assert "/public/directories/{slug}" in paths
    assert "/public/directories/{slug}/{company_id}" in paths
    assert "/public/stats" in paths
    assert "/public/prices" in paths
    assert "/public/news" in paths
    assert "/public/news/articles" in paths
    assert "/public/news/articles/filters" in paths
    assert "/public/news/articles/{signal_id}" in paths
    assert "/public/sitemap" in paths


def test_news_filters_route_is_declared_before_the_id_route() -> None:
    """`/articles/filters` must win over `/articles/{signal_id}`.

    Starlette matches in declaration order, so the id route declared first would
    swallow "filters" and answer 422 on a path that has to work.
    """
    from app.api.public import router  # noqa: PLC0415

    paths = [r.path for r in router.routes]  # type: ignore[attr-defined]
    assert paths.index("/public/news/articles/filters") < paths.index(
        "/public/news/articles/{signal_id}"
    )


def test_public_news_reader_matches_the_portal_surface() -> None:
    """The three reader routes are the portal's, minus the session.

    `/news` (the home rail) is deliberately excluded: it is a different endpoint
    with its own narrower signature. These three exist so a public, indexable
    page can render, and they must keep answering with the SAME models the
    signed-in surfaces use -- a public schema that drifts is how a field nobody
    audited becomes crawlable.
    """
    from app.api.portal.news import router as portal_router  # noqa: PLC0415
    from app.api.public import router as public_router  # noqa: PLC0415

    def models(router, prefix: str) -> dict[str, object]:  # noqa: ANN001
        return {
            r.path.removeprefix(prefix): r.response_model  # type: ignore[attr-defined]
            for r in router.routes
            if r.path.startswith(f"{prefix}/articles")  # type: ignore[attr-defined]
        }

    assert models(public_router, "/public/news") == models(portal_router, "/portal/news")


# ── The news reader answers a stranger (DB mocked, auth NOT overridden) ───────
#
# The auth dependency is deliberately left un-overridden in this client. That is
# the assertion: these requests carry no Authorization header and no cookie, and
# they have to come back 200. The portal suite can only ever test the authed
# path, so this is the one place the anonymous contract is exercised end to end.


def _anon_client() -> TestClient:
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _override_db() -> Generator[Any, None, None]:
        yield MagicMock()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=True)


_NEWS_CARD = {
    "id": 42,
    "headline": "Shurtan останавливает PP-линию",
    "category": "plant_shutdown",
    "importance": "high",
    "market_impact": "negative",
    "summary": "Плановый ремонт сократит выпуск PP.",
    "country": "UZ",
    "companies": ["Shurtan GCC"],
    "related_products": ["PP"],
    "source_name": "PetroTG",
    "published_at": "2026-07-18T08:00:00+00:00",
    "image_url": None,
}


def test_news_articles_are_listed_without_any_credentials() -> None:
    with patch("app.services.news_service.list_news_articles", return_value=[_NEWS_CARD]):
        resp = _anon_client().get(f"{_BASE}/news/articles")
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["headline"].startswith("Shurtan")


def test_news_article_detail_and_facets_are_anonymous() -> None:
    client = _anon_client()

    facets = {
        "categories": [{"value": "plant_shutdown", "count": 4}],
        "countries": [{"value": "UZ", "count": 9}],
        "products": [{"value": "PP", "count": 6}],
    }
    with patch("app.services.news_service.list_news_filter_options", return_value=facets):
        resp = client.get(f"{_BASE}/news/articles/filters")
    assert resp.status_code == 200, resp.text
    assert resp.json()["countries"][0]["value"] == "UZ"

    detail = {**_NEWS_CARD, "body": "…", "source_url": "https://example.test/a"}
    with patch("app.services.news_service.get_news_article", return_value=detail):
        resp = client.get(f"{_BASE}/news/articles/42")
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_url"] == "https://example.test/a"

    with patch("app.services.news_service.get_news_article", return_value=None):
        resp = client.get(f"{_BASE}/news/articles/999")
    assert resp.status_code == 404


def test_public_news_forwards_every_filter_to_the_service() -> None:
    """The reader is only as good as the params that survive the handler."""
    with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list:
        resp = _anon_client().get(
            f"{_BASE}/news/articles",
            params={
                "q": "shurtan", "scope": "producers", "category": "plant_shutdown",
                "country": "UZ", "company": "Shurtan", "product": "PP",
                "importance": "high", "source_id": 5, "sort": "newest",
                "lang": "uz", "limit": 10, "days": 14,
            },
        )
    assert resp.status_code == 200, resp.text
    assert mock_list.call_args.kwargs == {
        "limit": 10, "days": 14, "q": "shurtan", "scope": "producers",
        "category": "plant_shutdown", "country": "UZ", "company": "Shurtan",
        "product": "PP", "importance": "high", "source_id": 5, "sort": "newest",
        "lang": "uz",
    }


def test_public_news_scope_all_means_no_scope() -> None:
    with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list:
        resp = _anon_client().get(f"{_BASE}/news/articles", params={"scope": "all"})
    assert resp.status_code == 200
    assert mock_list.call_args.kwargs["scope"] is None


def test_no_public_route_depends_on_an_account() -> None:
    """The whole surface must be reachable without a session.

    This is the regression that matters: a future edit adding
    `account: UserAccount = Depends(get_current_account)` to one handler for
    convenience would silently de-index every page that route renders. Asserting
    it here means that edit fails in CI rather than in Search Console six weeks
    later.
    """
    from app.api.deps import get_current_account, get_current_client  # noqa: PLC0415
    from app.api.public import router  # noqa: PLC0415

    guarded = {get_current_account, get_current_client}
    for route in router.routes:
        dependant = route.dependant  # type: ignore[attr-defined]
        calls = {d.call for d in dependant.dependencies}
        assert not (calls & guarded), f"{route.path} requires auth"  # type: ignore[attr-defined]


def test_directory_slugs_cover_every_public_role() -> None:
    """The nav promises four directories; the slug map must serve all four."""
    from app.api.public import DIRECTORY_SLUGS  # noqa: PLC0415
    from app.services.directory_service import PUBLIC_DIRECTORY_ROLES  # noqa: PLC0415

    assert set(DIRECTORY_SLUGS.values()) == set(PUBLIC_DIRECTORY_ROLES)


def test_public_offer_card_omits_seller_contact() -> None:
    """A stranger gets the listing, never the way to phone the seller directly.

    Contact reveal is what the authenticated inquiry flow is for; leaking it
    here would also make every supplier's number scrapable.
    """
    from app.schemas.public import PublicOfferCard, PublicOfferDetail  # noqa: PLC0415

    forbidden = {"seller", "contact", "phone", "telegram", "telegram_username", "email"}
    for model in (PublicOfferCard, PublicOfferDetail):
        assert not (set(model.model_fields) & forbidden), model.__name__


def test_public_offer_detail_omits_moderation_internals() -> None:
    from app.schemas.public import PublicOfferDetail  # noqa: PLC0415

    forbidden = {
        "status",
        "moderation_note",
        "moderated_by",
        "compliance",
        "compliance_ok",
        "compliance_missing",
        "seller_id",
    }
    assert not (set(PublicOfferDetail.model_fields) & forbidden)


def test_public_company_card_omits_bank_and_case_data() -> None:
    from app.schemas.public import PublicCompanyCard, PublicCompanyDetail  # noqa: PLC0415

    forbidden = {
        "bank_accounts",
        "documents",
        "active_case",
        "tax_id",
        "members",
        "contact_phone",
    }
    for model in (PublicCompanyCard, PublicCompanyDetail):
        assert not (set(model.model_fields) & forbidden), model.__name__


def test_public_logistics_snippet_carries_no_contact_route() -> None:
    """The carrier block is capability data, not a way to reach the company.

    It is the first nested object on the anonymous company payload, so the
    field-name guard above does not see inside it. Everything a carrier fills in
    during registration is safe to publish EXCEPT a direct line — the platform's
    whole position is that contact happens through it.
    """
    from app.schemas.public import PublicLogisticsSnippet  # noqa: PLC0415

    forbidden = {
        "phone",
        "email",
        "website",
        "contact_phone",
        "contact_email",
        "contact_name",
        "director_name",
        "tax_id",
        "bank_accounts",
    }
    assert not (set(PublicLogisticsSnippet.model_fields) & forbidden)


def test_logistics_snippet_is_none_without_a_profile() -> None:
    """No questionnaire → no block, so the storefront omits the whole card.

    `{}` and `None` are different answers here: a carrier that reached the step
    and skipped it still gets a (blank) block, because "filled in nothing" and
    "is not a carrier" are different facts about a company.
    """
    from app.models.companies import Company  # noqa: PLC0415
    from app.services import logistics_service  # noqa: PLC0415

    assert logistics_service.logistics_profile_snippet(Company(logistics_profile=None)) is None
    assert logistics_service.logistics_profile_snippet(Company(logistics_profile={})) is None


def test_logistics_snippet_survives_a_malformed_blob() -> None:
    """Untyped JSONB written by a wizard that has already changed shape once.

    A value of the wrong type must read as absent rather than raise inside the
    response serializer — one bad row would otherwise 500 a whole directory
    page. `True` is called out because `bool` is an `int` subclass in Python, so
    a stray flag would otherwise render as «Опыт работы: 1 год».
    """
    from app.models.companies import Company  # noqa: PLC0415
    from app.services import logistics_service  # noqa: PLC0415

    snippet = logistics_service.logistics_profile_snippet(
        Company(
            logistics_profile={
                "city": 42,
                "services": "not-a-list",
                "from_countries": ["CN", "", "  ", "RU"],
                "years_experience": True,
                "projects_completed": -5,
                "tariff_model": "   ",
            }
        )
    )

    assert snippet is not None
    assert snippet["city"] is None
    assert snippet["services"] == []
    assert snippet["from_countries"] == ["CN", "RU"]
    assert snippet["years_experience"] is None
    assert snippet["projects_completed"] is None
    assert snippet["tariff_model"] is None


# ── Live DB behaviour ────────────────────────────────────────────────────────


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


def _confirm_role(db, company_id: int, role) -> None:  # noqa: ANN001
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus  # noqa: PLC0415

    db.add(
        CompanyBusinessRole(
            company_id=company_id, role=role, status=BusinessRoleStatus.confirmed
        )
    )


@requires_real_db
def test_offers_are_listed_without_any_credentials(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007001")
        company = make_company(
            db,
            owner,
            tax_id="317000001",
            legal_name="Anon Visible Chem",
            short_name="AnonChem",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        make_seller_offer(db, company=company, grade_text="PUBLIC-HDPE-1")
        db.commit()

    # No Authorization header anywhere in this request.
    resp = client.get(f"{_BASE}/offers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(i["grade_text"] == "PUBLIC-HDPE-1" for i in body["items"])


@requires_real_db
def test_unapproved_offers_never_reach_the_public_catalog(api) -> None:  # noqa: ANN001
    """The approved-only gate is the whole visibility rule, so pin it here too."""
    from app.models.enums import CompanyStatus, SellerOfferStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007002")
        company = make_company(
            db,
            owner,
            tax_id="317000002",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        pending = make_seller_offer(
            db,
            company=company,
            grade_text="PENDING-SECRET",
            status=SellerOfferStatus.pending_moderation,
        )
        db.commit()
        pending_id = pending.id

    listing = client.get(f"{_BASE}/offers").json()
    assert all(i["grade_text"] != "PENDING-SECRET" for i in listing["items"])
    assert client.get(f"{_BASE}/offers/{pending_id}").status_code == 404


@requires_real_db
def test_total_reflects_the_filter_not_the_page(api) -> None:  # noqa: ANN001
    """`total` is what the grid prints and what pagination ends on."""
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007003")
        company = make_company(
            db,
            owner,
            tax_id="317000003",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        for n in range(5):
            make_seller_offer(db, company=company, grade_text=f"COUNTME-{n}")
        db.commit()

    page = client.get(f"{_BASE}/offers", params={"q": "COUNTME", "limit": 2}).json()
    assert len(page["items"]) == 2
    assert page["total"] == 5


@requires_real_db
def test_directory_serves_each_role_and_scopes_the_profile(api) -> None:  # noqa: ANN001
    """A laboratory is not a trader, and /laboratories/{id} must know that."""
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        lab_owner = make_account(db, "+998900007101")
        lab = make_company(
            db,
            lab_owner,
            tax_id="317000101",
            legal_name="Tashkent Polymer Lab",
            short_name="TPL",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _confirm_role(db, lab.id, Role.laboratory)

        trader_owner = make_account(db, "+998900007102")
        trader = make_company(
            db,
            trader_owner,
            tax_id="317000102",
            legal_name="Silk Road Polymers",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _confirm_role(db, trader.id, Role.trader)
        db.commit()
        lab_id, trader_id = lab.id, trader.id

    labs = client.get(f"{_BASE}/directories/laboratories").json()
    assert {i["id"] for i in labs["items"]} == {lab_id}
    assert labs["role"] == "laboratory"

    traders = client.get(f"{_BASE}/directories/traders").json()
    assert {i["id"] for i in traders["items"]} == {trader_id}

    # Reached through the wrong directory, the company is not there.
    assert client.get(f"{_BASE}/directories/laboratories/{trader_id}").status_code == 404
    assert client.get(f"{_BASE}/directories/laboratories/{lab_id}").status_code == 200
    assert client.get(f"{_BASE}/directories/nonsense").status_code == 404


@requires_real_db
def test_unverified_company_is_absent_from_every_directory(api) -> None:  # noqa: ANN001
    """`declared` is a self-claim. Only `confirmed` on a verified company lists."""
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    client, session = api
    with session() as db:
        # Verified company, but the lab role is only DECLARED.
        a_owner = make_account(db, "+998900007201")
        declared = make_company(
            db,
            a_owner,
            tax_id="317000201",
            legal_name="Self Declared Lab",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        db.add(
            CompanyBusinessRole(
                company_id=declared.id,
                role=Role.laboratory,
                status=BusinessRoleStatus.declared,
            )
        )

        # Confirmed lab role, but the company itself is still pending.
        b_owner = make_account(db, "+998900007202")
        unverified = make_company(
            db,
            b_owner,
            tax_id="317000202",
            legal_name="Pending Lab",
            status=CompanyStatus.pending_verification,
        )
        _confirm_role(db, unverified.id, Role.laboratory)
        db.commit()
        declared_id, unverified_id = declared.id, unverified.id

    listed = {i["id"] for i in client.get(f"{_BASE}/directories/laboratories").json()["items"]}
    assert declared_id not in listed
    assert unverified_id not in listed
    assert client.get(f"{_BASE}/directories/laboratories/{declared_id}").status_code == 404
    assert client.get(f"{_BASE}/directories/laboratories/{unverified_id}").status_code == 404


@requires_real_db
def test_stats_and_sitemap_are_anonymous_and_consistent(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007301")
        company = make_company(
            db,
            owner,
            tax_id="317000301",
            legal_name="Sitemap Chem",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _confirm_role(db, company.id, Role.manufacturer)
        offer = make_seller_offer(db, company=company, grade_text="SITEMAP-PP")
        db.commit()
        offer_id, company_id = offer.id, company.id

    stats = client.get(f"{_BASE}/stats").json()
    assert stats["offer_count"] >= 1
    assert stats["company_count"] >= 1
    assert stats["directory_counts"]["manufacturer"] >= 1

    sitemap = client.get(f"{_BASE}/sitemap").json()
    paths = {e["path"] for e in sitemap["entries"]}
    assert f"/market/{offer_id}" in paths
    assert f"/manufacturers/{company_id}" in paths
    assert sitemap["truncated"] is False


@requires_real_db
def test_stats_expose_filter_facets_drawn_from_the_live_catalog(api) -> None:  # noqa: ANN001
    """The sidebar's four dropdowns are fed from `/public/stats`, not a static list.

    The point of aggregating them is that an option can never match nothing, so
    this pins both halves: the facet appears, and filtering by it returns the
    offer it was derived from.
    """
    from app.models.enums import CompanyStatus, PriceBasis  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007401")
        company = make_company(
            db,
            owner,
            tax_id="317000401",
            legal_name="Facet Chem LLC",
            short_name="FacetChem",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        make_seller_offer(
            db,
            company=company,
            grade_text="FACET-FOB-1",
            country="TR",
            incoterms=PriceBasis.FOB,
        )
        db.commit()
        company_id = company.id

    stats = client.get(f"{_BASE}/stats").json()
    assert "TR" in {f["value"] for f in stats["countries"]}
    assert "FOB" in {f["value"] for f in stats["incoterms"]}
    assert str(company_id) in {f["value"] for f in stats["companies"]}
    # Facets carry their own counts so a dropdown can show "TR (3)".
    assert all(f["offer_count"] >= 1 for f in stats["countries"])

    listed = client.get(f"{_BASE}/offers", params={"incoterms": "FOB", "country": "TR"}).json()
    assert listed["total"] >= 1
    assert any(i["grade_text"] == "FACET-FOB-1" for i in listed["items"])


@requires_real_db
def test_incoterms_filter_excludes_other_delivery_terms(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus, PriceBasis  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007402")
        company = make_company(
            db,
            owner,
            tax_id="317000402",
            legal_name="Incoterms Chem",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        make_seller_offer(db, company=company, grade_text="ONLY-CIF", incoterms=PriceBasis.CIF)
        db.commit()

    grades = {
        i["grade_text"]
        for i in client.get(f"{_BASE}/offers", params={"incoterms": "EXW"}).json()["items"]
    }
    assert "ONLY-CIF" not in grades


@requires_real_db
def test_carrier_questionnaire_reaches_the_anonymous_directory(api) -> None:  # noqa: ANN001
    """The gap this whole surface exists to close.

    `logistics_profile` was written by the registration wizard and stored, but
    `_company_card` built every directory row from the MANUFACTURER snippet — so
    a carrier's public page showed six blank production fields and none of what
    it had actually filled in. Asserted on both the list row and the detail, and
    with no credentials, because that is the only tier a crawler or a first-time
    visitor ever sees.
    """
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900007501")
        carrier = make_company(
            db,
            owner,
            tax_id="317000501",
            legal_name="Trans Asia Logistics",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
            logistics_profile={
                "city": "Ташкент",
                "description": "Международные перевозки нефтехимической продукции.",
                "services": ["international_road", "sea"],
                "from_countries": ["CN", "IR"],
                "to_countries": ["UZ"],
                "popular_routes": ["shanghai_tashkent"],
                "cargo_types": ["petrochemicals_polymers"],
                "capabilities": ["own_trucks", "sea_containers"],
                "tariff_model": "per_container",
                "years_experience": 12,
                "projects_completed": 1200,
            },
        )
        _confirm_role(db, carrier.id, Role.logistics_provider)

        # A non-carrier in the same environment must stay untouched: the block
        # is NULL for it, not an empty object the storefront would render.
        plain_owner = make_account(db, "+998900007502")
        plain = make_company(
            db,
            plain_owner,
            tax_id="317000502",
            legal_name="Silk Road Trading",
            status=CompanyStatus.verified,
            verified_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _confirm_role(db, plain.id, Role.trader)
        db.commit()
        carrier_id, plain_id = carrier.id, plain.id

    row = next(
        i
        for i in client.get(f"{_BASE}/directories/logistics").json()["items"]
        if i["id"] == carrier_id
    )
    assert row["logistics"]["services"] == ["international_road", "sea"]
    assert row["logistics"]["years_experience"] == 12

    detail = client.get(f"{_BASE}/directories/logistics/{carrier_id}")
    assert detail.status_code == 200
    block = detail.json()["logistics"]
    assert block["city"] == "Ташкент"
    assert block["capabilities"] == ["own_trucks", "sea_containers"]
    assert block["projects_completed"] == 1200
    assert block["tariff_model"] == "per_container"

    assert client.get(f"{_BASE}/directories/traders/{plain_id}").json()["logistics"] is None
