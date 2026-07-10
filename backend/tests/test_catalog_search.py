"""
Tests for cross-language catalog search (offer_service.list_catalog + matching_product_ids).

The bug this guards against: an offer listed under the Latin product code "PP" was
invisible when a buyer searched with the Cyrillic abbreviation "ПП" — the search only
looked at the offer's own free-text columns, never the linked Product's localized names
or the product_synonyms dictionary. list_catalog now resolves the query to product ids
via matching_product_ids, so a search in any supported language returns the linked offers.

Two layers:
  - TestMatchingProductIds — DB-free unit tests of the resolver control flow (run in CI).
  - TestCrossLanguageCatalogSearch — end-to-end SQL against a real localhost "test_polymer"
    DB (same skip guard as test_relevance_service.py; skips in CI and when unconfigured).
"""

from __future__ import annotations

import contextlib
import decimal
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command as alembic_command

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
# Same skip guard as test_relevance_service: a developer-provisioned localhost DB named
# "test_polymer". Intentionally NOT satisfied in CI (whose DB is polymer_intelligence_test
# AND whose conftest patch_env swaps DATABASE_URL for a placeholder), so this
# self-migrating fixture never runs against the CI/prod DB. The fix's control flow is
# covered DB-free by TestMatchingProductIds, which runs everywhere.
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Catalog search DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


# ── DB-free unit tests for the resolver logic (run everywhere, incl. CI) ────────


def _fake_db(product_rows, synonym_rows=None):
    """A MagicMock session whose two .query(...).filter(...) calls yield canned rows.

    matching_product_ids issues at most two queries — Product first, ProductSynonym
    second (only when the normalized term is >= 2 chars). Each returns an iterable of
    single-column rows, matching how the real ORM query is iterated as ``for (pid,) in``.
    """
    db = MagicMock()
    q_product = MagicMock()
    q_product.filter.return_value = product_rows
    queries = [q_product]
    if synonym_rows is not None:
        q_synonym = MagicMock()
        q_synonym.filter.return_value = synonym_rows
        queries.append(q_synonym)
    db.query.side_effect = queries
    return db


class TestMatchingProductIds:
    """offer_service.matching_product_ids control flow — no DB required."""

    def test_unions_and_dedups_product_and_synonym_hits(self) -> None:
        from app.services import offer_service  # noqa: PLC0415

        db = _fake_db([(1,), (2,)], [(2,), (3,)])  # 2 is a shared hit
        ids = offer_service.matching_product_ids(db, "полипропилен")
        assert sorted(ids) == [1, 2, 3]
        assert db.query.call_count == 2  # Product + ProductSynonym

    def test_empty_term_short_circuits_without_querying(self) -> None:
        from app.services import offer_service  # noqa: PLC0415

        db = MagicMock()
        assert offer_service.matching_product_ids(db, "   ") == []
        db.query.assert_not_called()

    def test_single_char_term_skips_synonym_query(self) -> None:
        """A 1-char term is too noisy for the synonym dictionary — only Product is queried."""
        from app.services import offer_service  # noqa: PLC0415

        db = _fake_db([(5,)])  # only the Product query is provided
        ids = offer_service.matching_product_ids(db, "п")
        assert ids == [5]
        assert db.query.call_count == 1  # synonym branch skipped (len(norm) < 2)

    def test_two_char_abbreviation_resolves_via_synonyms(self) -> None:
        """The reported case: "ПП" matches nothing by product name but resolves via synonyms."""
        from app.services import offer_service  # noqa: PLC0415

        db = _fake_db([], [(7,)])  # no name hit; synonym dictionary resolves it
        ids = offer_service.matching_product_ids(db, "ПП")
        assert ids == [7]
        assert db.query.call_count == 2


# ── End-to-end SQL against a real localhost test DB (dev-only; skips in CI) ──────


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
