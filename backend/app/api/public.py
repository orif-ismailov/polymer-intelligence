"""Anonymous marketplace endpoints (/api/v1/public).

The storefront at the front of the portal is server-rendered for search engines,
which means the render happens with no session and every fetch on this router
must answer a stranger. That is the one thing that makes this file different
from `app/api/portal/`: there is no `get_current_account` anywhere in it, by
design and not by omission.

What keeps that safe is that nothing here writes its own visibility rule:

* offers come from `offer_service`'s approved-only catalog query, the same one
  the cabinet and the Mini App use;
* companies come from `directory_service`, which filters to verified companies
  holding a CONFIRMED role;
* the response models live in `app/schemas/public.py`, which drops the seller
  contact block.

So making something public is a deliberate edit in three places, not a forgotten
dependency in one.

Rate limiting is nginx's job (these are cacheable GETs behind a CDN-shaped edge),
not a per-route dependency here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.companies import Company
from app.models.enums import CompanyBusinessRole as CompanyBusinessRoleEnum
from app.models.enums import OfferAvailability, PriceBasis
from app.schemas.public import (
    PublicCategoryOut,
    PublicCompanyCard,
    PublicCompanyDetail,
    PublicCompanyListOut,
    PublicFacetOut,
    PublicLogisticsSnippet,
    PublicOfferCard,
    PublicOfferDetail,
    PublicOfferListOut,
    PublicQuoteOut,
    PublicReviewOut,
    PublicSitemapEntry,
    PublicSitemapOut,
    PublicStatsOut,
)
from app.schemas.reports import NewsArticleCard
from app.services import (
    directory_service,
    logistics_service,
    manufacturer_service,
    news_service,
    offer_service,
    public_market_service,
    review_service,
    storage_service,
)

router = APIRouter(prefix="/public", tags=["public"])

#: URL segment per directory role. These are the marketplace's public paths and
#: they are part of the SEO contract -- renaming one is a redirect, not an edit.
#: Mirrors PUBLIC_DIRECTORIES in portal/src/shared/config/publicRoutes.ts.
DIRECTORY_SLUGS: dict[str, CompanyBusinessRoleEnum] = {
    "manufacturers": CompanyBusinessRoleEnum.manufacturer,
    "traders": CompanyBusinessRoleEnum.trader,
    "logistics": CompanyBusinessRoleEnum.logistics_provider,
    "laboratories": CompanyBusinessRoleEnum.laboratory,
}

#: Sitemap protocol ceiling for a single file.
_SITEMAP_MAX_URLS = 50_000


def _role_or_404(slug: str) -> CompanyBusinessRoleEnum:
    role = DIRECTORY_SLUGS.get(slug)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown directory")
    return role


def _company_card(
    db: Session,
    company: Company,
    ratings: dict[int, tuple[float, int]] | None = None,
) -> PublicCompanyCard:
    """One directory row.

    `ratings` is passed in, not looked up: this function already costs one
    query per row for `offer_count_for`, and a per-company aggregate beside it
    would double that on a 24-row page. Callers fetch the whole page's
    aggregate in one grouped query and hand it down.
    """
    snippet = manufacturer_service.profile_snippet(company)
    logistics = logistics_service.logistics_profile_snippet(company)
    rating, review_count = (ratings or {}).get(company.id, (None, 0))
    export_raw = snippet.get("export_countries")
    production = snippet.get("production_type")
    main_products = snippet.get("main_products")
    employees = snippet.get("employees")
    founded = snippet.get("founded_year")
    iso = snippet.get("iso_certification")
    return PublicCompanyCard(
        id=company.id,
        public_id=company.public_id,
        legal_name=company.legal_name,
        short_name=company.short_name,
        legal_address=company.legal_address,
        jurisdiction=company.jurisdiction,
        logo_url=storage_service.presign_company_logo(company),
        cover_url=storage_service.presign_company_cover(company),
        verified_at=company.verified_at,
        roles=directory_service.confirmed_roles(company),
        offer_count=manufacturer_service.offer_count_for(db, company.id),
        production_type=production if isinstance(production, str) else None,
        main_products=main_products if isinstance(main_products, str) else None,
        employees=employees if isinstance(employees, int) else None,
        founded_year=founded if isinstance(founded, int) else None,
        export_countries=[str(x) for x in export_raw] if isinstance(export_raw, list) else [],
        iso_certification=iso if isinstance(iso, str) else None,
        logistics=PublicLogisticsSnippet(**logistics) if logistics is not None else None,
        rating=rating,
        review_count=review_count,
    )


def _reviews_out(db: Session, company_id: int) -> list[PublicReviewOut]:
    """First page of published reviews, with the author COMPANY resolved.

    One extra query for the names rather than one per review — a profile with 20
    reviews would otherwise be 20 round trips for a tab most visitors never open.
    """
    rows = review_service.list_published(db, company_id)
    if not rows:
        return []
    author_ids = {r.author_company_id for r in rows}
    names = {
        c.id: (c.short_name or c.legal_name)
        for c in db.query(Company).filter(Company.id.in_(author_ids)).all()
    }
    return [
        PublicReviewOut(
            id=r.id,
            rating=r.rating,
            body=r.body,
            author_company_name=names.get(r.author_company_id),
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Catalog ───────────────────────────────────────────────────────────────────


@router.get("/offers", response_model=PublicOfferListOut, summary="Public offer catalog")
def list_public_offers(
    product_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    availability: OfferAvailability | None = Query(default=None),
    country: str | None = Query(default=None, max_length=2),
    incoterms: PriceBasis | None = Query(default=None),
    seller_company_id: int | None = Query(default=None),
    has_lab_passport: bool = Query(default=False),
    lab_verified: bool = Query(default=False),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PublicOfferListOut:
    """GET /public/offers -- approved listings with filters, paging and a total.

    The total is what lets the grid say how many results a filter has and lets
    pagination know where it ends. The cabinet's market screen guesses that from
    a short page, which is wrong on an exact multiple of the page size.
    """
    normalized_country = country.upper() if country else None
    offers = offer_service.list_catalog(
        db,
        product_id=product_id,
        q=q,
        availability=availability,
        country=normalized_country,
        incoterms=incoterms,
        company_id=seller_company_id,
        has_lab_passport=has_lab_passport,
        lab_verified=lab_verified,
        limit=limit,
        offset=offset,
    )
    total = offer_service.count_catalog(
        db,
        product_id=product_id,
        q=q,
        availability=availability,
        country=normalized_country,
        incoterms=incoterms,
        company_id=seller_company_id,
        has_lab_passport=has_lab_passport,
        lab_verified=lab_verified,
    )
    return PublicOfferListOut(
        items=[PublicOfferCard.model_validate(o) for o in offers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/offers/{offer_id}",
    response_model=PublicOfferDetail,
    summary="Public offer page",
)
def get_public_offer(offer_id: int, db: Session = Depends(get_db)) -> PublicOfferDetail:
    """GET /public/offers/{id} -- one approved listing, or 404.

    A withdrawn or rejected offer 404s rather than 403s: to an anonymous caller
    there is no difference between "this was taken down" and "this never existed",
    and a 403 would confirm the id is real.
    """
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    out = PublicOfferDetail.model_validate(offer)
    if offer.company is not None:
        out.seller_company_id = offer.company.id
        out.seller_display_name = offer.company.short_name or offer.company.legal_name
    return out


@router.get(
    "/categories",
    response_model=list[PublicCategoryOut],
    summary="Category tiles with offer counts",
)
def list_public_categories(
    lang: str = Query(default="ru", max_length=8),
    db: Session = Depends(get_db),
) -> list[PublicCategoryOut]:
    """GET /public/categories -- the storefront's category grid."""
    return [
        PublicCategoryOut(
            product_id=row.product_id,
            code=row.code,
            label=row.label,
            offer_count=row.offer_count,
        )
        for row in public_market_service.category_tiles(db, lang=lang)
    ]


