"""
Showcase coverage — guarantees no signed-in company lands on an empty page.

The main seeder generates a realistic *market*: some companies trade a lot, some
barely. That is true to life, but it means whichever account is opened during a
demo may find "Лабораторные заявки — заявок пока нет", which reads as an
unfinished feature rather than as a quiet week.

This tops every trading company up to a floor on each surface, adding only what is
missing. Purely additive, so it can run against an already-seeded environment
without disturbing uploaded media or existing rows.

    docker exec <api> python -m app.seed.seed_showcase_coverage

Idempotent: a company already at or above the floor is left alone.
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

RNG = random.Random(20260731)
UTC = datetime.UTC

#: Minimum rows per trading company, per surface.
FLOOR = {"rfq": 2, "inquiry": 2, "lab": 1, "sample": 1, "deal": 1}

#: A short, coherent trade-room exchange for a deal that is mid-flight.
_DEAL_CHAT = [
    ("buyer", "Добрый день! Готовы взять объём по обсуждённой цене. Подтвердите, пожалуйста."),
    ("seller", "Здравствуйте! Цена подтверждена, товар на складе. Готовим договор."),
    ("buyer", "Принято, ждём проект договора на подписание через ЭЦП."),
    ("seller", "Договор сформирован и направлен на подписание."),
]

_INQUIRY_MESSAGES = [
    "Здравствуйте! Подтвердите наличие и сроки отгрузки на указанный объём.",
    "Интересует пробная партия. Возможна ли отсрочка платежа 30 дней?",
    "Просим направить КП с учётом доставки до нашего склада.",
    "Рассматриваем долгосрочный контракт. Какие условия при годовом объёме?",
]

_RFQ_COMMENTS = [
    "Требуется поставка партиями с отсрочкой платежа 30 дней.",
    "Нужен паспорт качества на каждую партию, отгрузка автотранспортом.",
    "Планируем регулярные закупки — просим цену при квартальном контракте.",
    "Срочная потребность, готовы рассмотреть предоплату.",
]


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def _open_deal(
    db: Session,
    offer: sa.RowMapping,
    seller: sa.RowMapping,
    buyer: sa.RowMapping,
    now: datetime.datetime,
) -> int:
    """A `contract_signed` deal: contract, signatures, history and chat, in one piece.

    Stops at `contract_signed` deliberately — no escrow row is written, so the deal
    cannot claim money moved that the payments tables have no record of.
    """
    seller_id, buyer_id = int(seller["id"]), int(buyer["id"])
    seller_account, buyer_account = seller["account_id"], buyer["account_id"]
    qty = RNG.choice([60, 100, 150])
    unit_price = float(offer["price"] or 1200)
    opened = now - datetime.timedelta(days=RNG.randrange(12, 90), hours=RNG.randrange(0, 20))
    sent_at = opened + datetime.timedelta(days=1)
    activated = sent_at + datetime.timedelta(days=1)

    contract_id = db.execute(
        sa.text(
            """
            INSERT INTO contracts (template_id, template_version, initiator_company_id,
                                   counterparty_company_id, offer_id, title, variables,
                                   generated_document_path, document_sha256, status,
                                   created_by_user_account_id, sent_at, activated_at,
                                   created_at, updated_at)
            VALUES (1, 1, :initiator, :counterparty, :offer_id, :title,
                    CAST(:variables AS jsonb), :path, :sha, 'active', :created_by,
                    :sent_at, :activated, :created, :activated)
            RETURNING id
            """
        ),
        {
            "initiator": buyer_id,
            "counterparty": seller_id,
            "offer_id": offer["id"],
            "title": (
                f"Договор поставки № ДП-{opened.year}-{9000 + seller_id:04d} "
                f"({offer['polymer_type']} {offer['grade_text']})"
            ),
            "variables": json.dumps(
                {
                    "product": f"{offer['polymer_type']} {offer['grade_text']}",
                    "qty": str(qty), "unit": "t", "price": f"{unit_price:.2f}",
                    "currency": "USD", "incoterms": "DAP",
                    "payment_terms": "50% предоплата, 50% по факту отгрузки",
                    "delivery_window": "в течение 14 календарных дней с даты подписания",
                    "special_conditions": "Паспорт качества на каждую партию. Тара — биг-бэг 1000 кг.",
                },
                ensure_ascii=False,
            ),
            "path": f"contracts/coverage-{seller_id:04d}/contract_v1.pdf",
            "sha": f"{RNG.randrange(16**16):016x}" * 4,
            "created_by": buyer_account,
            "sent_at": sent_at,
            "activated": activated,
            "created": opened,
        },
    ).scalar_one()

    for company_id, account_id in ((buyer_id, buyer_account), (seller_id, seller_account)):
        evidence_id = db.execute(
            sa.text(
                """
                INSERT INTO signature_evidence (company_id, user_account_id, purpose, challenge,
                                                pkcs7_storage_path, pkcs7_sha256, cert_subject,
                                                signed_at, created_at)
                VALUES (:company_id, :account_id, 'contract_sign', :challenge, :path, :sha,
                        CAST(:subject AS jsonb), :signed, :signed)
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "account_id": account_id,
                "challenge": f"{RNG.randrange(16**16):016x}" * 4,
                "path": f"evidence/eimzo/{company_id}/coverage-{contract_id}.p7s",
                "sha": f"{RNG.randrange(16**16):016x}" * 4,
                "subject": json.dumps(
                    {"O": str(seller["legal_name"] if company_id == seller_id else buyer["legal_name"]),
                     "issuer": "E-IMZO Root CA",
                     "serialNumber": str(RNG.randrange(10**11, 10**12))},
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
            {"contract_id": contract_id, "company_id": company_id, "account_id": account_id,
             "evidence_id": evidence_id, "signed": activated},
        )

    deal_id = db.execute(
        sa.text(
            """
            INSERT INTO deals (number, buyer_company_id, seller_company_id, offer_id,
                               contract_id, status, amount, currency,
                               created_by_user_account_id, created_at, updated_at)
            VALUES (:number, :buyer, :seller, :offer_id, :contract_id, 'contract_signed',
                    :amount, 'USD', :created_by, :created, :updated)
            RETURNING id
            """
        ),
        {
            "number": f"DEAL-{opened.year}-{900000 + seller_id:06d}",
            "buyer": buyer_id,
            "seller": seller_id,
            "offer_id": offer["id"],
            "contract_id": contract_id,
            "amount": round(qty * unit_price, 2),
            "created_by": buyer_account,
            "created": opened,
            "updated": activated,
        },
    ).scalar_one()

    stamp, prior = opened, None
    for step in ("negotiation", "contract_pending", "contract_signed"):
        db.execute(
            sa.text(
                """
                INSERT INTO deal_status_history (deal_id, from_status, to_status, actor_kind,
                                                 actor_id, created_at)
                VALUES (:deal_id, :from_status, :to_status, :actor_kind, :actor_id, :created)
                """
            ),
            {
                "deal_id": deal_id, "from_status": prior, "to_status": step,
                "actor_kind": "buyer" if step != "contract_signed" else "seller",
                "actor_id": buyer_account if step != "contract_signed" else seller_account,
                "created": stamp,
            },
        )
        prior, stamp = step, stamp + datetime.timedelta(days=1)

    stamp = opened
    for side, text in _DEAL_CHAT:
        stamp += datetime.timedelta(hours=RNG.randrange(3, 20))
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
                "body": text,
                "created": stamp,
            },
        )
    return 1


