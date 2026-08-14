"""Read-only aggregates for the anonymous marketplace storefront.

Everything here answers a question the logged-out home page asks and nothing
else does: the hero stat strip, the category tiles with their counts, the price
rail, and the id lists the sitemap is generated from.

No function in this module takes an account, and none of them can: the whole
point is that a crawler with no session gets the same answer a buyer does. The
visibility rules are inherited rather than restated -- offers come through
`offer_service`'s approved-only catalog query and companies through
`directory_service`'s verified-and-confirmed filter -- so widening what the
public sees is impossible from this file alone.
"""

from __future__ import annotations

import datetime
import decimal

import sqlalchemy as sa
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.domains.companies import directory as directory_service
from app.domains.companies.models import Company
from app.domains.marketplace.models import SellerOffer
from app.models.enums import CompanyStatus, SellerOfferStatus
from app.models.prices import PricePoint
from app.models.reference import Product


def _label(
    name_ru: object, name_uz: object, name_en: object, lang: str
) -> str:
    """Pick a product's display name for ``lang``, falling back to Russian.

    Takes the three columns rather than a `Product` because the aggregate queries
    select scalars, not entities -- loading a full row per tile just to read one
    string would undo the point of the GROUP BY.
    """
    if lang == "uz" and name_uz:
        return str(name_uz)
    if lang == "en" and name_en:
        return str(name_en)
    return str(name_ru)


def product_label(product: Product, lang: str) -> str:
    """The product's display name in ``lang``, falling back to Russian."""
    return _label(product.name_ru, product.name_uz, product.name_en, lang)


class CategoryRow:
    """One category tile: the product, its label, and how many offers it has."""

    def __init__(self, *, product_id: int, code: str, label: str, offer_count: int) -> None:
        self.product_id = product_id
        self.code = code
        self.label = label
        self.offer_count = offer_count


def category_tiles(db: Session, *, lang: str = "ru") -> list[CategoryRow]:
    """Active products with their approved-offer counts, busiest first.

    LEFT JOIN, not INNER: a catalog category with zero live offers still belongs
    on the storefront (it is a real product a buyer may search for, and an empty
    category page is a better answer than a 404). `offer_service.category_counts`
    is the INNER-JOIN twin used for the cabinet's filter chips, where a zero-count
    chip would just be a dead filter.
    """
    rows = (
        db.query(
            Product.id,
            Product.code,
            Product.name_ru,
            Product.name_uz,
            Product.name_en,
            sa.func.count(SellerOffer.id),
        )
        .outerjoin(
            SellerOffer,
            sa.and_(
                SellerOffer.product_id == Product.id,
                SellerOffer.status == SellerOfferStatus.approved,
            ),
        )
        .filter(Product.is_active.is_(True))
        .group_by(Product.id, Product.code, Product.name_ru, Product.name_uz, Product.name_en)
        .order_by(sa.func.count(SellerOffer.id).desc(), Product.sort_order.asc())
        .all()
    )
    return [
        CategoryRow(
            product_id=int(pid),
            code=str(code),
            label=_label(name_ru, name_uz, name_en, lang),
            offer_count=int(count),
        )
        for pid, code, name_ru, name_uz, name_en, count in rows
    ]


class FacetRow:
    """One option in a storefront filter dropdown, with how many offers it has."""

    def __init__(self, *, value: str, label: str, offer_count: int) -> None:
        self.value = value
        self.label = label
        self.offer_count = offer_count


class StatsRow:
    """The hero strip's figures plus the sidebar filters' option lists."""

    def __init__(
        self,
        *,
        offer_count: int,
        company_count: int,
        country_count: int,
        directory_counts: dict[str, int],
        countries: list[FacetRow],
        incoterms: list[FacetRow],
        companies: list[FacetRow],
    ) -> None:
        self.offer_count = offer_count
        self.company_count = company_count
        self.country_count = country_count
        self.directory_counts = directory_counts
        self.countries = countries
        self.incoterms = incoterms
        self.companies = companies