# ── Directories ───────────────────────────────────────────────────────────────


@router.get(
    "/directories/{slug}",
    response_model=PublicCompanyListOut,
    summary="A public company directory (manufacturers / traders / logistics / laboratories)",
)
def list_public_directory(
    slug: str,
    q: str | None = Query(default=None, max_length=100),
    country: str | None = Query(default=None, max_length=2),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PublicCompanyListOut:
    """GET /public/directories/{slug} -- one page of verified companies.

    Four directories, one endpoint. They differ only by which confirmed role a
    company must hold, so four copies of this would be four chances for the
    laboratories page to forget the verified filter.
    """
    role = _role_or_404(slug)
    items, total = directory_service.list_by_role(
        db, role=role, q=q, country=country, limit=limit, offset=offset
    )
    ratings = review_service.rating_summary_for(db, [c.id for c in items])
    return PublicCompanyListOut(
        items=[_company_card(db, c, ratings) for c in items],
        total=total,
        limit=limit,
        offset=offset,
        role=str(role),
    )


@router.get(
    "/directories/{slug}/{company_id}",
    response_model=PublicCompanyDetail,
    summary="A company's public profile",
)
def get_public_company(
    slug: str,
    company_id: int,
    offers_limit: int = Query(default=12, ge=1, le=48),
    db: Session = Depends(get_db),
) -> PublicCompanyDetail:
    """GET /public/directories/{slug}/{id} -- a verified company's public sheet.

    Scoped to the directory it was reached through, so /laboratories/{id} cannot
    render a company that only ever confirmed a trader role.
    """
    role = _role_or_404(slug)
    company = directory_service.get_public_company(db, company_id, role=role)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    ratings = review_service.rating_summary_for(db, [company.id])
    card = _company_card(db, company, ratings)
    offers = offer_service.list_catalog(db, company_id=company.id, limit=offers_limit, offset=0)
    return PublicCompanyDetail(
        **card.model_dump(),
        registration_date=company.registration_date,
        legal_form=company.legal_form,
        offers=[PublicOfferCard.model_validate(o) for o in offers],
        reviews=_reviews_out(db, company.id),
    )


# ── Market context ────────────────────────────────────────────────────────────


@router.get("/stats", response_model=PublicStatsOut, summary="Live platform figures")
def get_public_stats(db: Session = Depends(get_db)) -> PublicStatsOut:
    """GET /public/stats -- the hero strip and directory tile counts."""
    stats = public_market_service.platform_stats(db)

    def facets(rows: list[public_market_service.FacetRow]) -> list[PublicFacetOut]:
        return [
            PublicFacetOut(value=r.value, label=r.label, offer_count=r.offer_count)
            for r in rows
        ]

    return PublicStatsOut(
        offer_count=stats.offer_count,
        company_count=stats.company_count,
        country_count=stats.country_count,
        directory_counts=stats.directory_counts,
        countries=facets(stats.countries),
        incoterms=facets(stats.incoterms),
        companies=facets(stats.companies),
    )


@router.get("/prices", response_model=list[PublicQuoteOut], summary="Market price rail")
def list_public_prices(
    limit: int = Query(default=8, ge=1, le=40),
    lang: str = Query(default="ru", max_length=8),
    db: Session = Depends(get_db),
) -> list[PublicQuoteOut]:
    """GET /public/prices -- latest price per product with its last change."""
    return [
        PublicQuoteOut(
            product_id=row.product_id,
            code=row.code,
            label=row.label,
            price=row.price,
            currency=row.currency,
            unit=row.unit,
            observed_on=row.observed_on,
            change_pct=row.change_pct,
        )
        for row in public_market_service.latest_quotes(db, limit=limit, lang=lang)
    ]


@router.get(
    "/news",
    response_model=list[NewsArticleCard],
    summary="Published industry news",
)
def list_public_news(
    limit: int = Query(default=6, ge=1, le=40),
    days: int = Query(default=14, ge=1, le=30),
    lang: str | None = Query(default=None, max_length=8),
    db: Session = Depends(get_db),
) -> list[NewsArticleCard]:
    """GET /public/news -- the storefront's industry-news rail.

    Same `news_service` call the cabinet and Mini App make, so the anonymous rail
    cannot show an article the signed-in feed would not.
    """
    articles = news_service.list_news_articles(db, limit=limit, days=days, lang=lang)
    return [NewsArticleCard.model_validate(a) for a in articles]


# ── SEO ───────────────────────────────────────────────────────────────────────


@router.get("/sitemap", response_model=PublicSitemapOut, summary="URLs for sitemap.xml")
def get_sitemap(db: Session = Depends(get_db)) -> PublicSitemapOut:
    """GET /public/sitemap -- every crawlable detail URL with its last-modified.

    Returns paths, not absolute URLs: the origin is the portal's
    `PUBLIC_SITE_ORIGIN`, and baking a host in here would mean the API had to be
    redeployed to move the storefront to another domain.
    """
    entries: list[PublicSitemapEntry] = []

    offer_rows = public_market_service.sitemap_offer_rows(db, limit=_SITEMAP_MAX_URLS)
    entries.extend(
        PublicSitemapEntry(path=f"/market/{offer_id}", lastmod=updated)
        for offer_id, updated in offer_rows
    )

    company_rows = public_market_service.sitemap_company_rows(db, limit=_SITEMAP_MAX_URLS)
    slug_by_role = {str(role): slug for slug, role in DIRECTORY_SLUGS.items()}
    entries.extend(
        PublicSitemapEntry(path=f"/{slug_by_role[role]}/{company_id}", lastmod=verified_at)
        for company_id, role, verified_at in company_rows
        if role in slug_by_role
    )

    return PublicSitemapOut(
        entries=entries[:_SITEMAP_MAX_URLS],
        truncated=len(entries) > _SITEMAP_MAX_URLS,
    )
