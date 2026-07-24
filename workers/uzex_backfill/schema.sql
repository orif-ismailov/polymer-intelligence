-- UZEX Offer Archive Backfill Worker — standalone schema.
--
-- Additive-only. No foreign keys to any application table. Every statement is
-- idempotent (IF NOT EXISTS / ON CONFLICT), so applying this on every startup is
-- safe and never mutates existing rows.

CREATE TABLE IF NOT EXISTS uzex_raw_offers (
    id             BIGSERIAL PRIMARY KEY,
    source         TEXT NOT NULL DEFAULT 'uzex_offer_detail',
    external_id    BIGINT NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status    INT,
    final_url      TEXT,
    status         TEXT NOT NULL,          -- ok | not_found | fetch_failed | parse_empty
    fields         JSONB,                  -- {label: value} as parsed
    raw_html       BYTEA,                  -- gzip; NULL except anomaly cases (see raw_html policy)
    content_hash   TEXT,                   -- sha256 of normalized fields JSON (sentinel for non-ok)
    UNIQUE (source, external_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_uzex_raw_offers_ext ON uzex_raw_offers (external_id);
CREATE INDEX IF NOT EXISTS idx_uzex_raw_offers_fields ON uzex_raw_offers USING gin (fields);
-- Supports retry-failed and status counts without a full scan.
CREATE INDEX IF NOT EXISTS idx_uzex_raw_offers_status ON uzex_raw_offers (status);

CREATE TABLE IF NOT EXISTS uzex_backfill_progress (
    worker_name    TEXT PRIMARY KEY,
    last_id        BIGINT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS uzex_discovered_labels (
    label          TEXT PRIMARY KEY,
    first_seen_id  BIGINT,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