#: How many seller companies the "Производитель / Компания" dropdown offers.
#: A select is not a directory — past a screenful it stops being usable, and
#: /manufacturers is the surface for browsing all of them.
_MAX_COMPANY_FACETS = 50


def _column_facets[ColumnT](db: Session, column: InstrumentedAttribute[ColumnT]) -> list[FacetRow]:
    """GROUP BY one approved-offer column, busiest value first.

    Values come straight out of the catalog rather than from a static list, so a
    dropdown can never offer a filter that returns nothing. Generic over the
    column's Python type so a `str | None` column and an enum column both fit
    without widening to `Any` (which the strict gate rejects).
    """
    rows = (
        db.query(column, sa.func.count(SellerOffer.id))
        .filter(SellerOffer.status == SellerOfferStatus.approved, column.isnot(None))
        .group_by(column)
        .order_by(sa.func.count(SellerOffer.id).desc(), column.asc())
        .all()
    )
    return [
        FacetRow(value=str(value), label=str(value), offer_count=int(count))
        for value, count in rows
        if value is not None and str(value)
    ]


def _company_facets(db: Session) -> list[FacetRow]:
    """Seller companies that actually have approved offers, busiest first."""
    rows = (
        db.query(
            Company.id,
            Company.short_name,
            Company.legal_name,
            sa.func.count(SellerOffer.id),
        )
        .join(SellerOffer, SellerOffer.company_id == Company.id)
        .filter(
            SellerOffer.status == SellerOfferStatus.approved,
            Company.status == CompanyStatus.verified,
        )
        .group_by(Company.id, Company.short_name, Company.legal_name)
        .order_by(sa.func.count(SellerOffer.id).desc(), Company.id.asc())
        .limit(_MAX_COMPANY_FACETS)
        .all()
    )
    return [
        FacetRow(
            value=str(company_id),
            label=str(short_name or legal_name or company_id),
            offer_count=int(count),
        )
        for company_id, short_name, legal_name, count in rows
    ]


def platform_stats(db: Session) -> StatsRow:
    """Live counts for the hero strip, the directory tiles and the sidebar filters.

    Real figures, not the mockup's round numbers. A storefront that claims
    "20 000+ продуктов" over an empty catalog is the first thing a buyer checks
    and the first thing that costs trust.

    The filter option lists ride along here rather than on their own endpoint
    because the home page already prefetches `/public/stats` server-side — a
    separate `/public/facets` would add a round trip to the SSR render for data
    that is aggregated from the same table in the same request.
    """
    offer_count = (
        db.query(sa.func.count(SellerOffer.id))
        .filter(SellerOffer.status == SellerOfferStatus.approved)
        .scalar()
        or 0
    )
    company_count = (
        db.query(sa.func.count(Company.id))
        .filter(Company.status == CompanyStatus.verified)
        .scalar()
        or 0
    )
    # Countries the catalog actually ships from, not jurisdictions on file.
    country_count = (
        db.query(sa.func.count(sa.distinct(SellerOffer.country)))
        .filter(
            SellerOffer.status == SellerOfferStatus.approved,
            SellerOffer.country.isnot(None),
        )
        .scalar()
        or 0
    )
    directory_counts = {
        str(role): directory_service.count_by_role(db, role)
        for role in directory_service.PUBLIC_DIRECTORY_ROLES
    }
    return StatsRow(
        offer_count=int(offer_count),
        company_count=int(company_count),
        country_count=int(country_count),
        directory_counts=directory_counts,
        countries=_column_facets(db, SellerOffer.country),
        incoterms=_column_facets(db, SellerOffer.incoterms),
        companies=_company_facets(db),
    )


