"""
Dev-only DEMO data seed — populates the dashboard with realistic sample rows so
every Surface-B screen (feed, requests, prices, alerts, sources) shows content
during local development and the Phase-4 acceptance drill.

NOT wired into the compose startup — run manually:

    docker compose -f deploy/docker-compose.dev.yml exec api python -m app.seed.seed_demo
    # or, from a host venv with DATABASE_URL pointing at the dev DB:
    cd backend && python -m app.seed.seed_demo

Idempotent: keyed off the sentinel source name prefix "DEMO —". Re-running is a
no-op once seeded. To re-seed from scratch, delete the DEMO rows first:

    DELETE FROM signals      WHERE source_id IN (SELECT id FROM sources WHERE name LIKE 'DEMO —%');
    DELETE FROM price_points WHERE source_id IN (SELECT id FROM sources WHERE name LIKE 'DEMO —%');
    DELETE FROM requests     WHERE number LIKE 'REQ-DEMO-%';
    DELETE FROM alert_rules  WHERE name LIKE 'DEMO —%';
    DELETE FROM clients      WHERE company_name LIKE 'DEMO —%';
    DELETE FROM sources      WHERE name LIKE 'DEMO —%';

WARNING: dev/demo only. Never run against production.
"""

from __future__ import annotations

import datetime
import decimal

import sqlalchemy as sa

from app.core.db import SessionLocal

_SENTINEL = "DEMO —"
_UTC = datetime.UTC


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=_UTC)


