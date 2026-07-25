# Polymer Intelligence — Архитектура базы данных

PostgreSQL 16+. Фаза 1: внутренний рынок Узбекистана (UZEX + Telegram-мониторинг + заявки клиентов), с заделом под Фазу 2 (внешний контекст, AI-аналитика).

## Принципы

1. **Сырьё неизменяемо.** Всё входящее сохраняется в `raw_items` до парсинга. Парсинг можно повторять (новый промпт, исправленный скрейпер) без потери данных.
2. **Один поток сигналов.** Всё распарсенное нормализуется в `signals` — лента дашборда, алерты и аналитика работают с одной таблицей.
3. **Заявки клиентов — транзакционные данные.** Отдельный контур со статусной машиной и SLA, не смешивается с шумом мониторинга.
4. **`price_points` — производный слой.** Считается из сделок и внешних индексов; UI графиков читает только его.
5. **AI-результаты версионируются.** Каждая LLM-оценка хранит модель и версию промпта — возможен пересчёт.
6. **Связывание контрагентов не блокирует запись.** `counterparty_id` nullable, уточняется фоновым процессом.

## Схема потока данных

```
UZEX scraper ─┐
Telegram userbot ─┤→ raw_items → [parser: rules/LLM] → signals ─┬→ alerts → deliveries
SunSirs/DCE cron ─┘                                             ├→ price_points (агрегация)
                                                                └→ counterparty linking
Web App клиента → requests (+ зеркальный signal через view/триггер)
reports ← price_points + signals (генерация утренних/недельных отчётов)
```

---

## 1. Справочники

```sql
-- Типы полимеров: PP, HDPE, LDPE, LLDPE, PVC, PET, PS, ABS...
CREATE TABLE products (
    id              smallserial PRIMARY KEY,
    code            text NOT NULL UNIQUE,          -- 'PP', 'HDPE'
    name_ru         text NOT NULL,                 -- 'Полипропилен'
    name_uz         text,
    category        text NOT NULL DEFAULT 'polymer',
    sort_order      int  NOT NULL DEFAULT 0,
    is_active       boolean NOT NULL DEFAULT true
);

-- Марки/грейды: T30S, H030 SG, F7000, 2420D...
CREATE TABLE product_grades (
    id              serial PRIMARY KEY,
    product_id      smallint NOT NULL REFERENCES products(id),
    code            text NOT NULL,                 -- 'T30S'
    producer        text,                          -- 'Shurtan GCC', 'Sibur'
    description     text,
    UNIQUE (product_id, code)
);
-- Грейды из сырых данных приходят свободным текстом; маппинг на справочник
-- выполняет парсер, при неудаче grade_id остаётся NULL, текст сохраняется.

-- Официальные курсы валют (ЦБ РУз, ежедневный импорт).
-- Хранится только официальный курс к UZS; кросс-курсы считаются на чтении.
CREATE TABLE fx_rates (
    rate_date       date NOT NULL,
    ccy             char(3) NOT NULL,              -- 'USD', 'CNY', 'RUB'
    rate            numeric(18,6) NOT NULL,        -- сколько UZS за 1 единицу ccy
    PRIMARY KEY (rate_date, ccy)
);
-- Конвертация в UI/отчётах — на чтении; в signals/price_points всегда
-- хранится оригинальная валюта источника, пересчёт не записывается.
```

## 2. Источники и сырой слой