class QuoteRow:
    """One row of the price rail."""

    def __init__(
        self,
        *,
        product_id: int,
        code: str,
        label: str,
        price: decimal.Decimal,
        currency: str,
        unit: str,
        observed_on: datetime.date,
        change_pct: decimal.Decimal | None,
    ) -> None:
        self.product_id = product_id
        self.code = code
        self.label = label
        self.price = price
        self.currency = currency
        self.unit = unit
        self.observed_on = observed_on
        self.change_pct = change_pct


def latest_quotes(db: Session, *, limit: int = 8, lang: str = "ru") -> list[QuoteRow]:
    """Most recent price per product, with the change against the prior reading.

    `change_pct` is None rather than 0 when there is only one observation. A
    freshly-seeded product showing "0.0%" reads as a flat market; showing nothing
    reads as what it is, which is no history yet.
    """
    # Rank observations per product so "latest" and "the one before it" come out
    # of a single pass instead of a query per product.
    ranked = (
        sa.select(
            PricePoint.product_id,
            PricePoint.price_avg,
            PricePoint.currency,
            PricePoint.unit,
            PricePoint.observed_on,
            sa.func.row_number()
            .over(
                partition_by=PricePoint.product_id,
                order_by=(PricePoint.observed_on.desc(), PricePoint.id.desc()),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest = sa.orm.aliased(ranked, name="latest")
    prior = sa.orm.aliased(ranked, name="prior")

    rows = db.execute(
        sa.select(
            Product.id,
            Product.code,
            Product.name_ru,
            Product.name_uz,
            Product.name_en,
            latest.c.price_avg,
            latest.c.currency,
            latest.c.unit,
            latest.c.observed_on,
            prior.c.price_avg,
        )
        .select_from(latest)
        .join(Product, Product.id == latest.c.product_id)
        .outerjoin(
            prior, sa.and_(prior.c.product_id == latest.c.product_id, prior.c.rn == 2)
        )
        .where(latest.c.rn == 1, Product.is_active.is_(True))
        .order_by(Product.sort_order.asc(), Product.code.asc())
        .limit(limit)
    ).all()

    out: list[QuoteRow] = []
    for pid, code, name_ru, name_uz, name_en, price, currency, unit, observed_on, prev in rows:
        label = _label(name_ru, name_uz, name_en, lang)
        change: decimal.Decimal | None = None
        if prev is not None and prev != 0:
            change = ((price - prev) / prev * 100).quantize(decimal.Decimal("0.1"))
        out.append(
            QuoteRow(
                product_id=int(pid),
                code=str(code),
                label=label,
                price=price,
                currency=str(currency),
                unit=str(unit),
                observed_on=observed_on,
                change_pct=change,
            )
        )
    return out


def sitemap_offer_rows(db: Session, *, limit: int = 50_000) -> list[tuple[int, datetime.datetime | None]]:
    """`(offer_id, last_modified)` for every approved offer, newest first.

    `limit` is the sitemap protocol's 50 000-URL ceiling per file. It is a real
    cap, not a guess -- when the catalog outgrows it the generator needs a
    sitemap index, so the endpoint reports whether it truncated.
    """
    rows = (
        db.query(SellerOffer.id, SellerOffer.updated_at)
        .filter(SellerOffer.status == SellerOfferStatus.approved)
        .order_by(SellerOffer.published_at.desc().nullslast(), SellerOffer.id.desc())
        .limit(limit)
        .all()
    )
    return [(int(oid), updated) for oid, updated in rows]


def sitemap_company_rows(
    db: Session, *, limit: int = 50_000
) -> list[tuple[int, str, datetime.datetime | None]]:
    """`(company_id, role, last_modified)` for every listed company.

    A company confirmed as both a manufacturer and a trader appears in two
    directories and therefore has two URLs. Both are emitted; the page itself
    carries a canonical so the duplicate does not split its ranking.
    """
    out: list[tuple[int, str, datetime.datetime | None]] = []
    for role in directory_service.PUBLIC_DIRECTORY_ROLES:
        items, _ = directory_service.list_by_role(db, role=role, limit=limit, offset=0)
        out.extend((c.id, str(role), c.verified_at) for c in items)
    return out