def ensure_coverage(db: Session) -> None:
    now = _now()

    companies = db.execute(
        sa.text(
            """
            SELECT c.id, c.short_name, c.legal_name, c.legal_address,
                   (SELECT m.user_account_id FROM company_members m
                     WHERE m.company_id = c.id ORDER BY m.id LIMIT 1) AS account_id
            FROM companies c
            WHERE c.status = 'verified'
            ORDER BY c.id
            """
        )
    ).mappings().all()

    # Offers available to inquire about / order analysis on, by owning company.
    offers = db.execute(
        sa.text(
            """
            SELECT id, company_id, product_id, price, grade_text, polymer_type
            FROM seller_offers WHERE status = 'approved' ORDER BY id
            """
        )
    ).mappings().all()
    if not offers:
        print("no approved offers — nothing to attach coverage to")
        return

    added = {"rfq": 0, "inquiry": 0, "lab": 0, "sample": 0, "deal": 0}

    for company in companies:
        cid = int(company["id"])
        account_id = company["account_id"]
        if account_id is None:
            continue
        others = [o for o in offers if int(o["company_id"]) != cid]
        own = [o for o in offers if int(o["company_id"]) == cid]
        if not others:
            continue

        # ── purchase requests ────────────────────────────────────────────────
        have = db.execute(
            sa.text("SELECT count(*) FROM requests WHERE company_id = :c"), {"c": cid}
        ).scalar_one()
        for n in range(max(0, FLOOR["rfq"] - int(have))):
            offer = others[(cid + n) % len(others)]
            created = now - datetime.timedelta(days=RNG.randrange(2, 45), hours=RNG.randrange(0, 20))
            volume = RNG.choice([25, 50, 80, 120, 200])
            db.execute(
                sa.text(
                    """
                    INSERT INTO requests (number, product_id, grade_text, polymer_type, volume,
                                          volume_unit, target_price, currency, incoterms,
                                          destination_country, port_or_city, validity_days,
                                          urgency, comment, status, ai, created_at, updated_at,
                                          company_name, contact_name, legal_address, company_id,
                                          created_by_user_account_id, required_docs, visibility)
                    VALUES (:number, :product_id, :grade, :ptype, :volume, 'MT', :target, 'USD',
                            :incoterms, 'UZ', :city, 30, :urgency, :comment, :status,
                            '{}'::jsonb, :created, :created, :company_name, :contact,
                            :address, :company_id, :account_id, CAST(:docs AS jsonb),
                            'verified_only')
                    """
                ),
                {
                    "number": f"REQ-{created.strftime('%Y-%m-%d')}-{9000 + cid * 10 + n:05d}",
                    "product_id": offer["product_id"],
                    "grade": offer["grade_text"],
                    "ptype": offer["polymer_type"],
                    "volume": volume,
                    "target": round(float(offer["price"] or 1200) * 0.97, 2),
                    "incoterms": RNG.choice(["DAP", "CPT", "EXW"]),
                    "city": (company["legal_address"] or "Ташкент").split(",")[0],
                    "urgency": RNG.choice(["low", "medium", "high"]),
                    "comment": RNG.choice(_RFQ_COMMENTS),
                    "status": RNG.choice(["new", "viewed", "in_progress", "offer_sent"]),
                    "created": created,
                    "company_name": company["legal_name"],
                    "contact": None,
                    "address": company["legal_address"],
                    "company_id": cid,
                    "account_id": account_id,
                    "docs": json.dumps(["tds", "coa"]),
                },
            )
            added["rfq"] += 1

        # ── inquiries on other companies' offers ─────────────────────────────
        have = db.execute(
            sa.text("SELECT count(*) FROM offer_requests WHERE company_id = :c"), {"c": cid}
        ).scalar_one()
        for n in range(max(0, FLOOR["inquiry"] - int(have))):
            offer = others[(cid * 3 + n) % len(others)]
            created = now - datetime.timedelta(days=RNG.randrange(1, 40), hours=RNG.randrange(0, 20))
            status = ["approved", "pending", "approved"][n % 3]
            db.execute(
                sa.text(
                    """
                    INSERT INTO offer_requests (offer_id, quantity, qty_unit, target_price,
                                                currency, message, status, moderated_by,
                                                reviewed_at, forwarded_at, created_at, updated_at,
                                                seller_notified, company_id,
                                                created_by_user_account_id)
                    VALUES (:offer_id, :qty, 'MT', :target, 'USD', :message, :status,
                            :moderated_by, :reviewed, :forwarded, :created, :created,
                            :notified, :company_id, :account_id)
                    """
                ),
                {
                    "offer_id": offer["id"],
                    "qty": RNG.choice([10, 20, 40, 60]),
                    "target": round(float(offer["price"] or 1200) * 0.96, 2),
                    "message": RNG.choice(_INQUIRY_MESSAGES),
                    "status": status,
                    "moderated_by": 2 if status != "pending" else None,
                    "reviewed": created + datetime.timedelta(hours=5) if status != "pending" else None,
                    "forwarded": created + datetime.timedelta(hours=6) if status == "approved" else None,
                    "created": created,
                    "notified": status == "approved",
                    "company_id": cid,
                    "account_id": account_id,
                },
            )
            added["inquiry"] += 1

        # ── laboratory orders ────────────────────────────────────────────────
        have = db.execute(
            sa.text("SELECT count(*) FROM lab_orders WHERE company_id = :c"), {"c": cid}
        ).scalar_one()
        if int(have) < FLOOR["lab"]:
            # ck_lab_order_target: an order hangs off an offer or off a deal. A seller
            # tests its own listing; a pure buyer tests material from one of its deals.
            target_offer = own[0] if own else None
            deal_id = None
            if target_offer is None:
                deal_id = db.execute(
                    sa.text(
                        """
                        SELECT id FROM deals
                        WHERE buyer_company_id = :c OR seller_company_id = :c
                        ORDER BY id LIMIT 1
                        """
                    ),
                    {"c": cid},
                ).scalar()
            if target_offer is not None or deal_id is not None:
                created = now - datetime.timedelta(days=RNG.randrange(3, 60))
                status = RNG.choice(["submitted", "accepted", "in_analysis", "sample_awaited"])
                partner = db.execute(
                    sa.text("SELECT id FROM lab_partners ORDER BY id LIMIT 1")
                ).scalar()
                db.execute(
                    sa.text(
                        """
                        INSERT INTO lab_orders (number, company_id, created_by_user_account_id,
                                                offer_id, deal_id, sample_volume, comment, status,
                                                lab_partner_id, operator_note, handled_by,
                                                created_at, updated_at)
                        VALUES (:number, :company_id, :account_id, :offer_id, :deal_id, :volume,
                                :comment, :status, :partner, :note, :handled_by, :created, :created)
                        """
                    ),
                    {
                        "number": f"LAB-{created.year}-{9000 + cid:06d}",
                        "company_id": cid,
                        "account_id": account_id,
                        "offer_id": target_offer["id"] if target_offer is not None else None,
                        "deal_id": deal_id,
                        "volume": RNG.choice(["500 г", "1 кг", "2 кг"]),
                        "comment": "Просим подтвердить ПТР и плотность независимым анализом.",
                        "status": status,
                        "partner": partner if status != "submitted" else None,
                        "note": "Образец получен." if status == "in_analysis" else None,
                        "handled_by": 2 if status != "submitted" else None,
                        "created": created,
                    },
                )
                added["lab"] += 1

        # ── sample requests ──────────────────────────────────────────────────
        have = db.execute(
            sa.text(
                """
                SELECT count(*) FROM sample_requests
                WHERE buyer_company_id = :c OR seller_company_id = :c
                """
            ),
            {"c": cid},
        ).scalar_one()
        if int(have) < FLOOR["sample"]:
            for offer in others:
                exists = db.execute(
                    sa.text(
                        """
                        SELECT 1 FROM sample_requests
                        WHERE offer_id = :o AND buyer_company_id = :c
                          AND status IN ('requested','accepted','sent')
                        """
                    ),
                    {"o": offer["id"], "c": cid},
                ).first()
                if exists:
                    continue
                created = now - datetime.timedelta(days=RNG.randrange(2, 40))
                status = RNG.choice(["requested", "accepted", "sent", "received"])
                db.execute(
                    sa.text(
                        """
                        INSERT INTO sample_requests (offer_id, buyer_company_id, seller_company_id,
                                                     created_by_user_account_id, status, qty,
                                                     delivery_address, courier, tracking_ref,
                                                     accepted_at, sent_at, received_at,
                                                     created_at, updated_at)
                        VALUES (:offer_id, :buyer, :seller, :account_id, :status, :qty, :address,
                                :courier, :tracking, :accepted, :sent, :received, :created, :created)
                        """
                    ),
                    {
                        "offer_id": offer["id"],
                        "buyer": cid,
                        "seller": offer["company_id"],
                        "account_id": account_id,
                        "status": status,
                        "qty": RNG.choice(["500 г", "1 кг"]),
                        "address": f"{company['legal_address']} (склад, приёмка 09:00–17:00)",
                        "courier": "BTS Express" if status in ("sent", "received") else None,
                        "tracking": f"UZ{RNG.randrange(10**8, 10**9)}" if status in ("sent", "received") else None,
                        "accepted": created + datetime.timedelta(days=1) if status != "requested" else None,
                        "sent": created + datetime.timedelta(days=3) if status in ("sent", "received") else None,
                        "received": created + datetime.timedelta(days=6) if status == "received" else None,
                        "created": created,
                    },
                )
                added["sample"] += 1
                break

        # ── deals (with the contract and trade-room chat that make one real) ──
        have = db.execute(
            sa.text(
                """
                SELECT count(*) FROM deals
                WHERE buyer_company_id = :c OR seller_company_id = :c
                """
            ),
            {"c": cid},
        ).scalar_one()
        if int(have) < FLOOR["deal"] and own:
            offer = own[0]
            buyer = next(
                (c for c in companies
                 if int(c["id"]) != cid and c["account_id"] is not None), None
            )
            if buyer is not None:
                added["deal"] += _open_deal(db, offer, company, buyer, now)

    db.commit()
    print(
        "coverage top-up: "
        + ", ".join(f"{k}+{v}" for k, v in added.items())
        + f" across {len(companies)} verified companies"
    )


def main() -> int:
    argparse.ArgumentParser(description="Top every company up to a per-surface floor.").parse_args()
    db = SessionLocal()
    try:
        ensure_coverage(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