```sql
CREATE TYPE source_kind AS ENUM
    ('exchange', 'telegram_channel', 'website', 'webapp', 'manual', 'external_index', 'rss');

CREATE TABLE sources (
    id              serial PRIMARY KEY,
    kind            source_kind NOT NULL,          -- грубая категория для UI/фильтров
    adapter         text NOT NULL,                 -- имя адаптера из реестра:
                                                   -- 'uzex_offers', 'telegram_channel',
                                                   -- 'llm_page', 'html_table', 'rss', 'sunsirs'...
    name            text NOT NULL,                 -- 'UZEX spot (сум)', '@polymer_traders_uz'
    url             text,
    config          jsonb NOT NULL DEFAULT '{}',   -- валидируется config_schema адаптера:
                                                   -- селекторы, маппинг колонок, расписание
    country         char(2),                       -- 'UZ', 'CN', 'RU'
    group_name      text,                          -- операторская группа источников (миграция 0016, Фаза 8f-2)
    is_enabled      boolean NOT NULL DEFAULT true,
    last_test_ok_at timestamptz,                   -- конструктор: включение запрещено,
                                                   -- пока NULL (тест ни разу не прошёл)
    -- health-мониторинг (экран Sources в дашборде):
    last_fetch_at   timestamptz,
    last_success_at timestamptz,
    consecutive_failures int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- Инвариант (CHECK или валидация в сервисе):
-- is_enabled = true ⇒ last_test_ok_at IS NOT NULL.

CREATE TYPE parse_status AS ENUM ('pending', 'parsed', 'failed', 'skipped', 'irrelevant');

-- Неизменяемый сырой слой. Никогда не UPDATE-ится по содержимому.
CREATE TABLE raw_items (
    id              bigserial PRIMARY KEY,
    source_id       int NOT NULL REFERENCES sources(id),
    external_id     text,                          -- id сообщения TG, номер лота UZEX
    content         text,                          -- текст сообщения / фрагмент HTML
    payload         jsonb,                         -- структурированное сырьё, если есть
    content_hash    bytea NOT NULL,                -- sha256 для дедупликации
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    event_at        timestamptz,                   -- время события у источника
    parse_status    parse_status NOT NULL DEFAULT 'pending',
    parse_attempts  smallint NOT NULL DEFAULT 0,
    UNIQUE (source_id, content_hash)
);
CREATE INDEX ON raw_items (parse_status, fetched_at) WHERE parse_status = 'pending';
CREATE INDEX ON raw_items (source_id, fetched_at DESC);

-- Журнал LLM-разборов: что, какой моделью, почём. Позволяет перепарсивать.
CREATE TABLE parse_runs (
    id              bigserial PRIMARY KEY,
    raw_item_id     bigint NOT NULL REFERENCES raw_items(id),
    parser          text NOT NULL,                 -- 'uzex_table_v2', 'llm_extract'
    model           text,                          -- 'claude-haiku-4-5', NULL для rule-based
    prompt_version  text,
    result          jsonb,
    status          text NOT NULL,                 -- 'ok' | 'error' | 'irrelevant'
    error           text,
    tokens_in       int,
    tokens_out      int,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

## 3. Контрагенты (entity resolution)

```sql
CREATE TYPE counterparty_role AS ENUM ('buyer', 'seller', 'trader', 'producer', 'unknown');

