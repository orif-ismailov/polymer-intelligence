"""
DB-backed tests for cross-language catalog search (offer_service.list_catalog).

The bug this guards against: an offer listed under the Latin product code "PP" was
invisible when a buyer searched with the Cyrillic abbreviation "ПП" — the search only
looked at the offer's own free-text columns, never the linked Product's localized names
or the product_synonyms dictionary. list_catalog now resolves the query to product ids
via matching_product_ids, so a search in any supported language returns the linked offers.

Requires a live PostgreSQL test DB (same skip guard as test_relevance_service.py); runs
in CI where the Postgres service is available, skips locally otherwise.
"""

from __future__ import annotations

import contextlib
import decimal
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command as alembic_command

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
# Runs against a throwaway localhost test DB only. Accepts both the documented dev name
# ("test_polymer") and the CI service database ("polymer_intelligence_test") so this
# actually executes in CI's Postgres, while never touching a real/prod DB (the module
# fixture downgrades to base). Safe: prod URLs are not on localhost.
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and (
    "test_polymer" in _DB_URL or "polymer_intelligence_test" in _DB_URL
)

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Catalog search DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine():
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def seeded_catalog(engine):
    """Migrate + seed reference/synonyms, then insert one approved PP offer and one
    free-text-only offer. Yields (engine, pp_offer_id, freetext_offer_id)."""
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", _DB_URL)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")
    alembic_command.upgrade(alembic_cfg, "head")

    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.models.marketplace import Seller, SellerOffer  # noqa: PLC0415
    from app.models.reference import Product  # noqa: PLC0415
    from app.seed.seed_reference import seed_all  # noqa: PLC0415

    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        seed_all(session)  # products + synonyms
        session.commit()

        pp = session.query(Product).filter(Product.code == "PP").first()
        assert pp is not None, "seed must create the PP product"

        seller = Seller(telegram_user_id=987654, company_name="Search Co")
        session.add(seller)
        session.flush()

        pp_offer = SellerOffer(
            seller_id=seller.id,
            product_id=pp.id,          # linked by product_id; no product_text
            grade_text="T30S",
            qty_available=decimal.Decimal("100"),
            price=decimal.Decimal("1200"),
            status=SellerOfferStatus.approved,
            published_at=utcnow(),
        )
        freetext_offer = SellerOffer(
            seller_id=seller.id,
            product_text="EVA copolymer",  # not in the product catalog
            qty_available=decimal.Decimal("50"),
            price=decimal.Decimal("1500"),
            status=SellerOfferStatus.approved,
            published_at=utcnow(),
        )
        session.add_all([pp_offer, freetext_offer])
        session.commit()
        ids = (pp_offer.id, freetext_offer.id)

    yield engine, ids[0], ids[1]

    with contextlib.suppress(Exception):
        alembic_command.downgrade(alembic_cfg, "base")


@_requires_real_db
class TestCrossLanguageCatalogSearch:
    def _search(self, engine, q: str):
        from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

        from app.services import offer_service  # noqa: PLC0415

        with sessionmaker(bind=engine)() as session:
            return [o.id for o in offer_service.list_catalog(session, q=q)]

    @pytest.mark.parametrize(
        "term",
        [
            "ПП",            # Cyrillic abbreviation (the reported bug)
            "пп",            # lowercase
            " ПП ",          # padded
            "PP",            # Latin code
            "полипропилен",  # RU full name
            "Полипропилен",  # RU, capitalized
            "Polypropylene",  # EN name
            "Polipropilen",  # UZ/TR name
        ],
    )
    def test_pp_offer_found_in_every_language(self, seeded_catalog, term) -> None:
        engine, pp_id, _ = seeded_catalog
        assert pp_id in self._search(engine, term), f"'{term}' must return the PP offer"

    def test_freetext_offer_still_matches_directly(self, seeded_catalog) -> None:
        """A free-text-only offer (product_text) keeps matching on its own columns."""
        engine, _, freetext_id = seeded_catalog
        assert freetext_id in self._search(engine, "EVA")

    def test_unknown_term_returns_nothing(self, seeded_catalog) -> None:
        engine, pp_id, freetext_id = seeded_catalog
        results = self._search(engine, "цемент")  # not a polymer
        assert pp_id not in results and freetext_id not in results

    def test_synonym_match_does_not_leak_other_products(self, seeded_catalog) -> None:
        """'ПП' resolves to PP only — the EVA free-text offer is not swept in."""
        engine, pp_id, freetext_id = seeded_catalog
        results = self._search(engine, "ПП")
        assert pp_id in results
        assert freetext_id not in results