def seed_demo() -> bool:
    """Seed demo rows. Returns True if data was created, False if already present."""
    db = SessionLocal()
    try:
        existing = db.execute(
            sa.text("SELECT id FROM sources WHERE name LIKE :p LIMIT 1"),
            {"p": f"{_SENTINEL}%"},
        ).first()
        if existing is not None:
            print("Demo data already present (sentinel source found) — nothing to do.")
            return False

        now = _now()

        # ── Sources ─────────────────────────────────────────────────────────
        # One healthy website (enabled), one healthy RSS, one pending channel
        # (disabled — shows the "Pending activation (Phase 5)" state on /sources).
        # WR-08: include config column so the enabled html_table source has a
        # valid URL/table_selector when the adapter's fetch() is called.
        # Without config the adapter returns [] silently (null config = empty url).
        website_id = db.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, url, country, is_enabled,
                                     config, last_test_ok_at, last_success_at, consecutive_failures)
                VALUES ('website', 'html_table', :name, 'https://example.uz/prices',
                        'UZ', true,
                        '{"url": "https://example.uz/prices", "table_selector": "table"}'::jsonb,
                        :now, :now, 0)
                RETURNING id
                """
            ),
            {"name": f"{_SENTINEL} Uzbek Polymer Exchange", "now": now},
        ).scalar_one()

        # WR-08: include config for RSS source too
        db.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, url, country, is_enabled,
                                     config, last_test_ok_at, last_success_at, consecutive_failures)
                VALUES ('rss', 'rss', :name, 'https://example.uz/feed.xml',
                        'UZ', true,
                        '{"url": "https://example.uz/feed.xml", "currency_default": "USD"}'::jsonb,
                        :now, :now, 0)
                """
            ),
            {"name": f"{_SENTINEL} Market News RSS", "now": now},
        )
        db.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, url, country, is_enabled,
                                     consecutive_failures)
                VALUES ('telegram_channel', 'telegram_channel', :name,
                        'https://t.me/demo_polymers', 'UZ', false, 0)
                """
            ),
            {"name": f"{_SENTINEL} Telegram Channel (pending)"},
        )

        # ── Client (for purchase requests; telegram_user_id set so Contact Buyer works) ─
        client_id = db.execute(
            sa.text(
                """
                INSERT INTO clients (telegram_user_id, phone, company_name, contact_name,
                                     language, is_blocked, created_at)
                VALUES (777000111, '+998901234567', :company, 'Alisher Karimov',
                        'ru', false, :now)
                RETURNING id
                """
            ),
            {"company": f"{_SENTINEL} TashPlast LLC", "now": now},
        ).scalar_one()

        # ── Signals (origin='signal' half of v_live_feed) ──────────────────
        signal_kinds = ["buy_request", "sell_offer", "deal", "price_quote"]
        urgencies = ["low", "medium", "high"]
        regions = ["Tashkent", "Samarkand", "Andijan", "Fergana", "Bukhara"]
        base_price = {1: 1180, 2: 1240, 3: 1310, 4: 1290, 5: 980, 6: 1150, 7: 1420, 8: 1560}

        n_signals = 45
        for i in range(n_signals):
            product_id = (i % 8) + 1
            kind = signal_kinds[i % len(signal_kinds)]
            urgency = urgencies[i % len(urgencies)]
            price = base_price[product_id] + (i % 11) * 7 - 35
            volume = 20 + (i % 9) * 15
            event_at = now - datetime.timedelta(hours=i * 5, minutes=(i * 13) % 60)
            db.execute(
                sa.text(
                    """
                    INSERT INTO signals (kind, source_id, product_id, grade_text, volume,
                                         volume_unit, price, currency, region, urgency,
                                         status, event_at, created_at)
                    VALUES (:kind, :source_id, :product_id, :grade, :volume, 'MT',
                            :price, 'USD', :region, :urgency, 'new', :event_at, :now)
                    """
                ),
                {
                    "kind": kind,
                    "source_id": website_id,
                    "product_id": product_id,
                    "grade": f"Grade {chr(65 + (i % 4))}",
                    "volume": decimal.Decimal(volume),
                    "price": decimal.Decimal(price),
                    "region": regions[i % len(regions)],
                    "urgency": urgency,
                    "event_at": event_at,
                    "now": now,
                },
            )

        # ── Purchase requests (origin='request' half of v_live_feed) ───────
        req_statuses = ["new", "viewed", "in_progress", "offer_sent", "matched", "new"]
        for i in range(6):
            product_id = (i % 8) + 1
            status = req_statuses[i % len(req_statuses)]
            urgency = urgencies[i % len(urgencies)]
            target = base_price[product_id] - 20 - (i % 5) * 10
            created = now - datetime.timedelta(days=i, hours=(i * 7) % 24)
            db.execute(
                sa.text(
                    """
                    INSERT INTO requests (number, client_id, product_id, grade_text,
                                          polymer_type, volume, volume_unit, target_price,
                                          currency, incoterms, destination_country,
                                          port_or_city, validity_days, urgency, comment,
                                          status, ai, created_at, updated_at)
                    VALUES (:number, :client_id, :product_id, :grade, :ptype, :volume, 'MT',
                            :target, 'USD', 'CIF', 'UZ', 'Tashkent', 14, :urgency,
                            :comment, :status, '{}'::jsonb, :created, :created)
                    """
                ),
                {
                    "number": f"REQ-DEMO-{i + 1:03d}",
                    "client_id": client_id,
                    "product_id": product_id,
                    "grade": f"Grade {chr(65 + (i % 3))}",
                    "ptype": "PP" if product_id == 1 else "PE",
                    "volume": decimal.Decimal(50 + i * 25),
                    "target": decimal.Decimal(target),
                    "urgency": urgency,
                    "comment": "Looking for prompt shipment, flexible on grade.",
                    "status": status,
                    "created": created,
                },
            )

        # ── Price series (drives the /prices chart + request price analysis) ─
        for product_id in (1, 2):
            for market in ("UZEX", "UZ"):
                for d in range(40):
                    observed = (now - datetime.timedelta(days=40 - d)).date()
                    drift = (d * 4) + (product_id * 15) + (7 if market == "UZEX" else 0)
                    avg = base_price[product_id] + drift - 60
                    db.execute(
                        sa.text(
                            """
                            INSERT INTO price_points (kind, source_id, product_id, market,
                                                      currency, unit, price_avg, price_min,
                                                      price_max, deals_count, observed_on,
                                                      created_at)
                            VALUES ('deal_avg', :source_id, :product_id, :market, 'USD', 'MT',
                                    :avg, :pmin, :pmax, :deals, :observed, :now)
                            """
                        ),
                        {
                            "source_id": website_id,
                            "product_id": product_id,
                            "market": market,
                            "avg": decimal.Decimal(avg),
                            "pmin": decimal.Decimal(avg - 25),
                            "pmax": decimal.Decimal(avg + 25),
                            "deals": 3 + (d % 6),
                            "observed": observed,
                            "now": now,
                        },
                    )

        # ── Alert rule (shows in the RuleBuilder list on /alerts) ───────────
        admin_id = db.execute(
            sa.text("SELECT id FROM staff_users WHERE role = 'admin' ORDER BY id LIMIT 1")
        ).scalar()
        db.execute(
            sa.text(
                """
                INSERT INTO alert_rules (kind, name, condition, channels, is_enabled, created_by, created_at)
                VALUES ('large_volume', :name,
                        '{"product_ids": [1], "min_volume": 100, "urgency": ["high"]}'::jsonb,
                        '[{"channel": "telegram_dm", "chat_id": "777000111"}]'::jsonb,
                        true, :created_by, :now)
                """
            ),
            {"name": f"{_SENTINEL} Large PP volume", "created_by": admin_id, "now": now},
        )

        db.commit()
        print(
            "Demo data seeded: 3 sources, 1 client, "
            f"{n_signals} signals, 6 requests, 160 price points, 1 alert rule."
        )
        return True
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding DEMO dashboard data...")
    seed_demo()
    print("Done.")
