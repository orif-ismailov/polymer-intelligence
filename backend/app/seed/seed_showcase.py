"""
Showcase seed — turns an empty dev environment into a platform that looks lived-in.

Populates every surface the portal and the dashboard render: verified companies with
people and bank details, a stocked market, RFQs and quotes, inquiries, deals across
the whole lifecycle, e-signed contracts, escrow, lab orders, samples, a 4-month price
history, counterparties, favourites, notifications and alerts.

Content lives in `showcase_data.py`; this module is only the insert mechanics.

    docker compose -f deploy/docker-compose.dev.yml exec api python -m app.seed.seed_showcase
    python -m app.seed.seed_showcase --reset     # wipe previous showcase rows first

Idempotent: keyed off the sentinel tax_id of the first showcase company. Re-running
without --reset is a no-op.

WARNING: dev/demo only. Never run against production.
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import hashlib
import json
import random
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_pii
from app.core.db import SessionLocal
from app.seed.showcase_data import (
    APP_SETTINGS,
    BANKS,
    COMPANIES,
    GRADE_SPECS,
    PEOPLE,
    PRODUCTS,
)

_UTC = datetime.UTC
#: Fixed seed so a re-run after --reset reproduces the same demo, byte for byte.
RNG = random.Random(20260730)

#: Presence of this tax_id means the showcase is already seeded.
SENTINEL_TAX_ID = COMPANIES[0]["tax_id"]

_D = decimal.Decimal


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=_UTC)


NOW = _now()


def _ago(days: float = 0, hours: float = 0) -> datetime.datetime:
    return NOW - datetime.timedelta(days=days, hours=hours)


def _money(value: float) -> decimal.Decimal:
    return _D(str(round(value, 2)))


def _qty(value: float) -> decimal.Decimal:
    return _D(str(round(value, 3)))


# ══════════════════════════════════════════════════════════════════════════════
# Purge
# ══════════════════════════════════════════════════════════════════════════════

#: Child-before-parent order. Everything here is demo/test content: the signal
#: pipeline tables (raw_items, signals, parse_runs, reports, fx_rates) are NOT
#: touched — those hold genuinely ingested market data worth keeping.
_PURGE_ORDER = [
    # Service-track threads (manufacturer / lab / logistics) and factory RFQs
    # arrived after the original list; without them the purge dies on the first
    # FK into `companies`.
    "manufacturer_messages",
    "manufacturer_threads",
    "lab_request_messages",
    "lab_request_threads",
    "lab_requests",
    "logistics_request_messages",
    "logistics_request_threads",
    "logistics_requests",
    "factory_rfq_documents",
    "factory_rfqs",
    "company_reviews",
    "substance_suggestions",
    "deliveries",
    "deal_messages",
    "deal_documents",
    "deal_status_history",
    "escrow_payments",
    "provider_events",
    "sample_requests",
    "lab_orders",
    "lab_partners",
    "rfq_responses",
    "rfq_push_log",
    "offer_favorites",
    "offer_requests",
    "seller_offer_files",
    "request_status_history",
    "request_files",
    "portal_notifications",
    "contract_signatures",
    "signature_evidence",
    "registry_snapshots",
    "verification_checks",
    "verification_documents",
    "verification_cases",
    "company_licenses",
    "company_bank_accounts",
    "company_business_roles",
    "company_members",
    "company_person_data",
    "inventory_items",
    "partner_suppliers",
    "price_points",
    "alerts",
    "alert_rules",
]


def purge(db: Session) -> None:
    """Delete demo content so a re-seed starts clean.

    `deals`/`contracts`/`requests`/`seller_offers`/`companies`/`user_accounts` are
    deleted last and explicitly, because they are self-referencing through
    `deals.contract_id` and `contracts.offer_id`.
    """
    for table in _PURGE_ORDER:
        db.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 — fixed literal list

    # Break the deals↔contracts cycle before deleting either side.
    db.execute(sa.text("UPDATE deals SET contract_id = NULL"))
    db.execute(sa.text("DELETE FROM deals"))
    db.execute(sa.text("DELETE FROM contracts"))
    db.execute(sa.text("DELETE FROM requests"))
    db.execute(sa.text("DELETE FROM seller_offers"))
    # The intel seeder links sellers/clients to companies, so they go first.
    db.execute(sa.text("DELETE FROM sellers"))
    db.execute(sa.text("DELETE FROM clients"))
    db.execute(sa.text("DELETE FROM companies"))
    db.execute(sa.text("DELETE FROM user_accounts"))
    # Classified intel signals may point at demo counterparties; signals are
    # pipeline data and stay, so detach rather than delete.
    db.execute(sa.text("UPDATE signals SET counterparty_id = NULL WHERE counterparty_id IS NOT NULL"))
    db.execute(sa.text("DELETE FROM counterparties"))
    # Numbering restarts with the data, so DEAL-2026-000001 is the first deal again.
    for seq in ("deal_seq", "lab_order_seq", "request_seq"):
        db.execute(sa.text(f"DROP SEQUENCE IF EXISTS {seq}_{NOW.year}"))
    print("purged previous showcase rows")


# ══════════════════════════════════════════════════════════════════════════════
# 1 — People, companies, verification
# ══════════════════════════════════════════════════════════════════════════════


def seed_companies(db: Session) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Insert accounts, companies, members, roles, banks, verification, registry.

    Returns (company key → company_id, company key → [account_id]).
    """
    company_ids: dict[str, int] = {}
    account_ids: dict[str, list[int]] = {}

    for idx, spec in enumerate(COMPANIES):
        key = str(spec["key"])
        people = PEOPLE[key]
        created = _ago(days=300 - idx * 7, hours=RNG.randrange(0, 20))

        # ── accounts ──────────────────────────────────────────────────────────
        ids: list[int] = []
        for phone, name, _role, lang in people:
            account_id = db.execute(
                sa.text(
                    """
                    INSERT INTO user_accounts (phone, name, language, status,
                                               created_at, last_login_at)
                    VALUES (:phone, :name, :lang, 'active', :created, :seen)
                    RETURNING id
                    """
                ),
                {
                    "phone": phone,
                    "name": name,
                    "lang": lang,
                    "created": created,
                    "seen": _ago(days=RNG.randrange(0, 6), hours=RNG.randrange(0, 22)),
                },
            ).scalar_one()
            ids.append(account_id)
        account_ids[key] = ids

        # ── company ───────────────────────────────────────────────────────────
        status = str(spec["status"])
        verified_at = created + datetime.timedelta(days=RNG.randrange(3, 12)) if status == "verified" else None
        company_id = db.execute(
            sa.text(
                """
                INSERT INTO companies (jurisdiction, tax_id, legal_name, short_name,
                                       legal_form, legal_address, director_name,
                                       registration_date, registry_status, status,
                                       verified_at, reverification_due_at,
                                       created_by_user_account_id, created_at, updated_at,
                                       identity_locked, logistics_profile,
                                       laboratory_profile)
                VALUES ('UZ', :tax_id, :legal_name, :short_name, :legal_form, :address,
                        :director, :reg_date, :registry_status, :status, :verified_at,
                        :reverify, :created_by, :created, :updated, :locked,
                        CAST(:logistics_profile AS jsonb),
                        CAST(:laboratory_profile AS jsonb))
                RETURNING id
                """
            ),
            {
                "tax_id": spec["tax_id"],
                "legal_name": spec["legal_name"],
                "short_name": spec["short_name"],
                "legal_form": spec["legal_form"],
                "address": spec["address"],
                "director": spec["director"],
                "reg_date": spec["reg_date"],
                "registry_status": "Действующее" if status != "liquidated" else "Ликвидировано",
                "status": status,
                "verified_at": verified_at,
                "reverify": (verified_at + datetime.timedelta(days=365)) if verified_at else None,
                "created_by": ids[0],
                "created": created,
                "updated": verified_at or created,
                "locked": status == "verified",
                # CAST(:name AS jsonb), not `:name::jsonb` — a `::` in a text()
                # string collides with SQLAlchemy's bind-parameter parsing and
                # fails at execute time with a syntax error on the colon.
                "logistics_profile": (
                    json.dumps(spec["logistics_profile"], ensure_ascii=False)
                    if spec.get("logistics_profile")
                    else None
                ),
                "laboratory_profile": (
                    json.dumps(spec["laboratory_profile"], ensure_ascii=False)
                    if spec.get("laboratory_profile")
                    else None
                ),
            },
        ).scalar_one()
        company_ids[key] = company_id

        # ── members ───────────────────────────────────────────────────────────
        for (_phone, _name, member_role, _lang), account_id in zip(people, ids, strict=True):
            db.execute(
                sa.text(
                    """
                    INSERT INTO company_members (company_id, user_account_id, member_role,
                                                 status, invited_by_user_account_id, created_at)
                    VALUES (:company_id, :account_id, :role, 'active', :invited_by, :created)
                    """
                ),
                {
                    "company_id": company_id,
                    "account_id": account_id,
                    "role": member_role,
                    "invited_by": None if member_role == "owner" else ids[0],
                    "created": created,
                },
            )

        # ── declared business roles (confirmed once the company is verified) ──
        for role in spec["roles"]:  # type: ignore[union-attr]
            db.execute(
                sa.text(
                    """
                    INSERT INTO company_business_roles (company_id, role, status,
                                                        confirmed_by, created_at)
                    VALUES (:company_id, :role, :status, :confirmed_by, :created)
                    """
                ),
                {
                    "company_id": company_id,
                    "role": role,
                    "status": "confirmed" if status == "verified" else "declared",
                    "confirmed_by": 1 if status == "verified" else None,
                    "created": created,
                },
            )

        # ── bank account ──────────────────────────────────────────────────────
        if status in ("verified", "pending_verification"):
            mfo, bank_name = BANKS[idx % len(BANKS)]
            number = f"2020{RNG.randrange(10**15, 10**16 - 1)}"
            db.execute(
                sa.text(
                    """
                    INSERT INTO company_bank_accounts (company_id, bank_mfo, bank_name,
                                                       account_number_enc, account_last4,
                                                       currency, status, verification_method,
                                                       verified_at, verified_by, created_at)
                    VALUES (:company_id, :mfo, :bank_name, :enc, :last4, 'UZS', :status,
                            :method, :verified_at, :verified_by, :created)
                    """
                ),
                {
                    "company_id": company_id,
                    "mfo": mfo,
                    "bank_name": bank_name,
                    "enc": encrypt_pii(number),
                    "last4": number[-4:],
                    "status": "verified" if status == "verified" else "pending",
                    "method": "document" if status == "verified" else None,
                    "verified_at": verified_at,
                    "verified_by": 1 if status == "verified" else None,
                    "created": created,
                },
            )

        _seed_verification_case(db, company_id, ids[0], status, created, verified_at)

    print(f"companies: {len(company_ids)} (+ {sum(len(v) for v in account_ids.values())} accounts)")
    return company_ids, account_ids


