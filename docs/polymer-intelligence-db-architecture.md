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

### R3 Stage A — E-IMZO рельсы верификации (migration 0020_eimzo)

Подтверждение личности компании цифровой подписью через сайдкар UNICON
**e-imzo-server** (национальные алгоритмы O'zDSt — сами PKCS#7 никогда не парсим).
Подписанный challenge заполняет и **замораживает** реквизиты компании
(`companies.identity_locked`), авто-проставляет проверку `eimzo_signature=passed`
и авто-подтверждает подписанта владельцем. Доказательства неизменяемы
(append-only `signature_evidence`), PINFL/ФИО шифруются тем же `VERIFICATION_ENC_KEY`
(§6.2). `integration_call_log` — журнал вызовов шлюза (метаданные, прунится 90 дней;
тела запросов/ответов НЕ хранятся — там может быть PINFL/PKCS#7).

```sql
-- Новое значение enum (ADD VALUE вне транзакции; DROP невозможен → downgrade оставляет)
ALTER TYPE verification_check_type ADD VALUE IF NOT EXISTS 'eimzo_signature';

-- Реквизиты, подтверждённые ЭЦП, замораживаются (PATCH по ним отклоняется)
ALTER TABLE companies ADD COLUMN identity_locked boolean NOT NULL DEFAULT false;

-- Неизменяемое доказательство одной проверенной подписи (purpose: company_identity | contract)
CREATE TABLE signature_evidence (
    id                 bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    company_id         bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_account_id    bigint NOT NULL REFERENCES user_accounts(id),   -- кто подписал
    purpose            text NOT NULL,                    -- 'company_identity' | 'contract'
    challenge          text NOT NULL,                    -- подписанный nonce
    pkcs7_storage_path text NOT NULL,                    -- S3 evidence/eimzo/{company_id}/…
    pkcs7_sha256       text NOT NULL,                    -- целостность сохранённого blob
    cert_subject       jsonb,                            -- разобранные поля subject сертификата
    signed_at          timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_signature_evidence_company_id ON signature_evidence(company_id);

-- Персональные данные директора/подписанта (шифрование на уровне приложения, §6.2)
CREATE TABLE company_person_data (
    id              bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    company_id      bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_account_id bigint REFERENCES user_accounts(id),
    full_name_enc   bytea NOT NULL,                      -- Fernet ciphertext
    pinfl_enc       bytea NOT NULL,                      -- Fernet ciphertext
    pinfl_last4     char(4),                             -- в открытом виде, только для маски ****last4
    position        text,
    source          text NOT NULL DEFAULT 'eimzo',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_company_person_data_company_id ON company_person_data(company_id);

-- Журнал вызовов интеграционного шлюза (аудит circuit-breaker; только метаданные)
CREATE TABLE integration_call_log (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    provider    text NOT NULL,                           -- 'eimzo', далее gov/bank/…
    operation   text NOT NULL,                           -- 'verify_pkcs7'
    ok          boolean NOT NULL,
    status_code int,
    latency_ms  int,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_integration_call_log_created  ON integration_call_log(created_at);          -- прун 90д
CREATE INDEX ix_integration_call_log_provider ON integration_call_log(provider, created_at);
```

### R3 Stage B — Контракты (migration 0021_contracts)

Контекст «Контракты» — зерно домена Deal Lifecycle. Верифицированная компания
создаёт `Contract` из `ContractTemplate` со второй верифицированной компанией; обе
стороны подписывают через E-IMZO (каждая подпись — строка `signature_evidence`
`purpose='contract'`, на неё ссылается `contract_signatures`). Обе подписи →
статус `active`. Сгенерированный PDF хранится в S3 (`generated_document_path`) с
`document_sha256` для детекции подделки.

```sql
CREATE TYPE contract_status AS ENUM (
    'draft','pending_counterparty','pending_signatures','active','declined','cancelled','expired');

-- Шаблон договора (двуязычный) + JSON Schema обязательных переменных
CREATE TABLE contract_templates (
    id                bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code              text NOT NULL UNIQUE,             -- SUPPLY_V1
    name_ru           text NOT NULL, name_uz text, name_en text,
    body_storage_path text NOT NULL,                    -- S3 contracts/templates/…
    variables_schema  jsonb NOT NULL,
    version           int NOT NULL DEFAULT 1,
    is_active         boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contracts (
    id                       bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    public_id                uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    template_id              bigint NOT NULL REFERENCES contract_templates(id),
    template_version         int NOT NULL,
    initiator_company_id     bigint NOT NULL REFERENCES companies(id),
    counterparty_company_id  bigint NOT NULL REFERENCES companies(id),
    offer_id                 bigint REFERENCES seller_offers(id),     -- контекстная ссылка
    title                    text NOT NULL,
    variables                jsonb NOT NULL DEFAULT '{}',
    generated_document_path  text, document_sha256 text,
    status                   contract_status NOT NULL DEFAULT 'draft',
    created_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    sent_at timestamptz, activated_at timestamptz, declined_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_contract_parties_distinct CHECK (initiator_company_id <> counterparty_company_id)
);
CREATE INDEX ix_contracts_initiator    ON contracts(initiator_company_id);
CREATE INDEX ix_contracts_counterparty ON contracts(counterparty_company_id);

-- Подпись одной стороны (переиспользует signature_evidence)
CREATE TABLE contract_signatures (
    id                        bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    contract_id               bigint NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    company_id                bigint NOT NULL REFERENCES companies(id),
    signed_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    signature_evidence_id     bigint NOT NULL REFERENCES signature_evidence(id),
    signed_at                 timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_signature UNIQUE (contract_id, company_id)
);
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

### R4 / P1 — Медиа: логотип компании (migration 0022_company_logo)

Блок F ТЗ deal-lifecycle (FR-M1, FR-M4). У компании появляется логотип. Хранится
**только ключ объекта** — постоянных публичных URL нет, API отдаёт короткоживущую presigned
ссылку на каждый запрос (TTL ≤ 600 с, как у документов контрактов R3). Замена логотипа
удаляет старый объект из S3 (fail-soft: ошибка удаления логируется, запрос не падает).
Фото офферов схему НЕ меняют — используется существующая `seller_offer_files`
(`kind='image'`).

```sql
-- NULL = логотипа нет (нормальное состояние, не ошибка)
ALTER TABLE companies ADD COLUMN logo_storage_path text;
```

### R4 / P2 — Сделки: Deal, Trade Room, отклики на RFQ (migration 0023_deals)

Блок A ТЗ deal-lifecycle (FR-D1–D10). Ядро домена: `Deal` — комната, в которой две
верифицированные компании доводят сделку до конца (машина состояний, чат, документы,
таймлайн). Сделка открывается из принятого отклика на RFQ либо из одобренного inquiry.

**Граница контекста.** Связь с контрактами односторонняя: FK живёт на `deals.contract_id`,
таблица `contracts` НЕ изменяется. Контекст контрактов о сделках не знает — сделка реагирует
на доменные события `CONTRACT_*` (outbox). Это даёт один источник истины вместо двух
взаимных nullable-FK, которые неизбежно разъезжаются.

```sql
CREATE TYPE deal_status AS ENUM (
    'negotiation','contract_pending','contract_signed','payment_pending','paid_escrow',
    'shipped','delivered','completed','cancelled','disputed');
CREATE TYPE deal_actor_kind    AS ENUM ('buyer','seller','staff','system');
CREATE TYPE deal_document_kind AS ENUM ('contract','invoice','lab_passport','transport','other');
CREATE TYPE rfq_response_status AS ENUM ('submitted','accepted','not_selected','withdrawn');
CREATE TYPE rfq_visibility      AS ENUM ('verified_only','all','selected');

-- Номер: DEAL-YYYY-NNNNNN (посерийная последовательность deal_seq_{YYYY})
CREATE TABLE deals (
    id                bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    public_id         uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    number            text NOT NULL UNIQUE,
    buyer_company_id  bigint NOT NULL REFERENCES companies(id),
    seller_company_id bigint NOT NULL REFERENCES companies(id),
    request_id  int    REFERENCES requests(id),        -- контекст: из какого RFQ
    offer_id    int    REFERENCES seller_offers(id),   -- контекст: из какого оффера
    contract_id bigint REFERENCES contracts(id),       -- владелец связи — сделка
    status      deal_status NOT NULL DEFAULT 'negotiation',
    amount      numeric(16,2), currency char(3) NOT NULL DEFAULT 'UZS',
    created_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    cancelled_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_deal_parties_distinct CHECK (buyer_company_id <> seller_company_id)
);
CREATE INDEX ix_deals_buyer_status  ON deals(buyer_company_id, status);
CREATE INDEX ix_deals_seller_status ON deals(seller_company_id, status);
-- Партиальный UNIQUE: потребитель события CONTRACT_ACTIVATED ищет сделку ПО contract_id
-- и обязан находить максимум одну.
CREATE UNIQUE INDEX uq_deals_contract ON deals(contract_id) WHERE contract_id IS NOT NULL;

-- Таймлайн: append-only, from_status NULL только у открывающей строки
CREATE TABLE deal_status_history (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    deal_id bigint NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    from_status deal_status, to_status deal_status NOT NULL,
    actor_kind  deal_actor_kind NOT NULL, actor_id bigint, reason text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_deal_status_history_deal ON deal_status_history(deal_id, id);

-- Чат Trade Room: append-only, путей UPDATE/DELETE нет
CREATE TABLE deal_messages (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    deal_id bigint NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    author_account_id bigint NOT NULL REFERENCES user_accounts(id),
    -- Сторона на момент отправки: членство меняется, а сообщение обязано
    -- продолжать показывать того, кто его действительно написал.
    author_company_id bigint NOT NULL REFERENCES companies(id),
    body text NOT NULL DEFAULT '',
    file_storage_path text, file_name text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_deal_message_not_empty CHECK (body <> '' OR file_storage_path IS NOT NULL)
);
CREATE INDEX ix_deal_messages_deal ON deal_messages(deal_id, id);

-- Документы: отзываются пометкой, объект в S3 остаётся как доказательство
CREATE TABLE deal_documents (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    deal_id bigint NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    kind deal_document_kind NOT NULL DEFAULT 'other',
    file_name text NOT NULL, mime_type text NOT NULL, size_bytes int NOT NULL,
    storage_path text NOT NULL, sha256 char(64) NOT NULL,
    uploaded_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    uploaded_by_company_id      bigint NOT NULL REFERENCES companies(id),
    revoked boolean NOT NULL DEFAULT false, revoked_reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_deal_documents_deal ON deal_documents(deal_id, id);

CREATE TABLE rfq_responses (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id int NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    company_id bigint NOT NULL REFERENCES companies(id),
    created_by_user_account_id bigint NOT NULL REFERENCES user_accounts(id),
    price numeric(14,2) NOT NULL, currency char(3) NOT NULL DEFAULT 'USD',
    qty numeric(14,3) NOT NULL, qty_unit text NOT NULL DEFAULT 'MT',
    incoterms price_basis,                    -- NULL = не указано (≠ 'unknown')
    lead_time_days int, comment text,
    status rfq_response_status NOT NULL DEFAULT 'submitted',
    deal_id bigint REFERENCES deals(id),      -- заполняется при акцепте
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_rfq_responses_request ON rfq_responses(request_id, id);
CREATE INDEX ix_rfq_responses_company ON rfq_responses(company_id, status);
-- Один ЖИВОЙ отклик компании на RFQ; партиальный, чтобы отзыв освобождал слот,
-- а не блокировал поставщика навсегда.
CREATE UNIQUE INDEX uq_rfq_response_active ON rfq_responses(request_id, company_id)
    WHERE status <> 'withdrawn';

-- Расширения RFQ (FR-D10) на существующей таблице requests
ALTER TABLE requests ADD COLUMN required_docs jsonb;                  -- sds|coa|origin_cert|…
ALTER TABLE requests ADD COLUMN visibility rfq_visibility NOT NULL DEFAULT 'verified_only';
ALTER TABLE requests ADD COLUMN visible_company_ids jsonb;            -- для visibility='selected'
```

### R4 / P3 — Escrow-платежи (migration 0024_escrow)

Деньги идут через банк-партнёр, не через платформу. Здесь хранится только *запись*
о движении: одна `EscrowPayment` на сделку и сырой inbox колбэков провайдера.

Два сознательных отсутствия:

- **Никаких банковских реквизитов** — ни номера счёта, ни IBAN, ни МФО. Счёт
  выставляет банк; хранение реквизитов не даёт ничего операционно, но делает
  таблицу мишенью для мошенничества.
- **Никакой статусной логики** — переходы, блокировка строки и побочные эффекты на
  сделку принадлежат `escrow_service`. Здесь только схема.

`mode` фиксируется в момент создания: оператор может переключить runtime-настройку
`escrow_mode` когда угодно, но платёж, открытый на stub-рельсе, остаётся stub —
иначе переключение задним числом изменило бы правила отметки существующих строк.

`provider_events` создаётся здесь, а не в P7: гарантия идемпотентности принадлежит
**схеме** (UNIQUE `(provider, external_id)` — повторный колбэк банка падает на
вставке, а не применяется дважды), а P7 добавляет только клиент и webhook-роут.

```sql
CREATE TYPE escrow_status AS ENUM ('pending','funded','released','refunded');

CREATE TABLE escrow_payments (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    deal_id  bigint NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    amount   numeric(16,2) NOT NULL, currency char(3) NOT NULL DEFAULT 'UZS',
    status   escrow_status NOT NULL DEFAULT 'pending',
    mode     text NOT NULL DEFAULT 'stub',      -- 'stub' | 'live', зафиксирован при создании
    provider_ref text,                          -- id операции банка (live); НЕ реквизиты
    funded_at timestamptz, released_at timestamptz, refunded_at timestamptz,
    funded_marked_by   bigint,                  -- staff_users.id (stub-режим)
    released_marked_by bigint,
    refunded_marked_by bigint,
    note text,                                  -- обязательный комментарий оператора
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Одна запись на сделку: весь денежный путь ищет платёж ПО сделке,
    -- две строки сделали бы вопрос «оплачена ли сделка» неоднозначным.
    CONSTRAINT uq_escrow_payments_deal UNIQUE (deal_id)
);
CREATE INDEX ix_escrow_payments_status ON escrow_payments(status, id);

-- Webhook-inbox (используется и P7). Payload хранится дословно: непонятый
-- колбэк — всё ещё доказательство.
CREATE TABLE provider_events (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    provider text NOT NULL, external_id text NOT NULL,
    payload jsonb NOT NULL,
    processed boolean NOT NULL DEFAULT false, processed_at timestamptz, error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_provider_events_external UNIQUE (provider, external_id)
);
CREATE INDEX ix_provider_events_unprocessed ON provider_events(processed, id);
```

### R4 / P4 — Поля продажи оффера + избранное (migration 0025_offer_sale_fields)

Как продавец на самом деле торгует этим оффером: срок производства, способ продажи и
три флага «готов к сделке» — они становятся бейджами на карточке маркета.

`seller_offers` — живая таблица с записями двух происхождений (TG-продавцы и
компании портала), поэтому **каждая** добавленная колонка nullable либо имеет
server default: голый NOT NULL уронил бы миграцию на реальной базе.

`accepts_rfq` по умолчанию TRUE, остальные два — FALSE: ответить на RFQ продавцу ничего
не стоит, а подписание договора и удержание денег в escrow — обязательства, в которые
нельзя записать задним числом.

`offer_favorites` привязано к **аккаунту**, а не к компании: закладка личная, и смена
«шляпы» компании в портале не должна её менять.

```sql
CREATE TYPE offer_sale_mode AS ENUM ('from_stock','made_to_order','recurring_contract');

ALTER TABLE seller_offers ADD COLUMN lead_time_days int;              -- срок производства
ALTER TABLE seller_offers ADD COLUMN sale_mode offer_sale_mode;       -- способ продажи
ALTER TABLE seller_offers ADD COLUMN accepts_rfq      boolean NOT NULL DEFAULT true;
ALTER TABLE seller_offers ADD COLUMN accepts_contract boolean NOT NULL DEFAULT false;
ALTER TABLE seller_offers ADD COLUMN accepts_escrow   boolean NOT NULL DEFAULT false;

CREATE TABLE offer_favorites (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_account_id bigint NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    offer_id        int    NOT NULL REFERENCES seller_offers(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_offer_favorite UNIQUE (user_account_id, offer_id)
);
CREATE INDEX ix_offer_favorites_account ON offer_favorites(user_account_id, id);
```

## История версий

- v1.9 (27.07.2026): R4/P4 — поля продажи оффера (миграция 0025_offer_sale_fields): enum `offer_sale_mode`; `seller_offers += lead_time_days / sale_mode / accepts_rfq / accepts_contract / accepts_escrow` (все nullable или с server default — таблица живая); таблица `offer_favorites` (UNIQUE `(user_account_id, offer_id)`, привязка к аккаунту, не к компании).
- v1.8 (27.07.2026): R4/P3 — escrow-платежи (миграция 0024_escrow): enum `escrow_status`; таблицы `escrow_payments` (UNIQUE по `deal_id`, `mode` зафиксирован при создании, `*_at`/`*_marked_by` на каждую отметку) и `provider_events` (webhook-inbox, UNIQUE `(provider, external_id)`). Банковских реквизитов в схеме нет. Таблица `deals` НЕ изменена — платёж двигает сделку только через `deal_service.transition()`.
- v1.7 (27.07.2026): R4/P2 — сделки (миграция 0023_deals): enum'ы `deal_status`, `deal_actor_kind`, `deal_document_kind`, `rfq_response_status`, `rfq_visibility`; таблицы `deals` (CHECK `buyer <> seller`, партиальный UNIQUE по `contract_id`), `deal_status_history`, `deal_messages` (CHECK «текст или файл»), `deal_documents`, `rfq_responses` (партиальный UNIQUE живого отклика); `requests += required_docs / visibility / visible_company_ids`. Таблица `contracts` НЕ изменена — связь односторонняя (`deals.contract_id`) + доменные события.
- v1.6 (27.07.2026): R4/P1 — медиа (миграция 0022_company_logo): `companies.logo_storage_path` (nullable, только S3-ключ; выдача — presigned TTL ≤ 600 с). Фото офферов — без изменений схемы (существующая `seller_offer_files`, `kind='image'`).
- v1.5 (26.07.2026): R3 Stage B — Контракты (миграция 0021_contracts): enum `contract_status`, таблицы `contract_templates`, `contracts` (CHECK `initiator <> counterparty`), `contract_signatures` (UNIQUE(contract_id, company_id), FK на `signature_evidence`). Зерно домена Deal Lifecycle.
- v1.4 (26.07.2026): R3 Stage A — E-IMZO рельсы (миграция 0020_eimzo): enum-значение `verification_check_type += 'eimzo_signature'`, `companies.identity_locked`, таблицы `signature_evidence` (неизменяемое доказательство подписи), `company_person_data` (шифрованные PINFL/ФИО, §6.2), `integration_call_log` (журнал шлюза, прун 90д).
- v1.2 (23.07.2026): раздел 10 — верификация компаний и портал (R1, миграция 0017): 14 ENUM-типов, таблицы `user_accounts`, `sms_send_log`, `companies`, `company_members`, `company_business_roles`, `company_bank_accounts`, `verification_cases`, `verification_checks`, `verification_documents`, `domain_events`; мост маркетплейса (`seller_offers.company_id`/`created_by_user_account_id`, nullable `seller_id` + CHECK `ck_offer_origin`; дремлющие `sellers.company_id`/`clients.company_id`).
- v1.1 (12.06.2026): `sources.adapter` + `last_test_ok_at` под конструктор источников (dev-спека §2.5); `fx_rates`; kind `rss`; вопросы 1 и 3 закрыты.
- v1.0 (12.06.2026): первая версия.
