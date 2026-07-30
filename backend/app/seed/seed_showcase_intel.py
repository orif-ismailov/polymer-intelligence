"""
Showcase intel — the signal-side rows the internal dashboard counts and charts.

The dashboard's KPI strip and AI panel read the *intelligence* tables, not the
portal ones, so a fully-populated marketplace can still render "0 buyers / 0
sellers / 0 hot leads". Three things are filled here:

  * `clients` / `sellers` — the Telegram-origin participants. The portal's
    `companies` are a separate identity space; `total_buyers` counts `clients`.
  * `counterparties.role` — `total_sellers` counts `role = 'seller'` specifically,
    so every company that actually supplies is marked as one.
  * AI-classified `signals` — `hot_leads` counts `ai->>'classification' = 'HOT'`,
    and the live feed / AI panel render the same rows.

    docker exec <api> python -m app.seed.seed_showcase_intel

Idempotent and additive: existing rows are updated in place, signals are keyed off
an `ai.seed` marker so a re-run replaces its own set and nothing else.
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

RNG = random.Random(20260801)
MARKER = "showcase-intel"
UTC = datetime.UTC

#: Telegram-origin buyers — the Mini App audience, distinct from portal accounts.
_TG_BUYERS = [
    ("Азиз Рахимов", "ООО «Yashnabad Plastic»", "+998901112233"),
    ("Дилшод Умаров", "ООО «Chirchiq Pack Servis»", "+998902223344"),
    ("Гулнора Салимова", "ЧП «Sirdaryo Agro Plast»", "+998903334455"),
    ("Бекзод Норов", "ООО «Zomin Polimer»", "+998904445566"),
    ("Феруза Каримова", "ООО «Yangiyul Tara»", "+998905556677"),
    ("Икром Тошев", "ООО «Denov Plastik»", "+998906667788"),
    ("Сардор Юсупов", "ООО «Kokand Profil»", "+998907778899"),
    ("Малика Абдуллаева", "ООО «Margilan Pack»", "+998908889900"),
    ("Жахонгир Собиров", "ООО «Guliston Truba»", "+998909990011"),
    ("Отабек Мирзаев", "ООО «Bekabad Polimer»", "+998911112233"),
    ("Нилуфар Хакимова", "ООО «Shahrisabz Tara»", "+998912223344"),
    ("Рустам Ergashev", "ООО «Navoiy Plast Servis»", "+998913334455"),
    ("Камола Ниязова", "ООО «Xiva Agroplast»", "+998914445566"),
    ("Азамат Дустов", "ООО «Buxoro Profil»", "+998915556677"),
    ("Санжар Холматов", "ООО «Angren Tara»", "+998916667788"),
    ("Зухра Исмоилова", "ООО «Jizzax Plastik»", "+998917778899"),
    ("Фаррух Бобоев", "ООО «Qoqon Polimer»", "+998918889900"),
    ("Лола Турсунова", "ООО «Samarqand Pack»", "+998919990011"),
]

_SIGNAL_REGIONS = ["Ташкент", "Самарканд", "Андижан", "Фергана", "Бухара",
                   "Наманган", "Навои", "Нукус", "Карши", "Термез"]

_BASE_PRICE = {1: 1180, 2: 1240, 3: 1330, 4: 1265, 5: 1010, 6: 1120, 7: 1480, 8: 2150}

_SUMMARY = {
    "buy_request": "Запрос на закупку {code} — {volume} т, {region}. Покупатель проверен.",
    "sell_offer": "Предложение {code} — {volume} т со склада, {region}. Цена ниже среднерыночной.",
    "deal": "Сделка по {code}: {volume} т по {price} USD/т, {region}.",
    "price_quote": "Котировка {code}: {price} USD/т, {region}.",
}


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def seed_intel(db: Session, *, signals: int = 120) -> None:
    now = _now()

    # ── Telegram-origin buyers and sellers ───────────────────────────────────
    made_clients = 0
    for i, (contact, company, phone) in enumerate(_TG_BUYERS):
        existing = db.execute(
            sa.text("SELECT id FROM clients WHERE telegram_user_id = :t"),
            {"t": 780_000_000 + i},
        ).first()
        if existing:
            continue
        db.execute(
            sa.text(
                """
                INSERT INTO clients (telegram_user_id, phone, company_name, contact_name,
                                     language, is_blocked, created_at)
                VALUES (:tg, :phone, :company, :contact, :lang, false, :created)
                """
            ),
            {
                "tg": 780_000_000 + i,
                "phone": phone,
                "company": company,
                "contact": contact,
                "lang": RNG.choice(["ru", "ru", "uz"]),
                "created": now - datetime.timedelta(days=RNG.randrange(5, 260)),
            },
        )
        made_clients += 1

    # Telegram-origin sellers mirror the portal's selling companies, so the two
    # identity spaces agree on who supplies this market.
    made_sellers = 0
    supplier_rows = db.execute(
        sa.text(
            """
            SELECT DISTINCT c.id, c.short_name, c.legal_name
            FROM companies c JOIN seller_offers o ON o.company_id = c.id
            WHERE c.status = 'verified' ORDER BY c.id
            """
        )
    ).mappings().all()
    for i, row in enumerate(supplier_rows):
        existing = db.execute(
            sa.text("SELECT id FROM sellers WHERE telegram_user_id = :t"),
            {"t": 790_000_000 + i},
        ).first()
        if existing:
            continue
        db.execute(
            sa.text(
                """
                INSERT INTO sellers (telegram_user_id, company_name, contact_name, phone,
                                     country, is_verified, is_blocked, company_id, created_at)
                VALUES (:tg, :company, :contact, :phone, 'UZ', true, false, :company_id, :created)
                """
            ),
            {
                "tg": 790_000_000 + i,
                "company": row["legal_name"],
                "contact": None,
                "phone": f"+9989{RNG.randrange(10**8, 10**9 - 1)}",
                "company_id": row["id"],
                "created": now - datetime.timedelta(days=RNG.randrange(20, 280)),
            },
        )
        made_sellers += 1

    # ── Counterparty roles ───────────────────────────────────────────────────
    # `total_sellers` counts role='seller' exactly, so anyone who supplies is one.
    supplier_names = {r["short_name"] for r in supplier_rows}
    updated_roles = 0
    for name in supplier_names:
        result = db.execute(
            sa.text("UPDATE counterparties SET role = 'seller' WHERE canonical_name = :n"),
            {"n": name},
        )
        updated_roles += result.rowcount or 0

    # ── AI-classified signals (live feed + AI panel + hot-lead KPI) ──────────
    db.execute(sa.text("DELETE FROM signals WHERE ai->>'seed' = :m"), {"m": MARKER})

    grades = db.execute(
        sa.text("SELECT id, product_id, code FROM product_grades ORDER BY id")
    ).mappings().all()
    source_ids = [
        r[0] for r in db.execute(
            sa.text("SELECT id FROM sources WHERE adapter LIKE 'uzex%' ORDER BY id")
        ).all()
    ] or [1]

    kinds = ["buy_request", "sell_offer", "deal", "price_quote"]
    made_signals = 0
    for i in range(signals):
        grade = grades[i % len(grades)]
        product_id = int(grade["product_id"])
        kind = kinds[i % len(kinds)]
        base = _BASE_PRICE.get(product_id, 1200)
        price = round(base * RNG.uniform(0.94, 1.07), 2)
        volume = RNG.choice([20, 25, 40, 60, 80, 100, 150, 200, 300, 500])
        region = _SIGNAL_REGIONS[i % len(_SIGNAL_REGIONS)]

        # A HOT lead is a large, urgent buy-side signal — the same rule the
        # dashboard's AI panel explains to the operator.
        urgency = RNG.choices(["high", "medium", "low"], weights=[3, 5, 4])[0]
        if kind == "buy_request" and (urgency == "high" or volume >= 300):
            classification, score = "HOT", RNG.uniform(0.86, 0.97)
        elif urgency == "high" or volume >= 200:
            classification, score = "MEDIUM", RNG.uniform(0.55, 0.74)
        else:
            classification, score = "LOW", RNG.uniform(0.24, 0.49)

        code = str(grade["code"])
        db.execute(
            sa.text(
                """
                INSERT INTO signals (kind, source_id, product_id, grade_id, grade_text,
                                     volume, volume_unit, price, currency, price_basis,
                                     region, ai, urgency, status, event_at, created_at)
                VALUES (:kind, :source_id, :product_id, :grade_id, :grade, :volume, 'MT',
                        :price, 'USD', :basis, :region, CAST(:ai AS jsonb), :urgency,
                        :status, :event_at, :event_at)
                """
            ),
            {
                "kind": kind,
                "source_id": source_ids[i % len(source_ids)],
                "product_id": product_id,
                "grade_id": grade["id"],
                "grade": code,
                "volume": volume,
                "price": price,
                "basis": RNG.choice(["EXW", "FCA", "CPT", "DAP", "CIF"]),
                "region": region,
                "ai": json.dumps(
                    {
                        "seed": MARKER,
                        "classification": classification,
                        "lead_score": round(score, 2),
                        "needs_review": i % 9 == 0,
                        "summary": _SUMMARY[kind].format(
                            code=code, volume=volume, price=price, region=region
                        ),
                    },
                    ensure_ascii=False,
                ),
                "urgency": urgency,
                # Vocabulary per app/models/signals.py: new / viewed / processed / archived.
                # Only the first two are used: `processed`/`archived` had no dashboard
                # translation until now, and an image built before that fix renders the
                # raw key in the feed's status column.
                "status": RNG.choices(["new", "viewed"], weights=[7, 3])[0],
                "event_at": now - datetime.timedelta(
                    hours=RNG.randrange(1, 26 * 24), minutes=RNG.randrange(0, 59)
                ),
            },
        )
        made_signals += 1

    db.commit()
    hot = db.execute(
        sa.text("SELECT count(*) FROM signals WHERE ai->>'classification' = 'HOT'")
    ).scalar_one()
    print(
        f"intel: {made_clients} clients, {made_sellers} sellers, {updated_roles} counterparty "
        f"roles → 'seller', {made_signals} classified signals ({hot} HOT leads)"
    )


def main() -> int:
    argparse.ArgumentParser(description="Seed dashboard-side intelligence rows.").parse_args()
    db = SessionLocal()
    try:
        seed_intel(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
