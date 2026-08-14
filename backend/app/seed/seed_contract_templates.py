"""Contract template seed (R3 Stage B — TB1.1).

Seeds the initial supply-contract template (`SUPPLY_V1`). The body HTML lives in
`data/contract_templates/` and is uploaded to S3 (`body_storage_path`); the row is
inserted idempotently (`ON CONFLICT (code) DO NOTHING`).

WARNING: the bundled body is a DEV placeholder (lorem/структура). The production
contract text is supplied by the legal team and is a launch blocker (TB4.4) — swap
the file + bump `version` before go-live.

Usage:
    python -m app.seed.seed_contract_templates
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.domains.contracts.models import ContractTemplate
from app.services import storage_service

_DATA_DIR = Path(__file__).parent / "data" / "contract_templates"

_SUPPLY_V1_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "product",
        "qty",
        "unit",
        "price",
        "currency",
        "incoterms",
        "payment_terms",
        "delivery_window",
    ],
    "properties": {
        "product": {"type": "string", "title": "Товар"},
        "qty": {"type": "string", "title": "Количество"},
        "unit": {"type": "string", "title": "Ед. изм.", "enum": ["kg", "t", "pcs"]},
        "price": {"type": "string", "title": "Цена"},
        "currency": {"type": "string", "title": "Валюта", "enum": ["UZS", "USD", "EUR", "RUB", "CNY"]},
        "incoterms": {
            "type": "string",
            "title": "Incoterms",
            "enum": ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"],
        },
        "payment_terms": {"type": "string", "title": "Условия оплаты"},
        "delivery_window": {"type": "string", "title": "Срок поставки"},
        "special_conditions": {"type": "string", "title": "Особые условия"},
    },
}


def seed_contract_templates(db: Session | None = None) -> list[ContractTemplate]:
    """Seed the SUPPLY_V1 template (idempotent). Returns rows created this run."""
    own = db is None
    session = db or SessionLocal()
    created: list[ContractTemplate] = []
    try:
        existing = session.execute(
            select(ContractTemplate).where(ContractTemplate.code == "SUPPLY_V1")
        ).scalar_one_or_none()
        if existing is None:
            html = (_DATA_DIR / "supply_v1_ru.html").read_text(encoding="utf-8")
            path = storage_service.store_contract_template("SUPPLY_V1", 1, html)
            template = ContractTemplate(
                code="SUPPLY_V1",
                name_ru="Договор поставки (полимеры)",
                name_uz="Yetkazib berish shartnomasi (polimerlar)",
                name_en="Supply contract (polymers)",
                body_storage_path=path,
                variables_schema=_SUPPLY_V1_SCHEMA,
                version=1,
                is_active=True,
            )
            session.add(template)
            session.flush()
            created.append(template)
        if own:
            session.commit()
    finally:
        if own:
            session.close()
    return created


if __name__ == "__main__":  # pragma: no cover
    rows = seed_contract_templates()
    print(f"seed_contract_templates: created {len(rows)} template(s)")