_CHECK_TYPES = [
    "tax_id_format",
    "bank_requisites",
    "documents_complete",
    "gov_registry",
    "vat_status",
    "eimzo_signature",
    "manual_kyb",
]


def _seed_verification_case(
    db: Session,
    company_id: int,
    account_id: int,
    company_status: str,
    created: datetime.datetime,
    verified_at: datetime.datetime | None,
) -> None:
    """A verification case whose checks match the company's outcome.

    `draft` companies get no case at all — that is the state before submission.
    """
    if company_status == "draft":
        return

    case_status = {
        "verified": "approved",
        "pending_verification": "pending_review",
        "rejected": "rejected",
    }[company_status]
    submitted = created + datetime.timedelta(days=1)
    decided = verified_at if company_status == "verified" else (
        submitted + datetime.timedelta(days=4) if company_status == "rejected" else None
    )

    case_id = db.execute(
        sa.text(
            """
            INSERT INTO verification_cases (company_id, case_type, status, submitted_at,
                                            decided_at, decided_by, decision_note, created_at)
            VALUES (:company_id, 'onboarding', :status, :submitted, :decided, :decided_by,
                    :note, :created)
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "status": case_status,
            "submitted": submitted,
            "decided": decided,
            "decided_by": 1 if decided else None,
            "note": {
                "verified": "Все проверки пройдены, учредительные документы соответствуют данным ЕГРЮЛ.",
                "rejected": "Расхождение между ИНН в заявке и данными государственного реестра. Повторная подача возможна после исправления.",
                "pending_verification": None,
            }[company_status],
            "created": created,
        },
    ).scalar_one()

    for check_type in _CHECK_TYPES:
        if company_status == "verified":
            check_status = "passed"
        elif company_status == "rejected":
            check_status = "failed" if check_type == "gov_registry" else "passed"
        else:  # pending_review — automated checks done, manual review outstanding
            check_status = "pending" if check_type == "manual_kyb" else "passed"

        result = {
            "tax_id_format": {"valid": check_status != "failed", "length": 9},
            "bank_requisites": {"mfo_known": True, "matches_company": check_status != "failed"},
            "documents_complete": {"required": 3, "provided": 3},
            "gov_registry": {
                "found": check_status != "failed",
                "registry_status": "Действующее" if check_status != "failed" else None,
                "reason": None if check_status != "failed" else "ИНН не найден в реестре",
            },
            "vat_status": {"registered": True, "vat_code": f"3{company_id:08d}"},
            "eimzo_signature": {"verified": check_status == "passed", "cert_valid": True},
            "manual_kyb": {"reviewer": "analyst@polymer.uz"} if check_status == "passed" else {},
        }[check_type]

        db.execute(
            sa.text(
                """
                INSERT INTO verification_checks (case_id, check_type, status, result,
                                                 attempts, started_at, finished_at)
                VALUES (:case_id, :check_type, :status, CAST(:result AS jsonb), 1,
                        :started, :finished)
                """
            ),
            {
                "case_id": case_id,
                "check_type": check_type,
                "status": check_status,
                "result": json.dumps(result, ensure_ascii=False),
                "started": submitted,
                "finished": None if check_status == "pending" else submitted + datetime.timedelta(minutes=3),
            },
        )

    # Documents backing the case (bytes are written by the media step).
    for kind in ("registration_certificate", "director_id", "bank_letter"):
        db.execute(
            sa.text(
                """
                INSERT INTO verification_documents (company_id, case_id, kind, storage_path,
                                                    mime_type, size_bytes, sha256,
                                                    uploaded_by_user_account_id, status,
                                                    reviewed_by, reviewed_at, created_at)
                VALUES (:company_id, :case_id, :kind, :path, 'application/pdf', :size,
                        :sha, :uploader, :status, :reviewed_by, :reviewed_at, :created)
                """
            ),
            {
                "company_id": company_id,
                "case_id": case_id,
                "kind": kind,
                "path": f"verification/{company_id}/{kind}.pdf",
                "size": RNG.randrange(180_000, 900_000),
                "sha": hashlib.sha256(f"{company_id}:{kind}".encode()).hexdigest(),
                "uploader": account_id,
                "status": "accepted" if company_status == "verified" else "pending_review",
                "reviewed_by": 1 if company_status == "verified" else None,
                "reviewed_at": verified_at,
                "created": submitted,
            },
        )

    # An append-only registry snapshot is the evidence behind the gov_registry check.
    if company_status != "pending_verification":
        db.execute(
            sa.text(
                """
                INSERT INTO registry_snapshots (company_id, kind, source, provider, payload,
                                                raw_status, note, created_by, fetched_at, created_at)
                VALUES (:company_id, 'company', 'manual', 'egrpo.stat.uz', CAST(:payload AS jsonb),
                        :raw_status, :note, 1, :fetched, :fetched)
                """
            ),
            {
                "company_id": company_id,
                "payload": json.dumps(
                    {
                        "found": company_status == "verified",
                        "registry_status": "Действующее" if company_status == "verified" else "Не найдено",
                        "checked_via": "Открытый сервис ЕГРПО",
                    },
                    ensure_ascii=False,
                ),
                "raw_status": "Действующее" if company_status == "verified" else "Не найдено",
                "note": "Проверено оператором по открытому реестру, приложен снимок экрана.",
                "fetched": submitted + datetime.timedelta(hours=2),
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2 — The market: offers
# ══════════════════════════════════════════════════════════════════════════════

#: Companies that publish offers.
_SELLER_KEYS = [
    "shurtan", "uzkor", "jizzakh", "navoiyazot",
    "polimer_savdo", "ca_polymers", "turon_kimyo", "silk_road", "oriental_chem",
    "termez_pack", "angren_recycling", "zarafshan",
]

_INCOTERMS = ["EXW", "FCA", "CPT", "DAP", "CIF"]

#: Non-approved listings, so the moderation queue and a seller's own drafts are
#: demonstrable rather than theoretical. (offer index -> status)
_OFFER_STATUS_OVERRIDES = {
    3: "pending_moderation",
    11: "pending_moderation",
    19: "draft",
    27: "pending_moderation",
    35: "archived",
    43: "draft",
    51: "rejected",
    59: "archived",
}


def seed_offers(
    db: Session, companies: dict[str, int], accounts: dict[str, list[int]]
) -> list[dict[str, object]]:
    """Publish the catalogue. Returns a light record per offer for later wiring."""
    offers: list[dict[str, object]] = []
    index = 0

    for key in _SELLER_KEYS:
        spec = next(c for c in COMPANIES if c["key"] == key)
        company_id = companies[key]
        account_id = accounts[key][0]
        city = str(spec["city"])
        wanted = set(spec["products"])  # type: ignore[arg-type]
        candidates = [g for g in GRADE_SPECS if g["product_id"] in wanted]
        # A producer lists only what it actually makes — Shurtan offering Uz-Kor's
        # EP548R would be the first thing anyone in this market spotted as fake.
        # Traders and distributors resell anything, so they keep the full set.
        if spec.get("makes"):
            candidates = [g for g in candidates if g["manufacturer"] == spec["makes"]]

        for grade in candidates:
            product_id = int(grade["product_id"])  # type: ignore[call-overload]
            code, substance_id, hs_code, cas, base = PRODUCTS[product_id]

            # Producers sell at the low end of the band; traders carry a margin.
            archetype = str(spec["archetype"])
            margin = {"producer": 0.0, "trader": 0.055, "converter": 0.03}.get(archetype, 0.03)
            price = base * (1 + margin) + RNG.randrange(-45, 60)

            availability = "in_stock" if RNG.random() < 0.72 else "on_order"
            sale_mode = (
                "from_stock" if availability == "in_stock"
                else RNG.choice(["made_to_order", "recurring_contract"])
            )
            qty = RNG.choice([60, 80, 120, 150, 200, 250, 300, 400, 500, 750, 1000])
            published = _ago(days=RNG.randrange(1, 150), hours=RNG.randrange(0, 23))

            status = _OFFER_STATUS_OVERRIDES.get(index, "approved")
            # An unverified company may not have live listings.
            if str(spec["status"]) != "verified" and status == "approved":
                status = "pending_moderation"

            lab_verified = status == "approved" and RNG.random() < 0.28
            samples = RNG.random() < 0.45

            offer_id = db.execute(
                sa.text(
                    """
                    INSERT INTO seller_offers (
                        product_id, grade_text, polymer_type, qty_available, qty_unit,
                        price, currency, incoterms, warehouse_city, country, min_order_qty,
                        description, status, moderated_by, moderation_note, published_at,
                        created_at, updated_at, availability, company_id,
                        created_by_user_account_id, lead_time_days, sale_mode,
                        accepts_rfq, accepts_contract, accepts_escrow, substance_id,
                        cas_number, hs_code, compliance_level, compliance_ok,
                        compliance_checked_at, samples_available, sample_price,
                        sample_dispatch_days, lab_verified, manufacturer,
                        key_properties, applications)
                    VALUES (
                        :product_id, :grade, :ptype, :qty, 'MT',
                        :price, 'USD', :incoterms, :city, 'UZ', :moq,
                        :description, :status, :moderated_by, :moderation_note, :published,
                        :created, :updated, :availability, :company_id,
                        :account_id, :lead_time, :sale_mode,
                        true, :accepts_contract, :accepts_escrow, :substance_id,
                        :cas, :hs, 'free', true,
                        :checked, :samples, :sample_price,
                        :sample_days, :lab_verified, :manufacturer,
                        CAST(:properties AS jsonb), CAST(:applications AS jsonb))
                    RETURNING id
                    """
                ),
                {
                    "product_id": product_id,
                    "grade": grade["grade"],
                    "ptype": code,
                    "qty": _qty(qty) if availability == "in_stock" else None,
                    "price": _money(price),
                    "incoterms": RNG.choice(_INCOTERMS),
                    "city": city,
                    "moq": _qty(RNG.choice([5, 10, 20, 25, 40])),
                    "description": grade["desc"],
                    "status": status,
                    "moderated_by": 2 if status in ("approved", "rejected") else None,
                    "moderation_note": (
                        "Отклонено: не приложен паспорт качества на партию."
                        if status == "rejected" else None
                    ),
                    "published": published if status == "approved" else None,
                    "checked": published,
                    "created": published - datetime.timedelta(days=2),
                    "updated": published,
                    "availability": availability,
                    "company_id": company_id,
                    "account_id": account_id,
                    "lead_time": (
                        RNG.choice([3, 5, 7, 10, 14, 21]) if availability == "on_order" else None
                    ),
                    "sale_mode": sale_mode,
                    "accepts_contract": RNG.random() < 0.75,
                    "accepts_escrow": RNG.random() < 0.55,
                    "substance_id": substance_id,
                    "cas": cas,
                    "hs": hs_code,
                    "samples": samples,
                    "sample_price": _money(RNG.choice([12, 15, 18, 25])) if samples else None,
                    "sample_days": RNG.choice([2, 3, 5, 7]) if samples else None,
                    "lab_verified": lab_verified,
                    "manufacturer": grade["manufacturer"],
                    "properties": json.dumps(grade["properties"], ensure_ascii=False),
                    "applications": json.dumps(grade["applications"], ensure_ascii=False),
                },
            ).scalar_one()

            offers.append(
                {
                    "id": offer_id,
                    "company_key": key,
                    "company_id": company_id,
                    "account_id": account_id,
                    "product_id": product_id,
                    "grade": grade["grade"],
                    "price": price,
                    "status": status,
                    "city": city,
                    "lab_verified": lab_verified,
                    "samples": samples,
                }
            )
            index += 1

    approved = sum(1 for o in offers if o["status"] == "approved")
    print(f"offers: {len(offers)} ({approved} live in the market)")
    return offers


# ══════════════════════════════════════════════════════════════════════════════
# 3 — Demand: RFQs, supplier quotes, per-offer inquiries
# ══════════════════════════════════════════════════════════════════════════════

_BUYER_KEYS = [
    "tashkent_plastic", "andijan_pipe", "fergana_film", "bukhara_sacks",
    "namangan_house", "samarkand_pet", "chirchiq_cable", "nukus_agrofilm",
    "olmaliq_pipe", "termez_pack", "urgench_irrigation", "qarshi_profile",
]

_RFQ_COMMENTS = [
    "Требуется поставка на условиях отсрочки платежа 30 дней. Объём законтрактуем на квартал.",
    "Нужен паспорт качества на каждую партию. Отгрузка автотранспортом до склада покупателя.",
    "Рассмотрим предложения только от производителей или официальных дистрибьюторов.",
    "Планируем регулярные закупки. Просим указать цену при годовом контракте.",
    "Срочная потребность — остановка линии. Готовы рассмотреть предоплату.",
    "Требуется соответствие пищевому регламенту, приложите сертификат.",
    "Просим указать сроки отгрузки и наличие на складе в Ташкенте.",
    "Интересует поставка железнодорожным транспортом, вагонная норма.",
]

_REQUIRED_DOCS = [
    ["tds", "coa"],
    ["tds", "coa", "origin"],
    ["coa"],
    ["tds", "sds", "coa", "origin"],
]


def seed_requests(
    db: Session,
    companies: dict[str, int],
    accounts: dict[str, list[int]],
    offers: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Buyer RFQs + the supplier quotes answering them."""
    requests: list[dict[str, object]] = []
    statuses = ["new", "viewed", "in_progress", "offer_sent", "matched", "closed", "cancelled"]

    for i in range(26):
        key = _BUYER_KEYS[i % len(_BUYER_KEYS)]
        spec = next(c for c in COMPANIES if c["key"] == key)
        company_id = companies[key]
        account_id = accounts[key][0]
        product_id = RNG.choice(list(spec["products"])) if spec["products"] else RNG.randrange(1, 9)  # type: ignore[arg-type]
        code, _sub, _hs, _cas, base = PRODUCTS[product_id]

        created = _ago(days=RNG.randrange(1, 120), hours=RNG.randrange(0, 23))
        status = statuses[i % len(statuses)]
        volume = RNG.choice([25, 50, 60, 100, 150, 200, 300, 500])
        target = base * RNG.uniform(0.94, 1.02)

        request_id = db.execute(
            sa.text(
                """
                INSERT INTO requests (number, product_id, grade_text, polymer_type, volume,
                                      volume_unit, target_price, currency, incoterms,
                                      destination_country, port_or_city, desired_date,
                                      validity_days, urgency, comment, status, assigned_to,
                                      ai, created_at, updated_at, company_name, contact_name,
                                      phone, legal_address, company_id,
                                      created_by_user_account_id, required_docs, visibility)
                VALUES (:number, :product_id, :grade, :ptype, :volume, 'MT', :target, 'USD',
                        :incoterms, 'UZ', :city, :desired, :validity, :urgency, :comment,
                        :status, :assigned, CAST(:ai AS jsonb), :created, :updated,
                        :company_name, :contact, :phone, :address, :company_id,
                        :account_id, CAST(:docs AS jsonb), :visibility)
                RETURNING id
                """
            ),
            {
                "number": f"REQ-{created.strftime('%Y-%m-%d')}-{i + 1:05d}",
                "product_id": product_id,
                "grade": RNG.choice([g["grade"] for g in GRADE_SPECS if g["product_id"] == product_id] or [None]),
                "ptype": code,
                "volume": _qty(volume),
                "target": _money(target),
                "incoterms": RNG.choice(["DAP", "CPT", "EXW", "CIF"]),
                "city": spec["city"],
                "desired": (created + datetime.timedelta(days=RNG.randrange(14, 60))).date(),
                "validity": RNG.choice([14, 21, 30, 45]),
                "urgency": RNG.choice(["low", "medium", "high"]),
                "comment": RNG.choice(_RFQ_COMMENTS),
                "status": status,
                "assigned": RNG.choice([2, 3]) if status not in ("new",) else None,
                "ai": json.dumps(
                    {
                        "match_count": RNG.randrange(2, 9),
                        "demand_level": RNG.choice(["low", "normal", "high"]),
                        "price_position": RNG.choice(["below_market", "at_market", "above_market"]),
                        "recommendation": (
                            "Целевая цена ниже рынка на 3–5%. Рекомендуем расширить круг поставщиков "
                            "или допустить альтернативную марку."
                        ),
                    },
                    ensure_ascii=False,
                ),
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(0, 4)),
                "company_name": spec["legal_name"],
                "contact": PEOPLE[key][0][1],
                "phone": PEOPLE[key][0][0],
                "address": spec["address"],
                "company_id": company_id,
                "account_id": account_id,
                "docs": json.dumps(RNG.choice(_REQUIRED_DOCS)),
                "visibility": RNG.choice(["verified_only", "verified_only", "all"]),
            },
        ).scalar_one()

        # Status history so the timeline on the request page is populated.
        prior = "new"
        stamp = created
        for step in statuses[: statuses.index(status) + 1][1:]:
            stamp = stamp + datetime.timedelta(hours=RNG.randrange(4, 40))
            db.execute(
                sa.text(
                    """
                    INSERT INTO request_status_history (request_id, from_status, to_status,
                                                        changed_by, comment, created_at)
                    VALUES (:request_id, :from_status, :to_status, :by, :comment, :created)
                    """
                ),
                {
                    "request_id": request_id,
                    "from_status": prior,
                    "to_status": step,
                    "by": RNG.choice([2, 3]),
                    "comment": None,
                    "created": stamp,
                },
            )
            prior = step

        requests.append(
            {
                "id": request_id,
                "company_key": key,
                "company_id": company_id,
                "account_id": account_id,
                "product_id": product_id,
                "volume": volume,
                "status": status,
                "created": created,
            }
        )

    # ── Supplier quotes against the live RFQs ────────────────────────────────
    quote_count = 0
    for req in requests:
        if req["status"] in ("new", "cancelled"):
            continue
        candidates = [
            o for o in offers
            if o["status"] == "approved"
            and o["product_id"] == req["product_id"]
            and o["company_id"] != req["company_id"]
        ]
        RNG.shuffle(candidates)
        # `uq_rfq_response_active` allows one live quote per (request, company), so a
        # supplier listing two grades of the same polymer still answers only once.
        sellers: list[dict[str, object]] = []
        seen_companies: set[int] = set()
        for offer in candidates:
            company_id = int(offer["company_id"])  # type: ignore[call-overload]
            if company_id in seen_companies:
                continue
            seen_companies.add(company_id)
            sellers.append(offer)

        for rank, offer in enumerate(sellers[: RNG.randrange(2, 5)]):
            resp_status = (
                "accepted" if (req["status"] == "matched" and rank == 0)
                else "not_selected" if req["status"] in ("matched", "closed")
                else "submitted"
            )
            db.execute(
                sa.text(
                    """
                    INSERT INTO rfq_responses (request_id, company_id,
                                               created_by_user_account_id, price, currency,
                                               qty, qty_unit, incoterms, lead_time_days,
                                               comment, status, created_at, updated_at)
                    VALUES (:request_id, :company_id, :account_id, :price, 'USD', :qty, 'MT',
                            :incoterms, :lead_time, :comment, :status, :created, :created)
                    """
                ),
                {
                    "request_id": req["id"],
                    "company_id": offer["company_id"],
                    "account_id": offer["account_id"],
                    "price": _money(float(offer["price"]) * RNG.uniform(0.97, 1.04)),  # type: ignore[arg-type]
                    "qty": _qty(float(req["volume"])),  # type: ignore[arg-type]
                    "incoterms": RNG.choice(["DAP", "CPT", "EXW", "FCA"]),
                    "lead_time": RNG.choice([3, 5, 7, 10, 14]),
                    "comment": RNG.choice(
                        [
                            "Готовы отгрузить со склада в течение недели. Оплата по факту отгрузки.",
                            "Цена действительна 5 банковских дней. Возможна отсрочка при контракте на квартал.",
                            "Отгрузка партиями по 20 тонн. Паспорт качества на каждую партию.",
                            "Предлагаем альтернативную марку с аналогичным ПТР, цена ниже на 2%.",
                        ]
                    ),
                    "status": resp_status,
                    "created": req["created"] + datetime.timedelta(hours=RNG.randrange(3, 60)),  # type: ignore[operator]
                },
            )
            quote_count += 1

    print(f"requests: {len(requests)} RFQs, {quote_count} supplier quotes")
    return requests


def seed_inquiries(
    db: Session,
    companies: dict[str, int],
    accounts: dict[str, list[int]],
    offers: list[dict[str, object]],
) -> int:
    """Per-offer buyer inquiries (the marketplace's other demand channel)."""
    live = [o for o in offers if o["status"] == "approved"]
    made = 0
    for i in range(34):
        offer = RNG.choice(live)
        key = _BUYER_KEYS[i % len(_BUYER_KEYS)]
        if companies[key] == offer["company_id"]:
            continue
        status = ["pending", "approved", "approved", "rejected"][i % 4]
        created = _ago(days=RNG.randrange(1, 90), hours=RNG.randrange(0, 23))
        db.execute(
            sa.text(
                """
                INSERT INTO offer_requests (offer_id, quantity, qty_unit, target_price,
                                            currency, message, status, moderated_by,
                                            moderation_note, reviewed_at, forwarded_at,
                                            created_at, updated_at, seller_notified,
                                            company_id, created_by_user_account_id)
                VALUES (:offer_id, :qty, 'MT', :target, 'USD', :message, :status,
                        :moderated_by, :note, :reviewed, :forwarded, :created, :created,
                        :notified, :company_id, :account_id)
                """
            ),
            {
                "offer_id": offer["id"],
                "qty": _qty(RNG.choice([10, 20, 25, 40, 60, 100])),
                "target": _money(float(offer["price"]) * RNG.uniform(0.93, 1.0)),  # type: ignore[arg-type]
                "message": RNG.choice(
                    [
                        "Здравствуйте! Подтвердите, пожалуйста, наличие и сроки отгрузки.",
                        "Интересует объём на пробную партию. Возможна ли отсрочка платежа?",
                        "Просим выставить счёт на указанный объём. Самовывоз со склада.",
                        "Нужен паспорт качества и сертификат происхождения. Цена договорная при объёме от 100 т.",
                        "Рассматриваем долгосрочное сотрудничество. Какие условия при годовом контракте?",
                    ]
                ),
                "status": status,
                "moderated_by": 2 if status != "pending" else None,
                "note": "Не указан контакт для связи." if status == "rejected" else None,
                "reviewed": created + datetime.timedelta(hours=6) if status != "pending" else None,
                "forwarded": created + datetime.timedelta(hours=7) if status == "approved" else None,
                "created": created,
                "notified": status == "approved",
                "company_id": companies[key],
                "account_id": accounts[key][0],
            },
        )
        made += 1

    # Favourites — the heart on the market cards.
    for key in _BUYER_KEYS:
        account_id = accounts[key][0]
        for offer in RNG.sample(live, RNG.randrange(2, 6)):
            db.execute(
                sa.text(
                    """
                    INSERT INTO offer_favorites (user_account_id, offer_id, created_at)
                    VALUES (:account_id, :offer_id, :created)
                    ON CONFLICT (user_account_id, offer_id) DO NOTHING
                    """
                ),
                {
                    "account_id": account_id,
                    "offer_id": offer["id"],
                    "created": _ago(days=RNG.randrange(1, 60)),
                },
            )

    print(f"inquiries: {made} (+ favourites)")
    return made


# ══════════════════════════════════════════════════════════════════════════════
# 4 — Deal lifecycle: contracts, deals, escrow, delivery
# ══════════════════════════════════════════════════════════════════════════════

#: The whole status machine, weighted so the "healthy pipeline" reads as real:
#: most deals have completed, a few are live, one is cancelled and one disputed.
_DEAL_PLAN: list[tuple[str, int]] = [
    ("completed", 7),
    ("delivered", 2),
    ("shipped", 2),
    ("paid_escrow", 2),
    ("payment_pending", 2),
    ("contract_signed", 2),
    ("contract_pending", 2),
    ("negotiation", 3),
    ("cancelled", 1),
    ("disputed", 1),
]

#: Order the machine actually walks, so history rows are a plausible path.
_DEAL_PATH = [
    "negotiation", "contract_pending", "contract_signed", "payment_pending",
    "paid_escrow", "shipped", "delivered", "completed",
]

_CHAT = [
    ("buyer", "Добрый день! Готовы начать по объёму 100 тонн. Подтвердите, пожалуйста, цену."),
    ("seller", "Здравствуйте! Цена подтверждена, действительна до конца недели. Отгрузка со склада в Ташкенте."),
    ("buyer", "Принято. Прошу подготовить проект договора поставки."),
    ("seller", "Договор сформирован и отправлен на подписание через ЭЦП."),
    ("buyer", "Подписали со своей стороны. Реквизиты для оплаты прежние?"),
    ("seller", "Да, реквизиты не менялись. После поступления средств на эскроу-счёт начинаем отгрузку."),
    ("buyer", "Оплата проведена, приложил платёжное поручение."),
    ("seller", "Средства видим. Отгрузка завтра, транспорт подан. Товарно-транспортную накладную приложу."),
    ("buyer", "Груз принят, расхождений нет. Спасибо за оперативность!"),
]

#: How much of `_CHAT` a deal in each status has plausibly said. The messages are
#: ordered to mirror the machine, so this is simply where each status stops talking.
_CHAT_DEPTH: dict[str, int] = {
    "negotiation": 2,
    "contract_pending": 4,
    "contract_signed": 5,
    "payment_pending": 6,
    "paid_escrow": 7,
    "shipped": 8,
    "delivered": 9,
    "completed": 9,
    "cancelled": 3,
    "disputed": 8,
}


def seed_deals(
    db: Session,
    companies: dict[str, int],
    accounts: dict[str, list[int]],
    offers: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Deals, their contracts, e-signatures, escrow, chat and documents."""
    live = [o for o in offers if o["status"] == "approved"]
    plan = [status for status, count in _DEAL_PLAN for _ in range(count)]
    RNG.shuffle(plan)

    deals: list[dict[str, object]] = []
    contract_n = 0

    for i, status in enumerate(plan):
        offer = live[i % len(live)]
        buyer_key = _BUYER_KEYS[i % len(_BUYER_KEYS)]
        if companies[buyer_key] == offer["company_id"]:
            buyer_key = _BUYER_KEYS[(i + 1) % len(_BUYER_KEYS)]

        buyer_id = companies[buyer_key]
        seller_id = int(offer["company_id"])  # type: ignore[call-overload]
        buyer_account = accounts[buyer_key][0]
        seller_account = int(offer["account_id"])  # type: ignore[call-overload]

        qty = RNG.choice([40, 60, 100, 120, 150, 200])
        unit_price = float(offer["price"])  # type: ignore[arg-type]
        amount = qty * unit_price
        opened = _ago(days=RNG.randrange(5, 200), hours=RNG.randrange(0, 23))
        path = _DEAL_PATH[: _DEAL_PATH.index(status) + 1] if status in _DEAL_PATH else ["negotiation"]

        # ── contract (exists from contract_pending onward) ───────────────────
        contract_id = None
        reached_contract = status in _DEAL_PATH and _DEAL_PATH.index(status) >= 1
        if reached_contract or status == "disputed":
            contract_n += 1
            signed = status in _DEAL_PATH and _DEAL_PATH.index(status) >= 2
            contract_status = "active" if signed else "pending_signatures"
            sent_at = opened + datetime.timedelta(days=1)
            activated = sent_at + datetime.timedelta(days=1) if signed else None
            variables = {
                "product": f"{PRODUCTS[int(offer['product_id'])][0]} {offer['grade']}",  # type: ignore[call-overload]
                "qty": str(qty),
                "unit": "t",
                "price": f"{unit_price:.2f}",
                "currency": "USD",
                "incoterms": RNG.choice(["EXW", "FCA", "CPT", "DAP"]),
                "payment_terms": RNG.choice(
                    [
                        "100% предоплата на эскроу-счёт",
                        "50% предоплата, 50% по факту отгрузки",
                        "Оплата в течение 10 банковских дней с даты поставки",
                    ]
                ),
                "delivery_window": "в течение 14 календарных дней с даты подписания",
                "special_conditions": "Паспорт качества на каждую партию. Тара — биг-бэг 1000 кг.",
            }
            contract_id = db.execute(
                sa.text(
                    """
                    INSERT INTO contracts (template_id, template_version, initiator_company_id,
                                           counterparty_company_id, offer_id, title, variables,
                                           generated_document_path, document_sha256, status,
                                           created_by_user_account_id, sent_at, activated_at,
                                           created_at, updated_at)
                    VALUES (1, 1, :initiator, :counterparty, :offer_id, :title,
                            CAST(:variables AS jsonb), :path, :sha, :status, :created_by,
                            :sent_at, :activated, :created, :updated)
                    RETURNING id
                    """
                ),
                {
                    "initiator": buyer_id,
                    "counterparty": seller_id,
                    "offer_id": offer["id"],
                    "title": (
                        f"Договор поставки № ДП-{opened.year}-{contract_n:04d} "
                        f"({PRODUCTS[int(offer['product_id'])][0]} {offer['grade']})"  # type: ignore[call-overload]
                    ),
                    "variables": json.dumps(variables, ensure_ascii=False),
                    "path": f"contracts/seed-{contract_n:04d}/contract_v1.pdf",
                    "sha": hashlib.sha256(f"contract:{contract_n}".encode()).hexdigest(),
                    "status": contract_status,
                    "created_by": buyer_account,
                    "sent_at": sent_at,
                    "activated": activated,
                    "created": opened,
                    "updated": activated or sent_at,
                },
            ).scalar_one()

            if signed:
                for company_id, account_id, person in (
                    (buyer_id, buyer_account, PEOPLE[buyer_key][0][1]),
                    (seller_id, seller_account, PEOPLE[str(offer["company_key"])][0][1]),
                ):
                    evidence_id = db.execute(
                        sa.text(
                            """
                            INSERT INTO signature_evidence (company_id, user_account_id, purpose,
                                                            challenge, pkcs7_storage_path,
                                                            pkcs7_sha256, cert_subject,
                                                            signed_at, created_at)
                            VALUES (:company_id, :account_id, 'contract_sign', :challenge,
                                    :path, :sha, CAST(:subject AS jsonb), :signed, :signed)
                            RETURNING id
                            """
                        ),
                        {
                            "company_id": company_id,
                            "account_id": account_id,
                            "challenge": hashlib.sha256(
                                f"challenge:{contract_n}:{company_id}".encode()
                            ).hexdigest(),
                            "path": f"evidence/eimzo/{company_id}/seed-{contract_n:04d}.p7s",
                            "sha": hashlib.sha256(f"p7s:{contract_n}:{company_id}".encode()).hexdigest(),
                            "subject": json.dumps(
                                {
                                    "CN": person,
                                    "O": next(
                                        c["legal_name"] for c in COMPANIES
                                        if companies[str(c["key"])] == company_id
                                    ),
                                    "serialNumber": f"{RNG.randrange(10**11, 10**12)}",
                                    "issuer": "E-IMZO Root CA",
                                },
                                ensure_ascii=False,
                            ),
                            "signed": activated,
                        },
                    ).scalar_one()
                    db.execute(
                        sa.text(
                            """
                            INSERT INTO contract_signatures (contract_id, company_id,
                                                             signed_by_user_account_id,
                                                             signature_evidence_id, signed_at)
                            VALUES (:contract_id, :company_id, :account_id, :evidence_id, :signed)
                            """
                        ),
                        {
                            "contract_id": contract_id,
                            "company_id": company_id,
                            "account_id": account_id,
                            "evidence_id": evidence_id,
                            "signed": activated,
                        },
                    )

        # ── deal ─────────────────────────────────────────────────────────────
        deal_id = db.execute(
            sa.text(
                """
                INSERT INTO deals (number, buyer_company_id, seller_company_id, request_id,
                                   offer_id, contract_id, status, amount, currency,
                                   created_by_user_account_id, cancelled_reason,
                                   created_at, updated_at)
                VALUES (:number, :buyer, :seller, NULL, :offer_id, :contract_id, :status,
                        :amount, 'USD', :created_by, :cancelled, :created, :updated)
                RETURNING id
                """
            ),
            {
                "number": f"DEAL-{opened.year}-{i + 1:06d}",
                "buyer": buyer_id,
                "seller": seller_id,
                "offer_id": offer["id"],
                "contract_id": contract_id,
                "status": status,
                "amount": _money(amount),
                "created_by": buyer_account,
                "cancelled": (
                    "Покупатель отозвал заявку: изменилась производственная программа."
                    if status == "cancelled" else None
                ),
                "created": opened,
                "updated": opened + datetime.timedelta(days=len(path) * 2),
            },
        ).scalar_one()

        # ── status history along the path actually walked ────────────────────
        stamp = opened
        prior: str | None = None
        walk = path if status not in ("cancelled", "disputed") else ["negotiation", "contract_pending", status]
        for step in walk:
            db.execute(
                sa.text(
                    """
                    INSERT INTO deal_status_history (deal_id, from_status, to_status,
                                                     actor_kind, actor_id, reason, created_at)
                    VALUES (:deal_id, :from_status, :to_status, :actor_kind, :actor_id,
                            :reason, :created)
                    """
                ),
                {
                    "deal_id": deal_id,
                    "from_status": prior,
                    "to_status": step,
                    "actor_kind": "buyer" if step in ("negotiation", "contract_pending", "delivered") else "seller",
                    "actor_id": buyer_account if step in ("negotiation", "contract_pending", "delivered") else seller_account,
                    "reason": (
                        "Расхождение по массе нетто при приёмке — 1,2 т. Ожидается решение сторон."
                        if step == "disputed" else None
                    ),
                    "created": stamp,
                },
            )
            prior = step
            stamp = stamp + datetime.timedelta(days=RNG.randrange(1, 6), hours=RNG.randrange(0, 20))

        # ── trade-room chat ──────────────────────────────────────────────────
        # Depth is pinned to the status, not to the length of the path: derived from
        # the path it ran ahead of reality, so a deal sitting at "contract signed"
        # showed messages about payment already made and a truck already loaded.
        depth = _CHAT_DEPTH.get(status, 2)
        msg_stamp = opened
        for side, body in _CHAT[:depth]:
            msg_stamp = msg_stamp + datetime.timedelta(hours=RNG.randrange(2, 26))
            db.execute(
                sa.text(
                    """
                    INSERT INTO deal_messages (deal_id, author_account_id, author_company_id,
                                               body, created_at)
                    VALUES (:deal_id, :account_id, :company_id, :body, :created)
                    """
                ),
                {
                    "deal_id": deal_id,
                    "account_id": buyer_account if side == "buyer" else seller_account,
                    "company_id": buyer_id if side == "buyer" else seller_id,
                    "body": body,
                    "created": msg_stamp,
                },
            )

        # ── documents ────────────────────────────────────────────────────────
        docs: list[tuple[str, str]] = []
        if contract_id:
            docs.append(("contract", "Договор поставки (подписан ЭЦП).pdf"))
        if status in ("paid_escrow", "shipped", "delivered", "completed", "disputed"):
            docs.append(("invoice", "Счёт-фактура.pdf"))
        if status in ("shipped", "delivered", "completed", "disputed"):
            docs.append(("transport", "Товарно-транспортная накладная.pdf"))
        if status in ("delivered", "completed"):
            docs.append(("lab_passport", "Паспорт качества партии.pdf"))
        for kind, name in docs:
            db.execute(
                sa.text(
                    """
                    INSERT INTO deal_documents (deal_id, kind, file_name, mime_type, size_bytes,
                                                storage_path, sha256, uploaded_by_user_account_id,
                                                uploaded_by_company_id, created_at)
                    VALUES (:deal_id, :kind, :name, 'application/pdf', :size, :path, :sha,
                            :account_id, :company_id, :created)
                    """
                ),
                {
                    "deal_id": deal_id,
                    "kind": kind,
                    "name": name,
                    "size": RNG.randrange(120_000, 1_400_000),
                    "path": f"deals/{deal_id}/documents/{kind}.pdf",
                    "sha": hashlib.sha256(f"{deal_id}:{kind}".encode()).hexdigest(),
                    "account_id": seller_account if kind != "contract" else buyer_account,
                    "company_id": seller_id if kind != "contract" else buyer_id,
                    "created": opened + datetime.timedelta(days=RNG.randrange(2, 12)),
                },
            )

        # ── escrow ───────────────────────────────────────────────────────────
        if status in ("payment_pending", "paid_escrow", "shipped", "delivered", "completed", "disputed"):
            escrow_status = (
                "pending" if status == "payment_pending"
                else "released" if status == "completed"
                else "funded"
            )
            funded_at = opened + datetime.timedelta(days=4) if escrow_status != "pending" else None
            released_at = opened + datetime.timedelta(days=12) if escrow_status == "released" else None
            db.execute(
                sa.text(
                    """
                    INSERT INTO escrow_payments (deal_id, amount, currency, status, mode,
                                                 provider_ref, funded_at, released_at,
                                                 funded_marked_by, released_marked_by, note,
                                                 created_at, updated_at)
                    VALUES (:deal_id, :amount, 'USD', :status, 'stub', :ref, :funded, :released,
                            :funded_by, :released_by, :note, :created, :updated)
                    """
                ),
                {
                    "deal_id": deal_id,
                    "amount": _money(amount),
                    "status": escrow_status,
                    "ref": f"ESC-{opened.year}-{deal_id:06d}",
                    "funded": funded_at,
                    "released": released_at,
                    "funded_by": buyer_account if funded_at else None,
                    "released_by": buyer_account if released_at else None,
                    "note": "Оплата подтверждена банком-партнёром." if funded_at else None,
                    "created": opened + datetime.timedelta(days=3),
                    "updated": released_at or funded_at or opened + datetime.timedelta(days=3),
                },
            )

        deals.append(
            {
                "id": deal_id,
                "status": status,
                "buyer_key": buyer_key,
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "buyer_account": buyer_account,
                "seller_account": seller_account,
                "offer_id": offer["id"],
                "amount": amount,
                "opened": opened,
            }
        )

    print(f"deals: {len(deals)} across {len(_DEAL_PLAN)} statuses, {contract_n} contracts")
    return deals


# ══════════════════════════════════════════════════════════════════════════════
# 5 — Laboratory: partners, orders, sample exchange
# ══════════════════════════════════════════════════════════════════════════════

_LAB_PARTNERS = [
    (
        "Испытательный центр «Central Polymer Lab»",
        {"contact": "Гулнора Каримова", "phone": "+998712001133", "email": "lab@cptl.uz",
         "address": "г. Ташкент, ул. Дурмон йули, 33"},
        "Аккредитация O'zAK. Полный цикл: ПТР, плотность, ИК-спектроскопия, ДСК.",
    ),
    (
        "Лаборатория «UzStandard Test»",
        {"contact": "Бахром Азимов", "phone": "+998712445566", "email": "info@uzstandard-test.uz",
         "address": "г. Ташкент, ул. Фаробий, 333А"},
        "Государственный центр стандартизации. Сертификация соответствия и протоколы испытаний.",
    ),
    (
        "Лаборатория полимеров «Ferghana Analytics»",
        {"contact": "Мадина Юлдашева", "phone": "+998732221010", "email": "lab@ferghana-analytics.uz",
         "address": "г. Фергана, ул. Мустакиллик, 88"},
        "Региональная лаборатория. Экспресс-анализ ПТР и плотности, срок 2 рабочих дня.",
    ),
]

_LAB_PLAN = ["done", "done", "done", "in_analysis", "in_analysis", "sample_awaited",
             "accepted", "submitted", "submitted", "rejected"]


def seed_labs(
    db: Session,
    companies: dict[str, int],
    accounts: dict[str, list[int]],
    offers: list[dict[str, object]],
    deals: list[dict[str, object]],
) -> None:
    """Lab partner directory, orders across the whole machine, and sample requests."""
    partner_ids = []
    for name, contacts, note in _LAB_PARTNERS:
        partner_ids.append(
            db.execute(
                sa.text(
                    """
                    INSERT INTO lab_partners (name, contacts, company_id, note, is_active,
                                              created_at, updated_at)
                    VALUES (:name, CAST(:contacts AS jsonb), :company_id, :note, true,
                            :created, :created)
                    RETURNING id
                    """
                ),
                {
                    "name": name,
                    "contacts": json.dumps(contacts, ensure_ascii=False),
                    "company_id": companies.get("cptl_lab") if "Central" in name else None,
                    "note": note,
                    "created": _ago(days=RNG.randrange(120, 300)),
                },
            ).scalar_one()
        )

    live = [o for o in offers if o["status"] == "approved"]
    for i, status in enumerate(_LAB_PLAN):
        offer = live[(i * 5) % len(live)]
        key = str(offer["company_key"])
        created = _ago(days=RNG.randrange(3, 120), hours=RNG.randrange(0, 20))
        done = status == "done"

        # `done` requires a result file — attach it to the offer, which is also what
        # flips the gold "Laboratory verified" badge in the market.
        result_file_id = None
        if done:
            result_file_id = db.execute(
                sa.text(
                    """
                    INSERT INTO seller_offer_files (offer_id, kind, file_name, mime_type,
                                                    size_bytes, storage_path, created_at)
                    VALUES (:offer_id, 'lab_passport', :name, 'application/pdf', :size,
                            :path, :created)
                    RETURNING id
                    """
                ),
                {
                    "offer_id": offer["id"],
                    "name": f"Протокол испытаний {offer['grade']}.pdf",
                    "size": RNG.randrange(200_000, 800_000),
                    "path": f"offers/{offer['id']}/lab-result-{i}.pdf",
                    "created": created + datetime.timedelta(days=6),
                },
            ).scalar_one()
            db.execute(
                sa.text("UPDATE seller_offers SET lab_verified = true WHERE id = :id"),
                {"id": offer["id"]},
            )

        db.execute(
            sa.text(
                """
                INSERT INTO lab_orders (number, company_id, created_by_user_account_id,
                                        offer_id, substance_id, sample_volume, comment,
                                        status, lab_partner_id, result_offer_file_id,
                                        operator_note, rejected_reason, handled_by,
                                        completed_at, created_at, updated_at)
                VALUES (:number, :company_id, :account_id, :offer_id, :substance_id,
                        :volume, :comment, :status, :partner_id, :result_file_id,
                        :operator_note, :rejected, :handled_by, :completed, :created, :updated)
                """
            ),
            {
                "number": f"LAB-{created.year}-{i + 1:06d}",
                "company_id": offer["company_id"],
                "account_id": offer["account_id"],
                "offer_id": offer["id"],
                "substance_id": PRODUCTS[int(offer["product_id"])][1],  # type: ignore[call-overload]
                "volume": RNG.choice(["500 г", "1 кг", "2 кг"]),
                "comment": (
                    f"Просим подтвердить ПТР и плотность по марке {offer['grade']} "
                    "для включения в каталог."
                ),
                "status": status,
                "partner_id": RNG.choice(partner_ids) if status not in ("submitted",) else None,
                "result_file_id": result_file_id,
                "operator_note": (
                    "Образец получен, передан в лабораторию." if status in ("in_analysis", "done") else None
                ),
                "rejected": (
                    "Объём образца недостаточен для полного цикла испытаний."
                    if status == "rejected" else None
                ),
                "handled_by": 2 if status != "submitted" else None,
                "completed": created + datetime.timedelta(days=6) if done else None,
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(1, 8)),
            },
        )
        del key

    # ── Sample exchange between buyer and seller ─────────────────────────────
    sample_plan = ["received", "received", "sent", "sent", "accepted", "accepted",
                   "requested", "requested", "declined", "rejected_by_buyer"]
    with_samples = [o for o in live if o["samples"]] or live
    # `uq_sample_request_active` allows one live request per (offer, buyer company),
    # so the pair is chosen explicitly rather than left to modular arithmetic.
    used_pairs: set[tuple[int, int]] = set()
    for i, status in enumerate(sample_plan):
        offer = with_samples[i % len(with_samples)]
        buyer_key = _BUYER_KEYS[i % len(_BUYER_KEYS)]
        for step in range(len(_BUYER_KEYS)):
            candidate = _BUYER_KEYS[(i + step) % len(_BUYER_KEYS)]
            pair = (int(offer["id"]), companies[candidate])  # type: ignore[call-overload]
            if companies[candidate] != offer["company_id"] and pair not in used_pairs:
                buyer_key = candidate
                used_pairs.add(pair)
                break
        buyer_spec = next(c for c in COMPANIES if c["key"] == buyer_key)
        created = _ago(days=RNG.randrange(2, 70), hours=RNG.randrange(0, 20))
        accepted = status in ("accepted", "sent", "received", "rejected_by_buyer")
        sent = status in ("sent", "received", "rejected_by_buyer")
        received = status in ("received", "rejected_by_buyer")

        db.execute(
            sa.text(
                """
                INSERT INTO sample_requests (offer_id, buyer_company_id, seller_company_id,
                                             created_by_user_account_id, status, qty,
                                             delivery_address, courier, tracking_ref,
                                             decline_reason, accepted_at, sent_at, received_at,
                                             created_at, updated_at)
                VALUES (:offer_id, :buyer, :seller, :account_id, :status, :qty, :address,
                        :courier, :tracking, :decline, :accepted, :sent, :received,
                        :created, :updated)
                """
            ),
            {
                "offer_id": offer["id"],
                "buyer": companies[buyer_key],
                "seller": offer["company_id"],
                "account_id": accounts[buyer_key][0],
                "status": status,
                "qty": RNG.choice(["500 г", "1 кг", "2 кг"]),
                "address": f"{buyer_spec['address']} (склад, приёмка 09:00–17:00)",
                "courier": RNG.choice(["BTS Express", "Uzbekistan Post", "FARGO", None]) if sent else None,
                "tracking": f"UZ{RNG.randrange(10**8, 10**9)}" if sent else None,
                "decline": (
                    "Марка снята с производства, образцы отсутствуют."
                    if status == "declined" else None
                ),
                "accepted": created + datetime.timedelta(days=1) if accepted else None,
                "sent": created + datetime.timedelta(days=3) if sent else None,
                "received": created + datetime.timedelta(days=6) if received else None,
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(1, 8)),
            },
        )

    print(f"labs: {len(partner_ids)} partners, {len(_LAB_PLAN)} orders, {len(sample_plan)} sample requests")
    del deals


# ══════════════════════════════════════════════════════════════════════════════
# 6 — Market intelligence: price history, counterparties, inventory, suppliers
# ══════════════════════════════════════════════════════════════════════════════


def seed_market_intel(db: Session, offers: list[dict[str, object]]) -> None:
    """A 4-month daily price series per product/market — the charts' fuel."""
    days = 120
    rows = 0
    for product_id, (code, _sub, _hs, _cas, base) in PRODUCTS.items():
        for market, spread in (("UZEX", 0.0), ("UZ", 0.018)):
            # A random walk with occasional shocks. The amplitude matters: the price
            # chart is drawn from a zero baseline, so a ±2% band renders as a flat
            # line across the whole card. Real polymer prices move on feedstock and
            # plant outages, and this band (roughly ±15%) reads that way at 30 days.
            level = base * (1 - 0.06)
            for d in range(days):
                observed = (NOW - datetime.timedelta(days=days - d)).date()
                level += base * RNG.uniform(-0.012, 0.013)
                if RNG.random() < 0.06:  # feedstock move / outage
                    level += base * RNG.uniform(-0.045, 0.05)
                level = max(base * 0.84, min(base * 1.19, level))
                avg = level * (1 + spread)
                db.execute(
                    sa.text(
                        """
                        INSERT INTO price_points (kind, source_id, product_id, market, currency,
                                                  unit, price_avg, price_min, price_max,
                                                  volume_total, deals_count, observed_on, created_at)
                        VALUES ('deal_avg', 1, :product_id, :market, 'USD', 'MT', :avg, :pmin,
                                :pmax, :volume, :deals, :observed, :created)
                        """
                    ),
                    {
                        "product_id": product_id,
                        "market": market,
                        "avg": _money(avg),
                        "pmin": _money(avg * 0.972),
                        "pmax": _money(avg * 1.031),
                        "volume": _qty(RNG.randrange(120, 1900)),
                        "deals": RNG.randrange(2, 18),
                        "observed": observed,
                        "created": NOW - datetime.timedelta(days=days - d),
                    },
                )
                rows += 1
        del code

    # Counterparties — the intel side's canonical trading names.
    for spec in COMPANIES:
        role = (
            "producer" if spec["archetype"] == "producer"
            else "trader" if spec["archetype"] == "trader"
            else "buyer"
        )
        db.execute(
            sa.text(
                """
                INSERT INTO counterparties (canonical_name, role, country, tax_id, notes,
                                            first_seen_at, created_at)
                VALUES (:name, :role, 'UZ', :tax_id, :notes, :seen, :seen)
                """
            ),
            {
                "name": spec["short_name"],
                "role": role,
                "tax_id": spec["tax_id"],
                "notes": f"{spec['legal_name']}, {spec['city']}.",
                "seen": _ago(days=RNG.randrange(120, 340)),
            },
        )

    # Own inventory + partner supplier book (the sourcing screens).
    for i, grade in enumerate(GRADE_SPECS[:12]):
        product_id = int(grade["product_id"])  # type: ignore[call-overload]
        db.execute(
            sa.text(
                """
                INSERT INTO inventory_items (product_id, grade_text, qty_on_hand, qty_unit,
                                             cost_price, currency, warehouse_city,
                                             created_at, updated_at)
                VALUES (:product_id, :grade, :qty, 'MT', :cost, 'USD', :city, :created, :created)
                """
            ),
            {
                "product_id": product_id,
                "grade": grade["grade"],
                "qty": _qty(RNG.choice([12, 24, 40, 60, 85, 120, 180])),
                "cost": _money(PRODUCTS[product_id][4] * RNG.uniform(0.95, 1.02)),
                "city": RNG.choice(["Ташкент", "Самарканд", "Андижан", "Бухара"]),
                "created": _ago(days=RNG.randrange(10, 120)),
            },
        )
        del i

    for spec in COMPANIES:
        if spec["archetype"] not in ("producer", "trader"):
            continue
        for product_id in list(spec["products"])[:3]:  # type: ignore[arg-type]
            db.execute(
                sa.text(
                    """
                    INSERT INTO partner_suppliers (name, product_id, grade_text,
                                                   indicative_price, currency, lead_time_days,
                                                   incoterms, notes, created_at, updated_at)
                    VALUES (:name, :product_id, :grade, :price, 'USD', :lead, :incoterms,
                            :notes, :created, :created)
                    """
                ),
                {
                    "name": spec["short_name"],
                    "product_id": product_id,
                    "grade": next(
                        (g["grade"] for g in GRADE_SPECS if g["product_id"] == product_id), None
                    ),
                    "price": _money(PRODUCTS[int(product_id)][4] * RNG.uniform(0.98, 1.06)),
                    "lead": RNG.choice([3, 5, 7, 10, 14, 21]),
                    "incoterms": RNG.choice(["EXW", "FCA", "CPT", "DAP"]),
                    "notes": f"Контакт: {PEOPLE[str(spec['key'])][0][1]}, {PEOPLE[str(spec['key'])][0][0]}.",
                    "created": _ago(days=RNG.randrange(30, 200)),
                },
            )

    print(f"market intel: {rows} price points, {len(COMPANIES)} counterparties, inventory + suppliers")
    del offers


# ══════════════════════════════════════════════════════════════════════════════
# 7 — Attention surfaces: notifications, alerts, settings
# ══════════════════════════════════════════════════════════════════════════════

# Real notification kinds only: the portal renders `notifications.<kind>.title`
# / `.body` straight out of its locale files (`notification_service.keys_for`
# is the runtime contract), so an invented kind shows up as a raw i18n key in
# the bell. Bodies here interpolate at most {{number}} / {{title}}, both of
# which the params below provide.
_NOTIFICATIONS = [
    ("inquiry_approved", "notifications.inquiry_approved.title", "notifications.inquiry_approved.body"),
    ("offer_moderated", "notifications.offer_moderated.title", "notifications.offer_moderated.body"),
    ("contract_accepted", "notifications.contract_accepted.title", "notifications.contract_accepted.body"),
    ("deal_status", "notifications.deal_status.title", "notifications.deal_status.body"),
    ("verification_decided", "notifications.verification_decided.title", "notifications.verification_decided.body"),
    ("rfq_response_new", "notifications.rfq_response_new.title", "notifications.rfq_response_new.body"),
    ("sample_request_status", "notifications.sample_request_status.title", "notifications.sample_request_status.body"),
    ("lab_order_status", "notifications.lab_order_status.title", "notifications.lab_order_status.body"),
]


def seed_attention(
    db: Session,
    accounts: dict[str, list[int]],
    deals: list[dict[str, object]],
    offers: list[dict[str, object]],
) -> None:
    """Portal notifications, staff alert rules and fired alerts, operator settings."""
    made = 0
    for key, ids in accounts.items():
        account_id = ids[0]
        for i in range(RNG.randrange(3, 7)):
            kind, title_key, body_key = RNG.choice(_NOTIFICATIONS)
            created = _ago(days=RNG.randrange(0, 40), hours=RNG.randrange(0, 23))
            deal = RNG.choice(deals) if deals else None
            db.execute(
                sa.text(
                    """
                    INSERT INTO portal_notifications (user_account_id, kind, title_key, body_key,
                                                      params, entity, entity_id, read_at, created_at)
                    VALUES (:account_id, :kind, :title_key, :body_key, CAST(:params AS jsonb),
                            :entity, :entity_id, :read_at, :created)
                    """
                ),
                {
                    "account_id": account_id,
                    "kind": kind,
                    "title_key": title_key,
                    "body_key": body_key,
                    "params": json.dumps(
                        {
                            "number": f"DEAL-{NOW.year}-{RNG.randrange(1, 30):06d}",
                            # `contract_accepted` interpolates {{title}}.
                            "title": f"Договор поставки № ДП-{NOW.year}-{RNG.randrange(1, 30):04d}",
                            "company": next(
                                c["short_name"] for c in COMPANIES if c["key"] == key
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    "entity": "deal" if deal else None,
                    "entity_id": str(deal["id"]) if deal else None,
                    # The two most recent stay unread, so the bell always has a badge.
                    "read_at": None if i < 2 else created + datetime.timedelta(hours=3),
                    "created": created,
                },
            )
            made += 1

    rules = [
        ("large_volume", "Крупные партии PP свыше 200 т",
         {"product_ids": [1], "min_volume": 200, "urgency": ["high", "medium"]}),
        ("price_spike", "Скачок цены HDPE более 5% за сутки",
         {"product_ids": [2], "change_pct": 5}),
        ("below_market_offer", "Предложения ниже рынка на 7%",
         {"product_ids": [1, 2, 3], "below_pct": 7}),
        ("new_hot_request", "Срочные заявки покупателей",
         {"urgency": ["high"]}),
        ("new_buyer", "Новый покупатель на площадке", {}),
        ("source_failure", "Источник недоступен более 2 часов", {"minutes": 120}),
    ]
    rule_ids = []
    for kind, name, condition in rules:
        rule_ids.append(
            db.execute(
                sa.text(
                    """
                    INSERT INTO alert_rules (kind, name, condition, channels, is_enabled,
                                             created_by, created_at)
                    VALUES (:kind, :name, CAST(:condition AS jsonb), CAST(:channels AS jsonb),
                            :enabled, 1, :created)
                    RETURNING id
                    """
                ),
                {
                    "kind": kind,
                    "name": name,
                    "condition": json.dumps(condition, ensure_ascii=False),
                    "channels": json.dumps([{"channel": "dashboard"}, {"channel": "telegram_channel"}]),
                    "enabled": kind != "source_failure",
                    "created": _ago(days=RNG.randrange(40, 200)),
                },
            ).scalar_one()
        )

    fired = [
        ("large_volume", "warning", "Крупная заявка: PP T30S, 300 т",
         "ООО «Andijan Polymer Pipe» разместило заявку на 300 т полипропилена T30S с отгрузкой в течение 30 дней."),
        ("price_spike", "critical", "HDPE F7000: рост цены на 6,2%",
         "Средняя цена сделок по HDPE F7000 выросла на 6,2% за сутки — с 1 242 до 1 319 USD/т."),
        ("below_market_offer", "info", "Предложение ниже рынка: LDPE 2420D",
         "ООО «Turon Kimyo Trade» опубликовало LDPE 2420D по 1 268 USD/т — на 7,4% ниже рыночного уровня."),
        ("new_hot_request", "warning", "Срочная заявка: PVC SG-5, 150 т",
         "ООО «Qarshi Plastic Profile» — срочная потребность, остановка линии. Требуется отгрузка в течение 5 дней."),
        ("new_buyer", "info", "Новый верифицированный покупатель",
         "ООО «Urgench Irrigation Systems» прошло верификацию и получило доступ к маркетплейсу."),
        ("large_volume", "warning", "Крупная заявка: HDPE, 500 т",
         "ООО «Olmaliq Pipe & Fitting» — годовой контракт на 500 т ПЭ100 для напорных труб."),
        ("price_spike", "info", "PET BG-780: снижение на 3,1%",
         "Цена на бутылочный ПЭТ снизилась на 3,1% на фоне роста предложения от Jizzakh Petroleum."),
        ("below_market_offer", "info", "Предложение ниже рынка: PP EP548R",
         "ООО «Central Asia Polymers» — блок-сополимер EP548R по 1 214 USD/т, на 8,1% ниже среднего."),
    ]
    for i, (kind, severity, title, body) in enumerate(fired):
        created = _ago(days=RNG.randrange(0, 25), hours=RNG.randrange(0, 23))
        db.execute(
            sa.text(
                """
                INSERT INTO alerts (kind, rule_id, severity, title, body, dedupe_key, created_at)
                VALUES (:kind, :rule_id, :severity, :title, :body, :dedupe, :created)
                """
            ),
            {
                "kind": kind,
                "rule_id": RNG.choice(rule_ids),
                "severity": severity,
                "title": title,
                "body": body,
                "dedupe": f"showcase:{i}:{created.date()}",
                "created": created,
            },
        )

    for setting_key, value in APP_SETTINGS:
        db.execute(
            sa.text(
                """
                INSERT INTO app_settings (key, value, updated_at, updated_by)
                VALUES (:key, CAST(:value AS jsonb), :updated, 1)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                                updated_at = EXCLUDED.updated_at,
                                                updated_by = EXCLUDED.updated_by
                """
            ),
            {"key": setting_key, "value": json.dumps(value), "updated": _ago(days=RNG.randrange(1, 60))},
        )

    print(
        f"attention: {made} notifications, {len(rules)} alert rules, "
        f"{len(fired)} alerts, {len(APP_SETTINGS)} settings"
    )
    del offers


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════


def seed_showcase(*, reset: bool = False) -> bool:
    """Seed the showcase. Returns True when rows were written."""
    db = SessionLocal()
    try:
        if reset:
            purge(db)
        else:
            existing = db.execute(
                sa.text("SELECT id FROM companies WHERE tax_id = :tax_id LIMIT 1"),
                {"tax_id": SENTINEL_TAX_ID},
            ).first()
            if existing is not None:
                print("Showcase already seeded (sentinel company found). Use --reset to rebuild.")
                return False

        companies, accounts = seed_companies(db)
        offers = seed_offers(db, companies, accounts)
        requests = seed_requests(db, companies, accounts, offers)
        seed_inquiries(db, companies, accounts, offers)
        deals = seed_deals(db, companies, accounts, offers)
        seed_labs(db, companies, accounts, offers, deals)
        seed_market_intel(db, offers)
        seed_attention(db, accounts, deals, offers)

        db.commit()
        print(f"\nShowcase seeded: {len(companies)} companies, {len(offers)} offers, "
              f"{len(requests)} RFQs, {len(deals)} deals.")
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the investor-demo showcase dataset.")
    parser.add_argument(
        "--reset", action="store_true",
        help="delete existing demo rows first (signals/news/reports are never touched)",
    )
    args = parser.parse_args()
    seed_showcase(reset=args.reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
