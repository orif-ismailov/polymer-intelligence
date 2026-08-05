"""
Showcase content for the role-specific tracks added in 0031-0039.

`seed_showcase` fills the trading core; this fills what the manufacturer,
logistics and laboratory work added on top, so those screens are not the one
empty corner of an otherwise populated demo:

  * companies.manufacturer_profile / logistics_profile / laboratory_profile
  * company_reviews          — ratings on verified sellers, from real counterparties
  * company_media + cover     — a cover image and a small gallery per company
  * factory_rfqs (+documents) — buyer → manufacturer enquiries across every status
  * manufacturer_threads/messages
  * logistics_requests (+ threads/messages)  — carrier broadcast + replies
  * lab_requests (+ threads/messages)        — laboratory enquiries + replies

    docker exec <api> python -m app.seed.seed_showcase_profiles

Idempotent and additive: a company that already has a profile, and a table that
already has rows, is left alone. Run `--reset` to rebuild just these tables.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import random
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.seed.showcase_profiles_data import (
    CONVERTER_PROFILES,
    LABORATORY_PROFILES,
    LOGISTICS_PROFILES,
    MANUFACTURER_PROFILES,
    REVIEW_TEXTS,
)

RNG = random.Random(20260802)
UTC = datetime.UTC

_RESET_TABLES = [
    "lab_request_messages", "lab_request_threads", "lab_requests",
    "logistics_request_messages", "logistics_request_threads", "logistics_requests",
    "manufacturer_messages", "manufacturer_threads",
    "factory_rfq_documents", "factory_rfqs",
    "company_reviews", "company_media",
]


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def _ago(days: float = 0, hours: float = 0) -> datetime.datetime:
    return _now() - datetime.timedelta(days=days, hours=hours)


# ══════════════════════════════════════════════════════════════════════════════
# Company lookup
# ══════════════════════════════════════════════════════════════════════════════


def _companies(db: Session) -> dict[str, dict]:
    """Slug-ish key → company row, matched on short_name (the seed's stable label)."""
    rows = db.execute(
        sa.text(
            """
            SELECT c.id, c.short_name, c.legal_name, c.legal_address, c.status,
                   (SELECT m.user_account_id FROM company_members m
                     WHERE m.company_id = c.id ORDER BY m.id LIMIT 1) AS account_id,
                   (SELECT a.name FROM company_members m
                      JOIN user_accounts a ON a.id = m.user_account_id
                     WHERE m.company_id = c.id ORDER BY m.id LIMIT 1) AS contact_name,
                   (SELECT a.phone FROM company_members m
                      JOIN user_accounts a ON a.id = m.user_account_id
                     WHERE m.company_id = c.id ORDER BY m.id LIMIT 1) AS contact_phone,
                   ARRAY(SELECT r.role::text FROM company_business_roles r
                          WHERE r.company_id = c.id) AS roles
            FROM companies c ORDER BY c.id
            """
        )
    ).mappings().all()
    return {str(r["short_name"]): dict(r) for r in rows}


#: short_name in the seeded data, per slug used by the profile tables.
_SLUG_TO_NAME = {
    "shurtan": "Shurtan GCC",
    "uzkor": "Uz-Kor Gas Chemical",
    "jizzakh": "Jizzakh Petroleum",
    "navoiyazot": "Navoiyazot",
    "tashkent_plastic": "Tashkent Plastic",
    "andijan_pipe": "Andijan Polymer Pipe",
    "fergana_film": "Fergana Film Pack",
    "bukhara_sacks": "Bukhara Woven Sacks",
    "namangan_house": "Namangan Household",
    "samarkand_pet": "Samarkand PET",
    "chirchiq_cable": "Chirchiq Cable",
    "nukus_agrofilm": "Nukus Agro Film",
    "olmaliq_pipe": "Olmaliq Pipe",
    "termez_pack": "Termez Packaging",
    "urgench_irrigation": "Urgench Irrigation",
    "qarshi_profile": "Qarshi Plastic Profile",
    "angren_recycling": "Angren Recycling",
    "trans_asia": "Trans Asia Logistics",
    "rail_freight": "Uzbek Rail Freight",
    "cptl_lab": "Central Polymer Lab",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1 — Role profiles
# ══════════════════════════════════════════════════════════════════════════════


def seed_profiles(db: Session, companies: dict[str, dict]) -> None:
    filled = {"manufacturer": 0, "logistics": 0, "laboratory": 0}

    def _set(company_id: int, column: str, payload: dict) -> None:
        db.execute(
            sa.text(f"UPDATE companies SET {column} = CAST(:p AS jsonb) WHERE id = :id"),  # noqa: S608
            {"p": json.dumps(payload, ensure_ascii=False), "id": company_id},
        )

    for slug, profile in MANUFACTURER_PROFILES.items():
        row = companies.get(_SLUG_TO_NAME[slug])
        if row is None:
            continue
        _set(int(row["id"]), "manufacturer_profile", profile)
        filled["manufacturer"] += 1

    for slug, (ptype, main, cap, lines, staff, founded, iso) in CONVERTER_PROFILES.items():
        row = companies.get(_SLUG_TO_NAME[slug])
        if row is None:
            continue
        _set(
            int(row["id"]),
            "manufacturer_profile",
            {
                "production_type": ptype,
                "main_products": main,
                "annual_capacity_tons": cap,
                "production_lines": lines,
                "employees": staff,
                "markets": ["domestic"] if cap < 15_000 else ["domestic", "export"],
                "export_countries": [] if cap < 15_000 else ["KZ", "TJ"],
                "founded_year": founded,
                "iso_certification": iso,
                "moq_tons": RNG.choice([5, 10, 20]),
                "min_annual_volume_tons": RNG.choice([100, 200, 300]),
                "financial_requirements": {
                    "bank_guarantee": RNG.random() < 0.4,
                    "letter_of_credit": RNG.random() < 0.3,
                    "payment_deferral": RNG.random() < 0.7,
                    "prepayment": RNG.random() < 0.6,
                },
                "additional_requirements": RNG.sample(
                    ["financial_reporting", "market_experience", "licenses_certificates",
                     "end_products_info", "production_photos"],
                    RNG.randrange(1, 4),
                ),
                "additional_other": None,
            },
        )
        filled["manufacturer"] += 1

    for slug, profile in LOGISTICS_PROFILES.items():
        row = companies.get(_SLUG_TO_NAME[slug])
        if row is None:
            continue
        _set(int(row["id"]), "logistics_profile", profile)
        filled["logistics"] += 1

    for slug, profile in LABORATORY_PROFILES.items():
        row = companies.get(_SLUG_TO_NAME[slug])
        if row is None:
            continue
        _set(int(row["id"]), "laboratory_profile", profile)
        filled["laboratory"] += 1

    db.commit()
    print(
        f"profiles: {filled['manufacturer']} manufacturer, "
        f"{filled['logistics']} logistics, {filled['laboratory']} laboratory"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2 — Reviews
# ══════════════════════════════════════════════════════════════════════════════


def seed_reviews(db: Session, companies: dict[str, dict]) -> None:
    verified = [c for c in companies.values() if c["status"] == "verified" and c["account_id"]]
    if len(verified) < 2:
        print("reviews: not enough verified companies")
        return

    #: Rating is a headline number in the public directory, so a company showing a
    #: single review reads as a dead listing. Traded-with counterparties are used
    #: first — that rating is corroborated by the deal tables — and the remainder is
    #: topped up from other verified companies to reach the floor.
    floor = 3
    by_id = {c["id"]: c for c in verified}
    made = 0
    for target in verified:
        existing = db.execute(
            sa.text("SELECT count(*) FROM company_reviews WHERE company_id = :id"),
            {"id": target["id"]},
        ).scalar_one()
        if int(existing) >= floor:
            continue

        partners = db.execute(
            sa.text(
                """
                SELECT DISTINCT CASE WHEN d.buyer_company_id = :id
                                     THEN d.seller_company_id ELSE d.buyer_company_id END AS other
                FROM deals d
                WHERE (d.buyer_company_id = :id OR d.seller_company_id = :id)
                  AND d.status IN ('completed', 'delivered', 'shipped')
                """
            ),
            {"id": target["id"]},
        ).scalars().all()

        # `uq_company_review_pair` allows one review per (company, author), so authors
        # who already left one are excluded rather than retried.
        already = set(
            db.execute(
                sa.text(
                    "SELECT author_company_id FROM company_reviews WHERE company_id = :id"
                ),
                {"id": target["id"]},
            ).scalars().all()
        )
        authors = [by_id[p] for p in partners if p in by_id and p not in already]
        if len(authors) < floor:
            spare = [
                c for c in verified
                if c["id"] != target["id"]
                and c["id"] not in already
                and c["id"] not in {a["id"] for a in authors}
            ]
            RNG.shuffle(spare)
            authors += spare[: floor - len(authors)]

        seen: set[int] = set()
        picked = []
        for author in authors:
            if author["id"] in seen:
                continue
            seen.add(author["id"])
            picked.append(author)
        for author in picked[: floor + RNG.randrange(0, 2) - int(existing)]:
            rating, body = RNG.choice(REVIEW_TEXTS)
            created = _ago(days=RNG.randrange(3, 150))
            db.execute(
                sa.text(
                    """
                    INSERT INTO company_reviews (company_id, author_company_id, author_account_id,
                                                 rating, body, status, created_at, updated_at)
                    VALUES (:company_id, :author_company_id, :author_account_id, :rating, :body,
                            'published', :created, :created)
                    """
                ),
                {
                    "company_id": target["id"],
                    "author_company_id": author["id"],
                    "author_account_id": author["account_id"],
                    "rating": rating,
                    "body": body,
                    "created": created,
                },
            )
            made += 1
    db.commit()
    print(f"reviews: {made} published")


# ══════════════════════════════════════════════════════════════════════════════
# 3 — Cover images + gallery
# ══════════════════════════════════════════════════════════════════════════════


def _cover_image(name: str, seed: int) -> bytes:
    """A wide brand banner: the company monogram over a subtle industrial gradient."""
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    from app.seed.seed_showcase_media import _LOGO_PALETTE, _font, _initials  # noqa: PLC0415

    w, h = 1600, 480
    dark, light = _LOGO_PALETTE[seed % len(_LOGO_PALETTE)]
    rng = random.Random(seed)

    img = Image.new("RGB", (w, h), dark)
    d = ImageDraw.Draw(img, "RGBA")

    # Diagonal sheen so the banner is not a flat block of colour.
    wash = Image.new("L", (w, h))
    wd = ImageDraw.Draw(wash)
    for i in range(0, w + h, 4):
        wd.line([(i, 0), (0, i)], fill=min(255, int(190 * i / (w + h))), width=4)
    img = Image.composite(
        Image.new("RGB", (w, h), tuple(min(255, int(c * 1.9)) for c in dark)), img, wash
    )
    d = ImageDraw.Draw(img, "RGBA")

    # Faint pellet field, echoing the product photography.
    for _ in range(220):
        r = rng.randint(10, 34)
        x, y = rng.randrange(-20, w), rng.randrange(-20, h)
        d.ellipse([x, y, x + r, y + int(r * 0.78)], fill=(*light, rng.randint(8, 26)))

    initials = _initials(name)
    font = _font(150)
    box = d.textbbox((0, 0), initials, font=font)
    d.text((90, (h - (box[3] - box[1])) / 2 - box[1]), initials, font=font, fill=(*light, 255))
    d.rounded_rectangle([92, h - 132, 92 + 190, h - 122], radius=5, fill=(*light, 230))

    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()


def seed_media(db: Session, companies: dict[str, dict]) -> None:
    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import ensure_bucket, s3_client  # noqa: PLC0415

    ensure_bucket()
    covers = gallery = 0

    for name, row in companies.items():
        if row["status"] != "verified":
            continue
        company_id = int(row["id"])
        has_cover = db.execute(
            sa.text("SELECT cover_storage_path FROM companies WHERE id = :id"),
            {"id": company_id},
        ).scalar()
        if not has_cover:
            data = _cover_image(name, seed=company_id * 7)
            key = f"companies/{company_id}/cover/showcase.jpg"
            s3_client.put_object(  # type: ignore[attr-defined]
                Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType="image/jpeg"
            )
            db.execute(
                sa.text("UPDATE companies SET cover_storage_path = :k WHERE id = :id"),
                {"k": key, "id": company_id},
            )
            covers += 1

        already = db.execute(
            sa.text("SELECT count(*) FROM company_media WHERE company_id = :id"),
            {"id": company_id},
        ).scalar_one()
        if already:
            continue
        # A small gallery: reuse the offer photography this company already has, so
        # the profile shows its own product rather than a generic stock frame.
        shots = db.execute(
            sa.text(
                """
                SELECT f.storage_path, f.mime_type, f.size_bytes
                FROM seller_offer_files f JOIN seller_offers o ON o.id = f.offer_id
                WHERE o.company_id = :id AND f.kind = 'image'
                ORDER BY f.id LIMIT 4
                """
            ),
            {"id": company_id},
        ).mappings().all()
        for shot in shots:
            db.execute(
                sa.text(
                    """
                    INSERT INTO company_media (company_id, storage_path, mime_type,
                                               size_bytes, created_at)
                    VALUES (:id, :path, :mime, :size, :created)
                    """
                ),
                {
                    "id": company_id,
                    "path": shot["storage_path"],
                    "mime": shot["mime_type"] or "image/jpeg",
                    "size": shot["size_bytes"] or 250_000,
                    "created": _ago(days=RNG.randrange(5, 120)),
                },
            )
            gallery += 1
        db.commit()

    db.commit()
    print(f"media: {covers} covers, {gallery} gallery images")


# ══════════════════════════════════════════════════════════════════════════════
# 4 — Factory RFQs + manufacturer chat
# ══════════════════════════════════════════════════════════════════════════════

_RFQ_STATUS_PLAN = ["quoted", "in_progress", "viewed", "submitted", "closed",
                    "in_progress", "quoted", "submitted", "rejected", "viewed"]

_RFQ_PAYMENT = ["Аккредитив (L/C)", "50% предоплата, 50% по факту отгрузки",
                "100% предоплата", "Отсрочка 30 банковских дней"]
_RFQ_VALIDITY = ["7 дней", "14 дней", "30 дней"]
_RFQ_GUARANTEE = ["Банковская гарантия 5%", "Гарантия качества по спецификации",
                  "Не требуется"]
_RFQ_INSPECTION = ["Входной контроль на нашей стороне", "SGS перед отгрузкой",
                   "Протокол испытаний завода"]
_RFQ_EXTRA = [
    "Просим подтвердить возможность отгрузки партиями по 20 т ежемесячно.",
    "Требуется сертификат происхождения для таможенного оформления.",
    "Нужна тара биг-бэг 1000 кг на паллетах, паллеты возвратные.",
    "Рассматриваем годовой контракт при подтверждении стабильного ПТР.",
]

_MFR_CHAT = [
    ("buyer", "Добрый день! Направили запрос по марке — подтвердите, пожалуйста, доступный объём на квартал."),
    ("mfr", "Здравствуйте! Запрос получили, передали в отдел сбыта. Объём подтверждаем, готовим коммерческое предложение."),
    ("buyer", "Спасибо. Уточните, входит ли доставка до Ташкента в указанную цену?"),
    ("mfr", "Цена указана на условиях FCA завод. Доставку можем организовать через партнёрскую логистику, посчитаем отдельно."),
    ("buyer", "Принято, ждём КП с обоими вариантами."),
]


def seed_factory_rfqs(db: Session, companies: dict[str, dict]) -> None:
    # Additive re-runs would collide on the unique `number`; these rows are a set,
    # not a top-up, so an existing set is left alone (use --reset to rebuild).
    if db.execute(sa.text("SELECT 1 FROM factory_rfqs LIMIT 1")).first():
        print("factory RFQs: already seeded")
        return
    # An RFQ hangs off a listing (`offer_id` is NOT NULL), so only a manufacturer
    # that actually sells can receive one. Most companies carrying the manufacturer
    # role here are converters — they make finished goods and BUY resin, so they
    # have no offers; selecting on the role alone silently dropped most of the plan.
    sellers = db.execute(
        sa.text(
            """
            SELECT o.company_id, o.id AS offer_id, o.price, o.grade_text, o.polymer_type
            FROM seller_offers o
            JOIN company_business_roles r
              ON r.company_id = o.company_id AND r.role = 'manufacturer'
            JOIN companies c ON c.id = o.company_id AND c.status = 'verified'
            WHERE o.status = 'approved'
            ORDER BY o.company_id, o.id
            """
        )
    ).mappings().all()
    by_company: dict[int, list] = {}
    for row in sellers:
        by_company.setdefault(int(row["company_id"]), []).append(row)
    listings = [(cid, offers) for cid, offers in by_company.items()]

    by_id = {int(c["id"]): c for c in companies.values()}
    buyers = [c for c in companies.values() if c["status"] == "verified" and c["account_id"]]
    if not listings or len(buyers) < 2:
        print("factory RFQs: no manufacturer listings/buyers")
        return

    year = _now().year
    made = docs = 0
    for i, status in enumerate(_RFQ_STATUS_PLAN):
        company_id, offers = listings[i % len(listings)]
        mfr = by_id.get(company_id)
        if mfr is None:
            continue
        offer = offers[i % len(offers)]
        buyer = next(
            (b for b in buyers[(i * 3) % len(buyers):] + buyers if b["id"] != mfr["id"]), None
        )
        if buyer is None:
            continue

        created = _ago(days=RNG.randrange(2, 110), hours=RNG.randrange(0, 22))
        rfq_id = db.execute(
            sa.text(
                """
                INSERT INTO factory_rfqs (
                    number, buyer_company_id, manufacturer_company_id, offer_id,
                    created_by_user_account_id, quantity, qty_unit, target_price, currency,
                    incoterms, destination_port, desired_delivery_date, payment_method,
                    offer_validity, performance_guarantee, inspection_requirement,
                    additional_requirements, contact_name, contact_position, contact_email,
                    contact_phone, contact_telegram, status, created_at, updated_at)
                VALUES (
                    :number, :buyer, :mfr, :offer_id, :account_id, :qty, 'MT', :target, 'USD',
                    :incoterms, :port, :delivery, :payment, :validity, :guarantee, :inspection,
                    :extra, :contact_name, :position, :email, :phone, :tg, :status,
                    :created, :updated)
                RETURNING id
                """
            ),
            {
                "number": f"FRQ-{year}-{900000 + i:06d}",
                "buyer": buyer["id"],
                "mfr": mfr["id"],
                "offer_id": offer["offer_id"],
                "account_id": buyer["account_id"],
                "qty": RNG.choice([60, 100, 150, 200, 300, 500]),
                "target": round(float(offer["price"] or 1200) * RNG.uniform(0.94, 1.01), 2),
                "incoterms": RNG.choice(["FCA", "DAP", "CPT", "EXW"]),
                "port": RNG.choice(["Ташкент", "Андижан", "Самарканд", "Термез (транзит)"]),
                "delivery": (created + datetime.timedelta(days=RNG.randrange(20, 70))).date(),
                "payment": RNG.choice(_RFQ_PAYMENT),
                "validity": RNG.choice(_RFQ_VALIDITY),
                "guarantee": RNG.choice(_RFQ_GUARANTEE),
                "inspection": RNG.choice(_RFQ_INSPECTION),
                "extra": RNG.choice(_RFQ_EXTRA),
                "contact_name": buyer["contact_name"] or "Контактное лицо",
                "position": RNG.choice(["Директор по закупкам", "Менеджер по снабжению",
                                        "Коммерческий директор", "Технолог"]),
                "email": f"purchasing@{str(buyer['short_name']).split()[0].lower()}.uz",
                "phone": buyer["contact_phone"] or "+998900000000",
                "tg": None,
                "status": status,
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(0, 6)),
            },
        ).scalar_one()
        made += 1

        # Compliance pack the manufacturer asked for — present once they engaged.
        if status in ("in_progress", "quoted", "closed"):
            for kind, label in (
                ("registration_certificate", "Свидетельство о регистрации.pdf"),
                ("tax_id", "Справка о постановке на учёт (ИНН).pdf"),
                ("bank_details", "Банковские реквизиты.pdf"),
            ):
                db.execute(
                    sa.text(
                        """
                        INSERT INTO factory_rfq_documents (factory_rfq_id, kind, file_name,
                                                           mime_type, size_bytes, storage_path,
                                                           created_at)
                        VALUES (:rfq, :kind, :name, 'application/pdf', :size, :path, :created)
                        """
                    ),
                    {
                        "rfq": rfq_id,
                        "kind": kind,
                        "name": label,
                        "size": RNG.randrange(90_000, 700_000),
                        "path": f"factory-rfqs/{rfq_id}/{kind}.pdf",
                        "created": created + datetime.timedelta(hours=3),
                    },
                )
                docs += 1

    db.commit()

    # ── buyer ↔ manufacturer threads ─────────────────────────────────────────
    # A thread is a direct enquiry to the factory, not tied to a listing, so every
    # company carrying the manufacturer role can hold one.
    directory = [
        c for c in companies.values()
        if c["status"] == "verified" and "manufacturer" in (c["roles"] or [])
    ]
    threads = msgs = 0
    for i, mfr in enumerate(directory[:12]):
        buyer = next((b for b in buyers[(i * 5) % len(buyers):] + buyers if b["id"] != mfr["id"]), None)
        if buyer is None:
            continue
        exists = db.execute(
            sa.text(
                """
                SELECT id FROM manufacturer_threads
                WHERE buyer_company_id = :b AND manufacturer_company_id = :m
                """
            ),
            {"b": buyer["id"], "m": mfr["id"]},
        ).scalar()
        if exists:
            continue
        opened = _ago(days=RNG.randrange(3, 80))
        thread_id = db.execute(
            sa.text(
                """
                INSERT INTO manufacturer_threads (buyer_company_id, manufacturer_company_id,
                                                  created_by_user_account_id, created_at, updated_at)
                VALUES (:b, :m, :account_id, :created, :created)
                RETURNING id
                """
            ),
            {"b": buyer["id"], "m": mfr["id"], "account_id": buyer["account_id"], "created": opened},
        ).scalar_one()
        threads += 1
        stamp = opened
        for side, body in _MFR_CHAT[: RNG.randrange(3, len(_MFR_CHAT) + 1)]:
            stamp += datetime.timedelta(hours=RNG.randrange(2, 20))
            db.execute(
                sa.text(
                    """
                    INSERT INTO manufacturer_messages (thread_id, author_account_id,
                                                       author_company_id, body, created_at)
                    VALUES (:t, :account_id, :company_id, :body, :created)
                    """
                ),
                {
                    "t": thread_id,
                    "account_id": buyer["account_id"] if side == "buyer" else mfr["account_id"],
                    "company_id": buyer["id"] if side == "buyer" else mfr["id"],
                    "body": body,
                    "created": stamp,
                },
            )
            msgs += 1
    db.commit()
    print(f"factory RFQs: {made} (+{docs} documents), manufacturer chat: {threads} threads / {msgs} messages")


# ══════════════════════════════════════════════════════════════════════════════
# 5 — Logistics requests (carrier broadcast) + replies
# ══════════════════════════════════════════════════════════════════════════════

_CARGO = [
    ("Полипропилен T30S в биг-бэгах", 120, "Биг-бэг 1000 кг на паллетах"),
    ("ПЭВП F7000, трубная марка", 200, "Биг-бэг 1250 кг"),
    ("ПВХ суспензионный SG-5", 80, "Мешки 25 кг на паллетах"),
    ("ПЭТ-гранулят бутылочный", 150, "Октабины"),
    ("ЛПЭНП LL0209AA", 60, "Мешки 25 кг"),
    ("АБС-пластик, импорт из Кореи", 40, "Мешки 25 кг, контейнер 40'"),
    ("ПЭНП плёночная марка 2420D", 100, "Биг-бэг 1000 кг"),
    ("Полистирол GPPS", 45, "Мешки 25 кг на паллетах"),
]
_SPECIAL = [
    "Требуется крытый транспорт, груз боится влаги.",
    "Нужна страховка груза на полную стоимость.",
    "Погрузка силами отправителя, выгрузка — наша.",
    "Требуется таможенное оформление под ключ.",
    None,
]
_ROUTES = [
    ("CN", "Шанхай", "UZ", "Ташкент"), ("IR", "Бендер-Аббас", "UZ", "Ташкент"),
    ("RU", "Москва", "UZ", "Ташкент"), ("KZ", "Алматы", "UZ", "Ташкент"),
    ("UZ", "Кунград", "UZ", "Андижан"), ("UZ", "Гузар", "UZ", "Фергана"),
    ("TR", "Стамбул", "UZ", "Самарканд"), ("UZ", "Навои", "KZ", "Шымкент"),
]
_LOG_STATUS_PLAN = ["quoted", "in_progress", "viewed", "submitted",
                    "closed", "quoted", "submitted", "rejected"]
_LOG_CHAT = [
    ("buyer", "Здравствуйте! Нужна ставка на этот маршрут, груз готов к отгрузке."),
    ("carrier", "Добрый день! Маршрут работаем регулярно. Уточните вес брутто и тип упаковки — посчитаем ставку."),
    ("buyer", "Вес и упаковка указаны в заявке. Интересует срок доставки «дверь-дверь»."),
    ("carrier", "Транзит 12–14 дней, включая таможенное оформление. Ставку и график направим сегодня."),
]


def seed_logistics_requests(db: Session, companies: dict[str, dict]) -> None:
    if db.execute(sa.text("SELECT 1 FROM logistics_requests LIMIT 1")).first():
        print("logistics: already seeded")
        return
    carriers = [
        c for c in companies.values()
        if c["status"] == "verified" and "logistics_provider" in (c["roles"] or [])
    ]
    buyers = [
        c for c in companies.values()
        if c["status"] == "verified" and c["account_id"]
        and "logistics_provider" not in (c["roles"] or [])
    ]
    if not carriers or not buyers:
        print("logistics requests: no carriers/buyers")
        return

    year = _now().year
    made = threads = msgs = 0
    for i, status in enumerate(_LOG_STATUS_PLAN):
        buyer = buyers[i % len(buyers)]
        cargo, volume, packaging = _CARGO[i % len(_CARGO)]
        from_country, from_city, to_country, to_city = _ROUTES[i % len(_ROUTES)]
        created = _ago(days=RNG.randrange(2, 90), hours=RNG.randrange(0, 22))

        request_id = db.execute(
            sa.text(
                """
                INSERT INTO logistics_requests (
                    number, buyer_company_id, created_by_user_account_id, cargo_name,
                    volume, volume_unit, packaging_type, special_requirements,
                    from_country, from_city, to_country, to_city, contact_phone,
                    status, created_at, updated_at)
                VALUES (:number, :buyer, :account_id, :cargo, :volume, 'MT', :packaging,
                        :special, :from_country, :from_city, :to_country, :to_city,
                        :phone, :status, :created, :updated)
                RETURNING id
                """
            ),
            {
                "number": f"LOG-{year}-{900000 + i:06d}",
                "buyer": buyer["id"],
                "account_id": buyer["account_id"],
                "cargo": cargo,
                "volume": volume,
                "packaging": packaging,
                "special": RNG.choice(_SPECIAL),
                "from_country": from_country,
                "from_city": from_city,
                "to_country": to_country,
                "to_city": to_city,
                "phone": buyer["contact_phone"],
                "status": status,
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(0, 5)),
            },
        ).scalar_one()
        made += 1

        # A broadcast reaches every carrier; the ones that engaged have a thread.
        if status == "submitted":
            continue
        for carrier in carriers[: 1 if status in ("viewed", "rejected") else len(carriers)]:
            opened = created + datetime.timedelta(hours=RNG.randrange(2, 20))
            thread_id = db.execute(
                sa.text(
                    """
                    INSERT INTO logistics_request_threads (logistics_request_id,
                                                           carrier_company_id,
                                                           created_by_user_account_id,
                                                           created_at, updated_at)
                    VALUES (:r, :c, :account_id, :created, :created)
                    RETURNING id
                    """
                ),
                {"r": request_id, "c": carrier["id"], "account_id": carrier["account_id"],
                 "created": opened},
            ).scalar_one()
            threads += 1
            stamp = opened
            for side, body in _LOG_CHAT[: RNG.randrange(2, len(_LOG_CHAT) + 1)]:
                stamp += datetime.timedelta(hours=RNG.randrange(1, 16))
                db.execute(
                    sa.text(
                        """
                        INSERT INTO logistics_request_messages (thread_id, author_account_id,
                                                                author_company_id, body, created_at)
                        VALUES (:t, :account_id, :company_id, :body, :created)
                        """
                    ),
                    {
                        "t": thread_id,
                        "account_id": buyer["account_id"] if side == "buyer" else carrier["account_id"],
                        "company_id": buyer["id"] if side == "buyer" else carrier["id"],
                        "body": body,
                        "created": stamp,
                    },
                )
                msgs += 1
    db.commit()
    print(f"logistics: {made} requests, {threads} carrier threads, {msgs} messages")


# ══════════════════════════════════════════════════════════════════════════════
# 6 — Laboratory requests + replies
# ══════════════════════════════════════════════════════════════════════════════

_LAB_STUDIES = [
    ("Входной контроль партии", ["ptr", "density"], "Подтвердить соответствие паспорту поставщика."),
    ("Идентификация марки", ["ir_spectroscopy"], "Определить марку неизвестного сырья на складе."),
    ("Полный анализ", ["ptr", "density", "ash", "moisture"], "Комплексная проверка перед годовым контрактом."),
    ("Термический анализ", ["dsc"], "Проверить температуру плавления для настройки экструдера."),
    ("Контроль влажности", ["moisture"], "Партия шла морем, есть подозрение на отсыревание."),
    ("Механические испытания", ["tensile", "impact"], "Проверить прочность для трубной продукции."),
]
_LAB_STATUS_PLAN = ["quoted", "in_progress", "viewed", "submitted", "closed", "rejected"]
_LAB_CHAT = [
    ("buyer", "Добрый день! Нужен анализ партии — сроки и стоимость?"),
    ("lab", "Здравствуйте! Стандартный срок 3 рабочих дня, экспресс — 24 часа. Пришлите образец 500 г."),
    ("buyer", "Образец подготовим сегодня, курьером завтра. Протокол нужен с печатью для таможни."),
    ("lab", "Принято. Протокол выдаём на бланке с аттестатом аккредитации — для таможни подходит."),
]


def seed_lab_requests(db: Session, companies: dict[str, dict]) -> None:
    if db.execute(sa.text("SELECT 1 FROM lab_requests LIMIT 1")).first():
        print("laboratory: already seeded")
        return
    labs = [
        c for c in companies.values()
        if c["status"] == "verified" and "laboratory" in (c["roles"] or [])
    ]
    buyers = [
        c for c in companies.values()
        if c["status"] == "verified" and c["account_id"] and "laboratory" not in (c["roles"] or [])
    ]
    if not labs or not buyers:
        print("lab requests: no laboratories/buyers")
        return

    grades = db.execute(
        sa.text("SELECT id, product_id, code FROM product_grades ORDER BY id")
    ).mappings().all()
    year = _now().year
    made = threads = msgs = 0

    for i, status in enumerate(_LAB_STATUS_PLAN):
        buyer = buyers[(i * 4) % len(buyers)]
        study, methods, purpose = _LAB_STUDIES[i % len(_LAB_STUDIES)]
        grade = grades[i % len(grades)] if grades else None
        created = _ago(days=RNG.randrange(2, 80), hours=RNG.randrange(0, 22))

        request_id = db.execute(
            sa.text(
                """
                INSERT INTO lab_requests (
                    number, buyer_company_id, created_by_user_account_id, product_id,
                    product_text, grade_text, study_type, methods, sample_qty, comment,
                    purpose, is_urgent, desired_date, contact_name, contact_email,
                    contact_phone, status, created_at, updated_at)
                VALUES (:number, :buyer, :account_id, :product_id, :product_text, :grade,
                        :study, CAST(:methods AS jsonb), :qty, :comment, :purpose, :urgent,
                        :desired, :contact_name, :email, :phone, :status, :created, :updated)
                RETURNING id
                """
            ),
            {
                "number": f"LBR-{year}-{900000 + i:06d}",
                "buyer": buyer["id"],
                "account_id": buyer["account_id"],
                "product_id": int(grade["product_id"]) if grade else None,
                "product_text": f"Полимерное сырьё {grade['code']}" if grade else "Полимерное сырьё",
                "grade": str(grade["code"]) if grade else None,
                "study": study,
                "methods": json.dumps(methods),
                "qty": RNG.choice(["500 г", "1 кг", "2 кг"]),
                "comment": "Образец отобран из партии по правилам ГОСТ, упакован в двойной пакет.",
                "purpose": purpose,
                "urgent": i % 3 == 0,
                "desired": (created + datetime.timedelta(days=RNG.randrange(3, 21))).date(),
                "contact_name": buyer["contact_name"],
                "email": f"lab@{str(buyer['short_name']).split()[0].lower()}.uz",
                "phone": buyer["contact_phone"],
                "status": status,
                "created": created,
                "updated": created + datetime.timedelta(days=RNG.randrange(0, 4)),
            },
        ).scalar_one()
        made += 1

        if status == "submitted":
            continue
        for lab in labs:
            opened = created + datetime.timedelta(hours=RNG.randrange(2, 18))
            thread_id = db.execute(
                sa.text(
                    """
                    INSERT INTO lab_request_threads (lab_request_id, laboratory_company_id,
                                                     created_by_user_account_id,
                                                     created_at, updated_at)
                    VALUES (:r, :l, :account_id, :created, :created)
                    RETURNING id
                    """
                ),
                {"r": request_id, "l": lab["id"], "account_id": lab["account_id"],
                 "created": opened},
            ).scalar_one()
            threads += 1
            stamp = opened
            for side, body in _LAB_CHAT[: RNG.randrange(2, len(_LAB_CHAT) + 1)]:
                stamp += datetime.timedelta(hours=RNG.randrange(1, 14))
                db.execute(
                    sa.text(
                        """
                        INSERT INTO lab_request_messages (thread_id, author_account_id,
                                                          author_company_id, body, created_at)
                        VALUES (:t, :account_id, :company_id, :body, :created)
                        """
                    ),
                    {
                        "t": thread_id,
                        "account_id": buyer["account_id"] if side == "buyer" else lab["account_id"],
                        "company_id": buyer["id"] if side == "buyer" else lab["id"],
                        "body": body,
                        "created": stamp,
                    },
                )
                msgs += 1
    db.commit()
    print(f"laboratory: {made} requests, {threads} lab threads, {msgs} messages")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════


def seed_showcase_profiles(*, reset: bool = False, skip_media: bool = False) -> None:
    db = SessionLocal()
    try:
        if reset:
            for table in _RESET_TABLES:
                db.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 — fixed literal list
            db.execute(sa.text("UPDATE companies SET cover_storage_path = NULL"))
            db.commit()
            print("reset: cleared the role-track tables")

        companies = _companies(db)
        if not companies:
            print("no companies — run seed_showcase first")
            return

        seed_profiles(db, companies)
        seed_reviews(db, companies)
        if not skip_media:
            seed_media(db, companies)
        seed_factory_rfqs(db, companies)
        seed_logistics_requests(db, companies)
        seed_lab_requests(db, companies)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the role-specific showcase content.")
    parser.add_argument("--reset", action="store_true", help="clear these tables first")
    parser.add_argument("--skip-media", action="store_true", help="skip cover rendering")
    args = parser.parse_args()
    seed_showcase_profiles(reset=args.reset, skip_media=args.skip_media)
    return 0


if __name__ == "__main__":
    sys.exit(main())