CREATE TABLE counterparties (
    id              serial PRIMARY KEY,
    canonical_name  text NOT NULL,
    role            counterparty_role NOT NULL DEFAULT 'unknown',
    country         char(2),
    tax_id          text,                          -- ИНН, если известен (из реестра UZEX)
    notes           text,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- 'ООО Полимер Трейд', '@polytrade_uz', 'POLIMER TREYD MCHJ' → одна компания
CREATE TABLE counterparty_aliases (
    id              serial PRIMARY KEY,
    counterparty_id int NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
    alias           text NOT NULL,
    alias_norm      text NOT NULL,                 -- нормализованная форма для поиска
    source_kind     source_kind,
    confidence      real NOT NULL DEFAULT 1.0,     -- 1.0 = подтверждено вручную
    UNIQUE (alias_norm, counterparty_id)
);
CREATE INDEX ON counterparty_aliases (alias_norm);
```

## 4. Сигналы — единый поток рынка

```sql
CREATE TYPE signal_kind AS ENUM
    ('buy_request',   -- кто-то ищет товар (биржевая заявка, пост в канале, заявка клиента)
     'sell_offer',    -- предложение на продажу
     'deal',          -- заключённая сделка (реестр UZEX)
     'price_quote',   -- котировка/прайс без конкретного объёма
     'news');         -- релевантная новость рынка

CREATE TYPE price_basis AS ENUM ('EXW', 'FCA', 'FOB', 'CIF', 'CPT', 'DAP', 'DDP', 'unknown');
CREATE TYPE urgency AS ENUM ('low', 'medium', 'high');

CREATE TABLE signals (
    id              bigserial PRIMARY KEY,
    kind            signal_kind NOT NULL,
    source_id       int NOT NULL REFERENCES sources(id),
    raw_item_id     bigint REFERENCES raw_items(id),
    -- товар
    product_id      smallint REFERENCES products(id),
    grade_id        int REFERENCES product_grades(id),
    grade_text      text,                          -- как было в источнике
    -- параметры
    volume          numeric(14,3),
    volume_unit     text NOT NULL DEFAULT 'MT',
    price           numeric(14,2),
    currency        char(3),                       -- 'USD', 'UZS', 'CNY'
    price_basis     price_basis NOT NULL DEFAULT 'unknown',
    region          text,                          -- рынок/регион события
    destination     text,
    -- контрагент
    counterparty_id   int REFERENCES counterparties(id),
    counterparty_text text,                        -- сырое имя до связывания
    -- AI-обогащение (пересчитываемое)
    ai              jsonb NOT NULL DEFAULT '{}',
    /* ai: { "lead_score": 0.92, "urgency": "high", "classification": "HOT",
             "summary": "...", "model": "...", "prompt_version": "v3",
             "scored_at": "..." } */
    urgency         urgency,                       -- денормализовано из ai для индексов
    -- жизненный цикл
    status          text NOT NULL DEFAULT 'new',   -- new / viewed / processed / archived
    processed_by    int,                           -- REFERENCES staff_users(id)
    event_at        timestamptz NOT NULL,          -- когда произошло у источника
    created_at      timestamptz NOT NULL DEFAULT now(),
    extra           jsonb NOT NULL DEFAULT '{}'    -- источник-специфика (секция UZEX, лот...)
);
CREATE INDEX ON signals (kind, event_at DESC);
CREATE INDEX ON signals (product_id, event_at DESC);
CREATE INDEX ON signals (counterparty_id) WHERE counterparty_id IS NOT NULL;
CREATE INDEX ON signals (status) WHERE status = 'new';
CREATE INDEX ON signals USING gin (ai jsonb_path_ops);
-- При росте объёма: партиционирование по месяцам event_at. В Фазе 1 не нужно.
```

## 5. Клиенты и заявки (Web App)

```sql
CREATE TABLE clients (
    id              serial PRIMARY KEY,
    telegram_user_id bigint UNIQUE,                -- из initData Web App
    phone           text,
    company_name    text,
    contact_name    text,
    language        char(2) NOT NULL DEFAULT 'ru', -- 'uz' | 'ru' | 'en'
    counterparty_id int REFERENCES counterparties(id),  -- связь с intelligence-контуром
    is_blocked      boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE request_status AS ENUM
    ('new', 'viewed', 'in_progress', 'offer_sent', 'matched', 'closed', 'cancelled');

CREATE TABLE requests (
    id              serial PRIMARY KEY,
    number          text NOT NULL UNIQUE,          -- 'REQ-2026-06-12-00125'
    client_id       int NOT NULL REFERENCES clients(id),
    product_id      smallint NOT NULL REFERENCES products(id),
    grade_text      text,
    polymer_type    text,                          -- доп. поле формы из мокапа
    volume          numeric(14,3) NOT NULL,
    volume_unit     text NOT NULL DEFAULT 'MT',
    target_price    numeric(14,2),
    currency        char(3) NOT NULL DEFAULT 'USD',
    incoterms       price_basis NOT NULL DEFAULT 'unknown',
    destination_country char(2) NOT NULL DEFAULT 'UZ',
    port_or_city    text,
    desired_date    date,
    validity_days   smallint NOT NULL DEFAULT 30,
    urgency         urgency NOT NULL DEFAULT 'medium',
    comment         text,
    status          request_status NOT NULL DEFAULT 'new',
    assigned_to     int,                           -- REFERENCES staff_users(id)
    ai              jsonb NOT NULL DEFAULT '{}',   -- match_score, price_analysis...
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON requests (status, created_at DESC);
CREATE INDEX ON requests (client_id, created_at DESC);

CREATE TABLE request_files (
    id              serial PRIMARY KEY,
    request_id      int NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    telegram_file_id text,                         -- хранить файл у Telegram, не у себя
    file_name       text NOT NULL,
    mime_type       text,
    size_bytes      int,
    storage_path    text,                          -- если скачан в S3/локально
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE request_status_history (
    id              serial PRIMARY KEY,
    request_id      int NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    from_status     request_status,
    to_status       request_status NOT NULL,
    changed_by      int,                           -- NULL = система/клиент
    comment         text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Заявки в общей ленте дашборда:
CREATE VIEW v_live_feed AS
    SELECT id, 'signal' AS origin, kind::text, product_id, grade_text, volume,
           price, currency, region, urgency, status, event_at
    FROM signals
    UNION ALL
    SELECT id, 'request', 'buy_request', product_id, grade_text, volume,
           target_price, currency, destination_country, urgency,
           status::text, created_at
    FROM requests;
```

## 6. Ценовые ряды (производный слой)

```sql
CREATE TYPE price_point_kind AS ENUM
    ('deal_avg',      -- агрегат сделок UZEX за день (avg/min/max/volume)
     'offer_avg',     -- агрегат предложений
     'index',         -- внешний индекс (SunSirs CN)
     'futures');      -- фьючерс DCE

CREATE TABLE price_points (
    id              bigserial PRIMARY KEY,
    kind            price_point_kind NOT NULL,
    source_id       int NOT NULL REFERENCES sources(id),
    product_id      smallint NOT NULL REFERENCES products(id),
    grade_id        int REFERENCES product_grades(id),
    market          text NOT NULL,                 -- 'UZ', 'CN', 'DCE'
    currency        char(3) NOT NULL,
    unit            text NOT NULL DEFAULT 'MT',
    price_avg       numeric(14,2) NOT NULL,
    price_min       numeric(14,2),
    price_max       numeric(14,2),
    volume_total    numeric(14,3),
    deals_count     int,
    observed_on     date NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, source_id, product_id, grade_id, market, observed_on)
);
CREATE INDEX ON price_points (product_id, market, observed_on DESC);
-- Заполняется: (а) ночным джобом агрегации из signals kind='deal',
-- (б) напрямую cron-джобами внешних индексов. UI графиков читает только её.
```

## 7. Алерты и доставка

```sql
CREATE TYPE alert_kind AS ENUM
    ('new_hot_request', 'large_volume', 'price_spike', 'below_market_offer',
     'new_buyer', 'source_failure', 'custom');

CREATE TABLE alert_rules (
    id              serial PRIMARY KEY,
    kind            alert_kind NOT NULL,
    name            text NOT NULL,
    condition       jsonb NOT NULL,                -- {"product":"PP","volume_gte":200,...}
    channels        jsonb NOT NULL DEFAULT '[]',   -- [{"type":"telegram_dm","chat_id":...}]
    is_enabled      boolean NOT NULL DEFAULT true,
    created_by      int,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    id              bigserial PRIMARY KEY,
    kind            alert_kind NOT NULL,
    rule_id         int REFERENCES alert_rules(id),
    severity        text NOT NULL DEFAULT 'info',  -- info / warning / critical
    title           text NOT NULL,
    body            text NOT NULL,
    signal_id       bigint REFERENCES signals(id),
    request_id      int REFERENCES requests(id),
    dedupe_key      text,                          -- защита от повторных алертов
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dedupe_key)
);

CREATE TYPE delivery_channel AS ENUM ('telegram_dm', 'telegram_channel', 'webapp', 'dashboard');
CREATE TYPE delivery_status AS ENUM ('queued', 'sent', 'failed');

CREATE TABLE deliveries (
    id              bigserial PRIMARY KEY,
    alert_id        bigint REFERENCES alerts(id),
    report_id       int,                           -- REFERENCES reports(id)
    channel         delivery_channel NOT NULL,
    recipient       text NOT NULL,                 -- chat_id / channel_id / user_id
    status          delivery_status NOT NULL DEFAULT 'queued',
    telegram_message_id bigint,
    error           text,
    sent_at         timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON deliveries (status) WHERE status = 'queued';
```

## 8. Отчёты (новостной движок)

```sql
CREATE TYPE report_kind AS ENUM ('morning', 'evening', 'intraday', 'weekly', 'custom');
-- 'evening' added in migration 0014 (Phase 8c — Evening Market Brief at 18:00 Tashkent).
CREATE TYPE report_status AS ENUM ('draft', 'pending_approval', 'approved', 'published', 'rejected');

CREATE TABLE reports (
    id              serial PRIMARY KEY,
    kind            report_kind NOT NULL,
    period_start    date NOT NULL,
    period_end      date NOT NULL,
    title           text NOT NULL,
    content_md      text NOT NULL,                 -- markdown, рендерится в TG/WebApp
    data_snapshot   jsonb NOT NULL DEFAULT '{}',   -- цифры на момент генерации
    status          report_status NOT NULL DEFAULT 'draft',  -- human-in-the-loop!
    generated_by    text,                          -- модель + версия промпта
    approved_by     int,
    published_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- Публикации фиксируются в deliveries (report_id).
```

## 9. Внутренние пользователи и аудит

```sql
CREATE TYPE staff_role AS ENUM ('admin', 'analyst', 'trader', 'viewer');

CREATE TABLE staff_users (
    id              serial PRIMARY KEY,
    email           text NOT NULL UNIQUE,
    full_name       text NOT NULL,
    role            staff_role NOT NULL DEFAULT 'viewer',
    password_hash   text NOT NULL,
    telegram_user_id bigint,                       -- для DM-алертов
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id              bigserial PRIMARY KEY,
    staff_user_id   int REFERENCES staff_users(id),
    action          text NOT NULL,                 -- 'request.status_change', 'report.approve'
    entity          text NOT NULL,
    entity_id       text NOT NULL,
    details         jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Runtime operator-editable settings (migration 0015, Phase 8d). Only overrides are
-- stored; unset keys fall back to code defaults in app/services/settings_service.py
-- (news_ai_enabled, news_require_approval, report_auto_publish, llm_extract_model,
-- news_prompt_version). Per-article approval state lives in signals.ai.news.approval.
CREATE TABLE app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  int REFERENCES staff_users(id)
);
```

---

## 10. Верификация компаний и портал (R1, миграция 0017)

Модель личности v2 (ARCHITECTURE §5, поправка A1): человек = `user_accounts`
(телефон, passwordless OTP), членство в компании — через `company_members.user_account_id`.
Telegram-личности (`clients`/`sellers`) — отдельный «замороженный» мир; связь пока
дремлющая (`user_accounts.telegram_user_id`, `sellers.company_id`, `clients.company_id`,
`seller_offers.company_id` — все NULL, без логики моста в R1–R3).

Бизнес-логика в `app/services/` (company/verification/otp/event сервисы, R1 wave 4+);
шифрование PII — `app/core/crypto.py` (Fernet, ключ `VERIFICATION_ENC_KEY`);
транзакционный outbox — `domain_events` + beat-таск `dispatch_domain_events`.

```sql
-- ── ENUM-типы (14) ────────────────────────────────────────────────────────
CREATE TYPE account_status              AS ENUM ('active','blocked');
CREATE TYPE company_status              AS ENUM ('draft','pending_verification','verified','rejected','suspended','liquidated');
CREATE TYPE company_member_role         AS ENUM ('owner','manager','member');
CREATE TYPE company_member_status       AS ENUM ('active','invited','removed');
CREATE TYPE company_business_role       AS ENUM ('manufacturer','importer','trader','logistics_provider','distributor','laboratory','insurance_provider');
CREATE TYPE business_role_status        AS ENUM ('declared','confirmed','revoked');
CREATE TYPE bank_account_status         AS ENUM ('unverified','pending','verified','failed','archived');
CREATE TYPE bank_verification_method    AS ENUM ('document','e_invoice_crosscheck','bank_api','manual');
CREATE TYPE verification_case_type      AS ENUM ('onboarding','reverification','targeted');
CREATE TYPE verification_case_status    AS ENUM ('draft','submitted','checks_running','needs_info','pending_review','approved','rejected','cancelled');
CREATE TYPE verification_check_type     AS ENUM ('tax_id_format','bank_requisites','documents_complete','manual_kyb');  -- R3 +eimzo_signature; P2 +gov_registry/tax_status/vat_status
CREATE TYPE verification_check_status   AS ENUM ('pending','running','passed','warning','failed','unavailable','waived');
CREATE TYPE verification_document_kind  AS ENUM ('registration_certificate','director_id','bank_letter','license','permit','certificate','power_of_attorney','other');
CREATE TYPE document_review_status      AS ENUM ('pending_review','accepted','rejected');

-- ── Личности портала ──────────────────────────────────────────────────────
CREATE TABLE user_accounts (
    id               bigserial PRIMARY KEY,
    phone            text NOT NULL UNIQUE,            -- E.164
    name             text,
    language         char(2) NOT NULL DEFAULT 'ru',
    status           account_status NOT NULL DEFAULT 'active',
    telegram_user_id bigint UNIQUE,                   -- дремлющий мост к Mini App (frozen)
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_login_at    timestamptz
);

-- Лог отправок SMS — учёт стоимости + форензика OTP-абьюза. Коды НЕ хранятся.
CREATE TABLE sms_send_log (
    id              bigserial PRIMARY KEY,
    phone           text NOT NULL,
    purpose         text NOT NULL,                    -- 'otp'
    provider        text NOT NULL,                    -- 'console' | 'eskiz'
    provider_msg_id text,
    status          text NOT NULL,                    -- 'ok' | 'error'
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_sms_send_log_phone_created ON sms_send_log(phone, created_at);  -- дневной лимит

-- ── Реестр компаний ───────────────────────────────────────────────────────
CREATE TABLE companies (
    id                         bigserial PRIMARY KEY,
    public_id                  uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),  -- стабильная внешняя ссылка
    jurisdiction               char(2) NOT NULL DEFAULT 'UZ',
    tax_id                     text NOT NULL,          -- STIR/INN
    legal_name                 text, short_name text, legal_form text,
    legal_address              text, director_name text, registration_date date,
    registry_status            text,                   -- статус по данным гос-реестра (заполняется в P2)
    status                     company_status NOT NULL DEFAULT 'draft',
    verified_at                timestamptz, reverification_due_at timestamptz,
    counterparty_id            int REFERENCES counterparties(id),
    created_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jurisdiction, tax_id)                      -- uq_company_jurisdiction_tax_id
);

CREATE TABLE company_members (
    id                         bigserial PRIMARY KEY,
    company_id                 bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_account_id            bigint NOT NULL REFERENCES user_accounts(id),
    member_role                company_member_role NOT NULL DEFAULT 'member',
    status                     company_member_status NOT NULL DEFAULT 'active',
    invited_by_user_account_id bigint REFERENCES user_accounts(id),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, user_account_id)               -- uq_company_member
);

CREATE TABLE company_business_roles (
    id           bigserial PRIMARY KEY,
    company_id   bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role         company_business_role NOT NULL,
    status       business_role_status NOT NULL DEFAULT 'declared',
    confirmed_by int REFERENCES staff_users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, role)                           -- uq_company_business_role
);

CREATE TABLE company_bank_accounts (
    id                   bigserial PRIMARY KEY,
    company_id           bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    bank_mfo             char(5) NOT NULL, bank_name text,
    account_number_enc   bytea NOT NULL,               -- Fernet-шифртекст (app-layer, §15)
    account_last4        char(4) NOT NULL,             -- для маскирования
    currency             char(3) NOT NULL DEFAULT 'UZS',
    status               bank_account_status NOT NULL DEFAULT 'unverified',
    verification_method  bank_verification_method,
    evidence_document_id bigint REFERENCES verification_documents(id),
    verified_at timestamptz, verified_by int REFERENCES staff_users(id),
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- ── Верификация ───────────────────────────────────────────────────────────
CREATE TABLE verification_cases (
    id            bigserial PRIMARY KEY,
    company_id    bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    case_type     verification_case_type NOT NULL DEFAULT 'onboarding',
    status        verification_case_status NOT NULL DEFAULT 'draft',
    submitted_at timestamptz, decided_at timestamptz,
    decided_by    int REFERENCES staff_users(id),      -- NULL = авто/telegram-актор (детали в audit_log)
    decision_note text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_verification_cases_company_id ON verification_cases(company_id);
-- Один открытый кейс на компанию — инвариант как ограничение БД, а не логика приложения (§6.1):
CREATE UNIQUE INDEX ux_open_case ON verification_cases(company_id)
    WHERE status NOT IN ('approved','rejected','cancelled');

CREATE TABLE verification_checks (
    id          bigserial PRIMARY KEY,
    case_id     bigint NOT NULL REFERENCES verification_cases(id) ON DELETE CASCADE,
    check_type  verification_check_type NOT NULL,
    status      verification_check_status NOT NULL DEFAULT 'pending',
    result      jsonb, attempts int NOT NULL DEFAULT 0, last_error text,
    started_at timestamptz, finished_at timestamptz,
    waived_by   int REFERENCES staff_users(id), waive_reason text,
    UNIQUE (case_id, check_type)                        -- uq_verification_check
);

CREATE TABLE verification_documents (
    id                          bigserial PRIMARY KEY,
    company_id                  bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    case_id                     bigint REFERENCES verification_cases(id) ON DELETE SET NULL,
    kind                        verification_document_kind NOT NULL,
    storage_path                text NOT NULL,          -- verification/{company_id}/{token}-{name}
    mime_type text, size_bytes int, sha256 text NOT NULL,
    uploaded_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    status                      document_review_status NOT NULL DEFAULT 'pending_review',
    review_note text, reviewed_by int REFERENCES staff_users(id), reviewed_at timestamptz,
    expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_verification_documents_company_id ON verification_documents(company_id);

-- ── Транзакционный outbox (§7) ────────────────────────────────────────────
CREATE TABLE domain_events (
    id             bigserial PRIMARY KEY,
    event_type     text NOT NULL,                       -- см. app/services/event_types.py
    aggregate_type text NOT NULL, aggregate_id text NOT NULL,
    payload        jsonb NOT NULL DEFAULT '{}',
    occurred_at    timestamptz NOT NULL DEFAULT now(),
    published_at   timestamptz, attempts int NOT NULL DEFAULT 0
);
CREATE INDEX ix_outbox_unpublished ON domain_events(id) WHERE published_at IS NULL;

-- ── Мост маркетплейса (dual-origin offers, A1) ────────────────────────────
ALTER TABLE seller_offers ADD COLUMN company_id bigint REFERENCES companies(id);
ALTER TABLE seller_offers ADD COLUMN created_by_user_account_id bigint REFERENCES user_accounts(id);
ALTER TABLE seller_offers ALTER COLUMN seller_id DROP NOT NULL;   -- оффер от TG-продавца ИЛИ от компании
ALTER TABLE seller_offers ADD CONSTRAINT ck_offer_origin CHECK (seller_id IS NOT NULL OR company_id IS NOT NULL);
ALTER TABLE sellers ADD COLUMN company_id bigint REFERENCES companies(id);   -- дремлющий
ALTER TABLE clients ADD COLUMN company_id bigint REFERENCES companies(id);   -- дремлющий
```

### R2 — паритет портала (migration 0018_portal_parity, A2)

Двусторонний бридж распространяется на buy-side: заявки и запросы-по-офферу могут
исходить от TG-клиента **ИЛИ** от портальной компании-аккаунта. `client_id`
становится NULLABLE, добавляются `company_id` + `created_by_user_account_id`, а
инвариант происхождения держит CHECK — не app-логика. Плюс новый центр
уведомлений портала (`portal_notifications`): тексты никогда не хранятся готовыми —
только i18n-ключи + `params`, чтобы портал рендерил на языке читателя (ru/uz/en).

```sql
-- ── requests: dual-origin (TG-клиент ИЛИ портальная компания) ─────────────
ALTER TABLE requests ADD COLUMN company_id bigint REFERENCES companies(id);
ALTER TABLE requests ADD COLUMN created_by_user_account_id bigint REFERENCES user_accounts(id);
ALTER TABLE requests ALTER COLUMN client_id DROP NOT NULL;
ALTER TABLE requests ADD CONSTRAINT ck_request_origin
    CHECK (client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL);

-- ── offer_requests (inquiries): те же поля происхождения ──────────────────
ALTER TABLE offer_requests ADD COLUMN company_id bigint REFERENCES companies(id);
ALTER TABLE offer_requests ADD COLUMN created_by_user_account_id bigint REFERENCES user_accounts(id);
ALTER TABLE offer_requests ALTER COLUMN client_id DROP NOT NULL;
ALTER TABLE offer_requests ADD CONSTRAINT ck_inquiry_origin
    CHECK (client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL);

-- ── portal_notifications: центр уведомлений (polling-модель, SSE отложен) ──
CREATE TABLE portal_notifications (
    id              bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_account_id bigint NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    kind            text NOT NULL,                 -- расширяемо: request_status, inquiry_approved, verification_decided, offer_moderated, news_breaking…
    title_key       text NOT NULL,                 -- i18n-ключ (не готовый текст)
    body_key        text NOT NULL,                 -- i18n-ключ
    params          jsonb NOT NULL DEFAULT '{}',   -- значения для интерполяции
    entity          text,                          -- цель deep-link (тип)
    entity_id       text,                          -- цель deep-link (id)
    read_at         timestamptz,                   -- NULL ⇒ непрочитано
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- (user_account_id, read_at, id): unread-count + лента (новые сверху, скан назад)
CREATE INDEX ix_portal_notifications_account_unread
    ON portal_notifications(user_account_id, read_at, id);
```

---

## Маппинг на экраны мокапов

| Экран | Источник данных |
|---|---|
| Live Market Feed | `v_live_feed` |
| Purchase Requests (таблица + карточка) | `requests` + `clients` + `request_files`; AI-блок из `requests.ai` |
| Seller Offers | `signals WHERE kind='sell_offer'` |
| Price Trends график | `price_points` |
| AI Signals / Alerts | `alerts` + `deliveries` |
| Sources (health) | `sources` (last_success_at, consecutive_failures) |
| Top Buyer Requests / Hot Leads | `signals`/`requests` ORDER BY `ai->>'lead_score'` |
| Market News (Web App) | `reports WHERE status='published'` |
| Counterparty профиль (Фаза 2+) | `counterparties` + агрегаты по `signals` |

## Что сознательно НЕ в Фазе 1

- Партиционирование `raw_items`/`signals` — добавить при >1–2 млн строк.
- Materialized views для статистики контрагентов («repeated buyer», циклы) — Фаза 3.
- Полнотекстовый поиск по `raw_items.content` (pg_trgm/tsvector) — добавить при необходимости.
- Таблица `offers` (ответы внутренней команды на заявки клиентов) — добавить, когда определится бизнес-процесс ответа: пока неясно, отвечаете вы клиенту вручную в TG или через систему.

## Открытые вопросы для ТЗ

1. ~~Хранение файлов заявок~~ — РЕШЕНО (dev-спека §4.2): прямая загрузка на backend в S3-совместимое хранилище (MinIO), telegram_file_id — запасной путь для файлов, присланных боту.
2. **Мультиязычность отчётов:** один отчёт = одна запись или три (uz/ru/en)? Влияет на `reports`. По допущению клиентского ТЗ Фазы 1–2 — только RU.
3. ~~Курсы валют~~ — РЕШЕНО: таблица `fx_rates` добавлена в схему (см. раздел 1), источник — ЦБ РУз.
4. **Retention сырых данных:** `raw_items` растёт быстрее всех; решить, через сколько месяцев архивировать content (хэш и метаданные остаются).

## История версий

- v1.2 (23.07.2026): раздел 10 — верификация компаний и портал (R1, миграция 0017): 14 ENUM-типов, таблицы `user_accounts`, `sms_send_log`, `companies`, `company_members`, `company_business_roles`, `company_bank_accounts`, `verification_cases`, `verification_checks`, `verification_documents`, `domain_events`; мост маркетплейса (`seller_offers.company_id`/`created_by_user_account_id`, nullable `seller_id` + CHECK `ck_offer_origin`; дремлющие `sellers.company_id`/`clients.company_id`).
- v1.1 (12.06.2026): `sources.adapter` + `last_test_ok_at` под конструктор источников (dev-спека §2.5); `fx_rates`; kind `rss`; вопросы 1 и 3 закрыты.
- v1.0 (12.06.2026): первая версия.
