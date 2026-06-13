"""
Reference data seed script.

Populates products, product_grades, and logs the synonyms dictionary.
Idempotent: uses INSERT ... ON CONFLICT DO NOTHING on natural unique constraints,
so re-running creates no duplicates.

Seed scope (dev-spec §9 E1):
- products: polymer product types with RU/UZ names
- product_grades: UZ-producer grades (Shurtan GCC, Uz-Kor)
- synonyms: loaded and logged; DB write deferred until the synonyms table
  is created in a future migration (schema-contract constraint: no new table
  without a migration — Rule 4 applied at plan time, see seed/__init__.py)

Usage:
    python -m app.seed.seed_reference

Idempotency contract:
    Running this function twice on the same migrated database:
    - Inserts the expected rows on first run
    - Inserts 0 additional rows on second run
    - Never raises an error on second run
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Paths to data files
_DATA_DIR = Path(__file__).parent / "data"
_PRODUCTS_FILE = _DATA_DIR / "products.json"
_GRADES_FILE = _DATA_DIR / "grades.json"
_SYNONYMS_FILE = _DATA_DIR / "synonyms.json"


def _load_json(path: Path) -> Any:
    """Load and return JSON from a file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_products(session: Session) -> int:
    """Upsert polymer products idempotently.

    Uses INSERT ... ON CONFLICT (code) DO NOTHING so re-runs are safe.
    Returns the number of rows inserted (0 on re-run).
    """
    products = _load_json(_PRODUCTS_FILE)
    inserted = 0
    for p in products:
        result = session.execute(
            text(
                """
                INSERT INTO products (code, name_ru, name_uz, category, sort_order, is_active)
                VALUES (:code, :name_ru, :name_uz, :category, :sort_order, true)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "code": p["code"],
                "name_ru": p["name_ru"],
                "name_uz": p.get("name_uz"),
                "category": p.get("category", "polymer"),
                "sort_order": p.get("sort_order", 0),
            },
        )
        inserted += result.rowcount
    session.flush()
    logger.info("seed.products_seeded", extra={"inserted": inserted, "total": len(products)})
    return inserted


def seed_grades(session: Session) -> int:
    """Upsert product grades idempotently.

    Uses INSERT ... ON CONFLICT (product_id, code) DO NOTHING.
    Returns the number of rows inserted (0 on re-run).
    """
    grades = _load_json(_GRADES_FILE)
    inserted = 0

    for g in grades:
        # Resolve product_id by code
        row = session.execute(
            text("SELECT id FROM products WHERE code = :code"),
            {"code": g["product_code"]},
        ).fetchone()

        if row is None:
            logger.warning(
                "seed.grade_product_not_found",
                extra={"product_code": g["product_code"], "grade_code": g["code"]},
            )
            continue

        product_id = row[0]
        result = session.execute(
            text(
                """
                INSERT INTO product_grades (product_id, code, producer, description)
                VALUES (:product_id, :code, :producer, :description)
                ON CONFLICT (product_id, code) DO NOTHING
                """
            ),
            {
                "product_id": product_id,
                "code": g["code"],
                "producer": g.get("producer"),
                "description": g.get("description"),
            },
        )
        inserted += result.rowcount

    session.flush()
    logger.info("seed.grades_seeded", extra={"inserted": inserted, "total": len(grades)})
    return inserted


def load_synonyms() -> dict[str, list[str]]:
    """Load the synonyms dictionary from synonyms.json.

    Returns a dict mapping product_code -> list of synonym strings.
    Phase 1: synonyms are loaded here but not written to DB because
    the synonyms table is not yet in the schema. The data is available
    in memory for the UZEX relevance filter to use (Phase 2 will add
    the table and a migration that seeds from this file).
    """
    data = _load_json(_SYNONYMS_FILE)
    # Remove _comment key if present
    return {k: v for k, v in data.items() if not k.startswith("_")}


def seed_all(session: Session) -> dict[str, int]:
    """Run all seed operations idempotently.

    Returns counts of rows inserted per entity type.
    """
    products_inserted = seed_products(session)
    grades_inserted = seed_grades(session)

    # Load synonyms (logs count; DB write deferred to Phase 2 migration)
    synonyms = load_synonyms()
    total_synonyms = sum(len(v) for v in synonyms.values())
    logger.info(
        "seed.synonyms_loaded",
        extra={
            "product_count": len(synonyms),
            "synonym_count": total_synonyms,
            "note": "DB write deferred — synonyms table created in Phase 2",
        },
    )

    session.commit()

    return {
        "products": products_inserted,
        "grades": grades_inserted,
        "synonyms_loaded": total_synonyms,  # loaded but not written to DB yet
    }


if __name__ == "__main__":
    import sys
    import os
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)

    from sqlalchemy import create_engine  # noqa: PLC0415

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        try:
            from app.core.config import settings  # noqa: PLC0415

            db_url = settings.DATABASE_URL
        except Exception:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            sys.exit(1)

    engine = create_engine(db_url)
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        counts = seed_all(session)

    print(f"Seed complete: {counts}")
    sys.exit(0)
