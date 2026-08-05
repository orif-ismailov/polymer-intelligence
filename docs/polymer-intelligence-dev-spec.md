# Polymer Intelligence — Спецификация реализации (для разработчиков)

> **⚠️ Исторический документ.** Это спецификация исходного проектного замысла, написанная
> до/во время первичной реализации. Она **не поддерживается** в актуальном состоянии и
> **не отражает** текущее состояние кода. За точной информацией обращайтесь к актуальным
> каноническим документам: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md), [`docs/API.md`](API.md),
> [`docs/CONFIGURATION.md`](CONFIGURATION.md), [`docs/DEVELOPMENT.md`](DEVELOPMENT.md),
> [`docs/TESTING.md`](TESTING.md), [`docs/GETTING-STARTED.md`](GETTING-STARTED.md).
>
> Известные основные расхождения с текущим кодом: `parsing/` находится в `backend/parsing/`
> (а не `backend/app/parsing/`), экстрактор называется `extractor.py` (а не `llm_extract.py`);
> `telegram/` и `userbot/` — пакеты в корне репозитория (а не вложены в `backend/`);
> `counterparty_service`, `price_service` и группа эндпоинтов `/counterparties*` так и не были
> реализованы; `docs/runbook.md` и `deploy/restore.sh` не существуют; прогон eval-тестов
> экстракции выполняется через `python -m parsing.eval_cli` (цели `make eval-extraction` нет);
> dashboard работает на Next.js 16.2.6 (а не «14+»).

Версия 1.0 · 12.06.2026
Основание: клиентское ТЗ v1.0 (polymer-intelligence-tz.md) + схема БД (polymer-intelligence-db-architecture.md).
Этот документ отвечает на вопрос «как строим», клиентское ТЗ — «что и зачем». При противоречии приоритет у клиентского ТЗ.

---

## 1. Состав системы и репозиторий

Монорепо:

```
polymer-intelligence/
├── backend/                  # FastAPI + Celery (один Python-пакет)
│   ├── app/
│   │   ├── api/              # роутеры: auth, requests, signals, prices, alerts, reports, sources, admin
│   │   ├── core/             # config, security, deps
│   │   ├── models/           # SQLAlchemy (по схеме приложения A)
│   │   ├── schemas/          # Pydantic
│   │   ├── services/         # бизнес-логика (см. §3)
│   │   ├── ingest/           # сборщики: uzex/, sunsirs/, dce/, cbu_rates/
│   │   ├── parsing/          # rule-based парсеры + LLM-извлечение, промпты с версиями
│   │   ├── tasks/            # Celery-таски + расписание beat
│   │   └── telegram/         # aiogram-бот (вебхук через FastAPI)
│   ├── userbot/              # ОТДЕЛЬНЫЙ процесс Telethon (не в Celery!)
│   ├── alembic/
│   └── tests/
├── dashboard/                # Next.js 14+ (app router)
├── webapp/                   # React + Vite + @telegram-apps/sdk
├── deploy/                   # docker-compose.prod.yml, nginx/, backup-скрипты
└── docs/                     # этот документ, схема БД, runbook
```

Контейнеры: `api`, `worker` (Celery), `beat`, `userbot`, `bot` не нужен отдельно (вебхук в api), `dashboard`, `postgres`, `redis`, `nginx`. Web App собирается статикой, отдаётся nginx.

**Почему userbot отдельным процессом:** Telethon держит постоянное MTProto-соединение и сессию; внутри Celery-воркера это приводит к конфликтам event loop и блокировкам сессии. Userbot — самостоятельный долгоживущий процесс, который пишет напрямую в `raw_items` и ставит Celery-задачу на парсинг через Redis.

---

## 2. Конвейер данных (главное в системе)

```
fetch (ingest/*) → raw_items (dedupe по sha256) → task: parse_raw_item
    → rule-based (UZEX, индексы)  ─┐
    → LLM-extract (TG, free-text) ─┴→ signals → post_process:
                                              ├─ task: match_counterparty
                                              ├─ task: evaluate_alert_rules
                                              └─ (deal) → nightly aggregate → price_points
```

Правила, обязательные для всех сборщиков:

1. Сборщик НЕ парсит смысл. Он сохраняет сырьё в `raw_items` и выходит. Парсинг — отдельная таска. Исключение: табличные источники (UZEX, SunSirs) кладут в `payload` уже разобранную структуру строки таблицы, но запись в `signals`/`price_points` всё равно делает parse-таска.
2. Дедупликация: `sha256(source_id + external_id + content_normalized)` → `ON CONFLICT DO NOTHING`. Повторный прогон сборщика не создаёт дублей.
3. Любая ошибка сборщика: лог + инкремент `sources.consecutive_failures`; при достижении 3 — алерт `source_failure` (с dedupe_key = `source_failure:{source_id}:{date}`). Успех сбрасывает счётчик.
4. HTTP: таймаут 30 с, 3 ретрая с экспоненциальной задержкой, User-Agent честный (`PolymerIntelligence/1.0 (+contact@...)`), уважать robots-паузы: ≥2 с между запросами к одному хосту.

### 2.1. Сборщик UZEX (`ingest/uzex/`)

Страницы (Этап 0: подтвердить актуальные URL руками, вёрстка ASP.NET, server-rendered таблицы):

| Раздел | URL (проверить) | Период | Что извлекаем |
|---|---|---|---|
| Выставлено (сум) | /Trade/OffersSumNew, /Trade/NewSpotTable | 15 мин в торговые часы | лот, товар, объём, цена старта, секция |
| Выставлено (валюта) | /Trade/OffersCurrencyNew | 15 мин | то же |
| Выставлено (импорт) | /Trade/OffersImportNew | 15 мин | то же |
| Котировальные листы | /Trade/ContractsSumNew, /Trade/ContractsCurrencyNew (+Rubl/Euro/Yuan) | 1 ч | контрактные цены |
| Реестр сделок | /Trade/List | 1 ч | сделка: товар, объём, цена, дата, стороны (если публикуются) |

Реализация: `httpx` + `selectolax` (быстрее BeautifulSoup). Браузерная автоматизация НЕ используется; если страница потребует JS — эскалация тимлиду, не самодеятельность с Playwright.

Фильтр релевантности: товар матчится по словарю `products` + таблице синонимов (`полипропилен`, `PP`, `полиэтилен высокой плотности`, `ПЭВП`, `HDPE`, узбекские варианты — словарь в seed-миграции, пополняется через админку). Нематч → `raw_items.parse_status='irrelevant'`, в signals не попадает. Раз в неделю отчёт по irrelevant-товарам с частотой >N — для пополнения словаря.

Извлечение грейда: regex-набор по известным паттернам (`[A-Z]{1,3}\d{2,4}[A-Z]{0,3}`, конкретные известные грейды из `product_grades`); нематч → `grade_text` заполняется, `grade_id` NULL.

### 2.2. Userbot (`userbot/`)

- Telethon, session-файл в volume, аккаунт выдаёт заказчик. API_ID/API_HASH — от его же аккаунта.
- Подписка на каналы из `sources WHERE kind='telegram_channel' AND is_enabled`. Перечитывать список раз в 10 мин (добавление канала без рестарта).
- На новое сообщение: текст + метаданные (msg_id, channel_id, дата, есть ли медиа) → `raw_items` → enqueue `parse_raw_item`. Медиа-файлы НЕ скачиваем (Фаза 1), фиксируем факт наличия.
- Анти-флуд: Telethon сам обрабатывает FloodWait — логировать и ждать, не ретраить вручную. Никаких массовых join'ов: добавление каналов — по 1–2 в час.
- Догон истории при первом подключении канала: последние 200 сообщений, не больше.
- Health: userbot пишет heartbeat в Redis каждые 60 с; beat-таска проверяет и алертит при тишине >5 мин.

### 2.3. LLM-извлечение (`parsing/llm_extract.py`)

- Модель: claude-haiku-4-5 (конфигурируемо). Один вызов = классификация + извлечение.
- Выход — строго JSON по схеме (хранится в `docs/extraction-schema.json`, версия в промпте):

```json
{
  "relevant": true,
  "kind": "buy_request | sell_offer | price_quote | news",
  "product_code": "PP | HDPE | ... | null",
  "grade_text": "T30S | null",
  "volume_mt": 300.0,
  "price": 1080.0,
  "currency": "USD | UZS | CNY | null",
  "price_basis": "FCA | CIF | ... | unknown",
  "region": "string | null",
  "counterparty_text": "string | null",
  "contact": "string | null",
  "urgency": "low | medium | high",
  "summary_ru": "1 предложение",
  "confidence": 0.0
}
```

- Промпты лежат в `parsing/prompts/` как файлы `extract_v{N}.md`; номер версии пишется в `parse_runs.prompt_version`. Менять промпт = новый файл, старые не редактируются.
- `confidence < 0.5` → сигнал создаётся со `status='needs_review'` (отдельный фильтр в дашборде).
- Бюджет: счётчик токенов за день в Redis; превышение `LLM_DAILY_TOKEN_LIMIT` → новые элементы остаются `pending`, алерт админу, ночью добор.
- Батчинг: до 10 коротких сообщений одним вызовом запрещён (теряется качество) — по одному. Зато параллелизм воркера до 5 одновременных вызовов.

### 2.4. Внешние индексы (Фаза 2)

- SunSirs: страницы дневных цен PP/HDPE/LDPE/LLDPE/PVC/PET → `price_points (kind='index', market='CN', currency='CNY')`. Конвертация в USD — на чтении, по `fx_rates`, в БД хранится оригинал.
- DCE-фьючерсы: ближайший контракт PP и LLDPE, дневное расчётное значение → `kind='futures', market='DCE'`.
- ETS KZ: после верификации — еженедельные индикаторы → `kind='index', market='KZ'`. Если верификация провалится, модуль не пишется вовсе.
- Курсы ЦБ РУз: `https://cbu.uz/ru/arkhiv-kursov-valyut/json/` (официальный JSON API) → таблица `fx_rates` (добавить в схему: `date, ccy char(3), rate numeric, PRIMARY KEY(date, ccy)`).

### 2.5. Архитектура адаптеров: добавление источников из админки

**Требование заказчика:** новый источник данных добавляется через админку без релиза кода — везде, где это технически возможно.

**Интерфейс адаптера.** Каждый способ сбора — класс, реализующий протокол:

```python
class SourceAdapter(Protocol):
    type_name: str                      # 'telegram_channel' | 'llm_page' | 'html_table' | ...
    config_schema: type[BaseModel]      # pydantic-схема конфига → автогенерация формы в админке
    async def fetch(self, source: Source) -> list[RawItemDraft]: ...
    async def test(self, config: dict) -> TestResult:  # dry-run для кнопки «Тест» в админке
```

Адаптеры регистрируются в реестре (`ingest/registry.py`); админка получает список типов и их config_schema через `GET /admin/source-types` — форма добавления источника строится по схеме автоматически. Новый адаптер = один файл + регистрация; ни миграций, ни правок UI.

**Встроенные адаптеры и их уровень «без кода»:**

| Тип | Конфиг в админке | Код нужен? | Парсинг |
|---|---|---|---|
| `telegram_channel` | @username канала | нет | LLM-извлечение |
| `llm_page` | URL, расписание (cron-пресеты), CSS-селектор контентной области (опц.) | нет | страница → текст (selectolax, srip тегов) → diff с прошлым снимком → новые фрагменты → LLM-извлечение |
| `html_table` | URL, расписание, селектор таблицы, маппинг колонок → {product_text, grade, volume, price, currency, counterparty, date} + формат даты | нет | rule-based, без LLM |
| `rss` | URL фида, расписание | нет | элементы фида → LLM-извлечение |
| `uzex_*`, `sunsirs`, `dce`, `cbu_rates` | только расписание/вкл-выкл | да (поставляются с системой) | специализированный |

**`llm_page` — детали (ключевой для «изи»):**
- Снимок страницы хешируется; повторный fetch без изменений → no-op (нулевые токены).
- Изменился — текстовый diff, в LLM уходят только новые блоки (контроль бюджета).
- Источник автоматически наследует общий `LLM_DAILY_TOKEN_LIMIT`; в админке у источника виден расход токенов за 7 дней.
- Ограничение, отображаемое прямо в форме админки: «работает только с публичными страницами без логина и без JS-рендера; проверьте кнопкой Тест».

**Кнопка «Тест» обязательна для всех типов:** dry-run fetch + parse, превью до 10 извлечённых записей, ничего не пишется в БД. Источник нельзя включить (`is_enabled=true`), пока тест ни разу не прошёл успешно (поле `sources.last_test_ok_at`).

**Граница (зафиксирована и в клиентском ТЗ):** источники за авторизацией, с JS-рендером, капчей, нестандартными форматами — новый адаптер кодом (≈1 день на типовой случай благодаря реестру). Платные подписочные сервисы добавляются только при наличии подписки и только адаптером (контроль внутреннего контура).


---

## 3. Backend: сервисы и API

### 3.1. Сервисный слой (`services/`)

- `request_service` — создание заявки (генерация номера `REQ-YYYY-MM-DD-NNNNN` через sequence по дате), статусная машина (валидация переходов: new→viewed→in_progress→{offer_sent, closed, cancelled}; matched из in_progress/offer_sent), history, постановка уведомления клиенту.
- `signal_service` — создание из parse-результата, смена статуса, needs_review-очередь.
- `alert_service` — см. §3.3.
- `price_service` — выдача рядов для графиков (downsampling на SQL: дневные точки как есть, диапазон >1 года — недельная агрегация), ночная агрегация deals→price_points.
- `report_service` — Фаза 2, см. §5.
- `counterparty_service` — матчинг по `alias_norm` (нормализация: lower, убрать ООО/MCHJ/ИП/кавычки, схлопнуть пробелы, транслит uz-lat↔cyr), точное совпадение → автолинк с confidence источника, fuzzy (pg_trgm similarity >0.6) → кандидат в очередь подтверждения.

### 3.2. REST API (префикс `/api/v1`)

Аутентификация: дашборд — JWT (access 15 мин + refresh 7 дн, httpOnly cookie); Web App — заголовок `X-Telegram-Init-Data`, валидация подписи по алгоритму Telegram (HMAC от bot token) на каждый запрос, TTL initData 24 ч.

Клиентский контур (Web App):
```
POST /webapp/requests                 создать заявку
GET  /webapp/requests                 мои заявки (по client из initData)
GET  /webapp/requests/{id}            детали + история статусов
POST /webapp/requests/{id}/files      аттач (приходит telegram_file_id от бота, см. §4.2)
GET  /webapp/reports                  опубликованные отчёты (Фаза 2)
GET  /webapp/me · PATCH /webapp/me    профиль, язык
```

Внутренний контур (дашборд):
```
GET  /feed                            v_live_feed, фильтры: kind, product_id, source_id,
                                      urgency, status, date_from/to; keyset-пагинация по (event_at, id)
GET  /requests · GET /requests/{id} · PATCH /requests/{id}   (статус, assigned_to → audit_log)
GET  /signals · PATCH /signals/{id}   (status, needs_review-решения)
GET  /prices/series?product_id&market&grade_id&from&to
GET  /sources · PATCH /sources/{id} (enable/disable) · POST /sources (admin)
GET  /alerts · GET/POST/PATCH /alert-rules
GET  /counterparties · POST /counterparties/{id}/merge · GET /counterparties/candidates · POST .../confirm
GET  /reports · POST /reports/{id}/approve · POST /reports/{id}/reject   (Фаза 2, роль analyst+)
POST /auth/login · POST /auth/refresh · GET /admin/users (CRUD, admin)
GET  /health                          статус БД, Redis, очередей, последних сборов
```

Реалтайм ленты: SSE `GET /feed/stream` (новые id), фронт дотягивает по REST. Fallback — поллинг 30 с. WebSocket не используем (лишняя инфраструктура для односторонних обновлений).

### 3.3. Движок алертов

`evaluate_alert_rules(signal_id | request_id)` вызывается после создания сущности. Правило = JSONB-условие, поддерживаемые предикаты Фазы 1 (захардкоженный интерпретатор, НЕ eval):

```json
{"kind": ["buy_request"], "product_id": [1,2], "volume_gte": 200,
 "urgency_in": ["high"], "lead_score_gte": 0.8, "source_kind": ["webapp"]}
```

Сработало → `alerts` (dedupe_key = `rule:{rule_id}:{entity}:{id}`) → `deliveries` по каналам правила → таска `send_delivery` (rate limit: глобальный токен-бакет 25 msg/s на бота, 1 msg/s на chat_id, очередь deliveries и есть буфер).

`price_spike` (Фаза 2): beat-таска после ночной агрегации — |Δ день/день| по price_points > порога правила.

### 3.4. Celery: очереди и расписание

Очереди: `ingest` (сборщики), `parse` (LLM, concurrency 5), `notify` (доставка), `default`.
Beat:
```
*/15 9-18 * * 1-5 (Asia/Tashkent)  uzex_fetch_offers (3 секции)
0 * * * *                          uzex_fetch_contracts, uzex_fetch_deals
0 7 * * *                          fetch_cbu_rates
30 7 * * *                         fetch_sunsirs, fetch_dce        (Фаза 2)
0 2 * * *                          aggregate_price_points (вчера)
*/5 * * * *                        check_source_health, check_userbot_heartbeat
0 3 * * *                          retry_failed_parses (parse_attempts < 3)
0 8 * * 1-5                        generate_morning_report          (Фаза 2)
```
Все таски идемпотентны: повторный запуск за тот же период не создаёт дублей (dedupe на уровне БД, см. §2).

---

## 4. Telegram-слой

### 4.1. Бот (aiogram 3, вебхук `POST /telegram/webhook/{secret}`)

- `/start` клиенту: приветствие RU/UZ (по language_code), inline-кнопка Web App, создание/находка `clients`.
- Уведомления клиенту: смена статуса заявки (шаблоны в `telegram/templates/{ru,uz}/`), публикация отчёта (Фаза 2, опционально по подписке клиента).
- Команде (по telegram_user_id из staff_users): алерты в DM/группу с inline-ссылкой на карточку в дашборде.
- Никакой бизнес-логики в хендлерах — только вызовы сервисов.

### 4.2. Файлы заявок

Поток: Web App не умеет загружать файлы напрямую с телефона в Telegram-хранилище, поэтому: шаг 3 мастера предлагает «прикрепить файлы» → Web App просит пользователя отправить файлы боту (deep link `t.me/bot?start=attach_{request_draft_id}`) ИЛИ грузит на наш backend напрямую (multipart, до 10 МБ, MIME-валидация по magic bytes, не по расширению). Решение: **грузим на backend в S3-совместимое хранилище (MinIO в комплекте docker-compose)** — это проще UX, telegram_file_id остаётся для файлов, пришедших боту. Поле `storage_path` уже есть в схеме. (Уточнение к допущению 2.3.2 клиентского ТЗ: приоритет — прямая загрузка, file_id — запасной путь.)

### 4.3. Userbot — эксплуатация

Runbook (в `docs/runbook.md`): что делать при FloodWait >1 ч, при бане аккаунта (замена session: процедура логина с новым номером заказчика, перенос подписок), ротация. Сессии — только в volume, в репозиторий не попадают (gitignore + pre-commit hook на `*.session`).

---

## 5. Отчёты (Фаза 2)

`generate_morning_report`:
1. SQL-сбор фактов за вчера: price_points UZ (Δ к позавчера), число/структура заявок и сигналов, топ-сигналы по lead_score, внешний фон (CN/DCE Δ).
2. Факты → `data_snapshot` (jsonb) → LLM (модель класса Sonnet) с жёстким промптом: «использовать ТОЛЬКО числа из snapshot, ничего не вычислять самому, не добавлять фактов». 
3. Пост-валидация: каждый процент/число из текста должен присутствовать в snapshot (regex-проверка чисел); провал → status='draft' + пометка, не pending_approval.
4. `status='pending_approval'` → уведомление analyst'ам → кнопки Approve/Reject в дашборде → publish → deliveries в канал. Footer всегда: «По данным uzex.uz».

Автопубликация без approve отсутствует на уровне кода (нет такого перехода в статусной машине), не только UI.

---

## 6. Фронтенд

### 6.1. Дашборд (Next.js)

- Стек: Next.js (app router), TypeScript strict, TanStack Query, таблицы — TanStack Table, графики — Recharts, UI — shadcn/ui, тёмная тема по мокапам (дизайн-токены вынести в tailwind config на старте, не хардкодить цвета).
- Страницы Фазы 1: `/login`, `/` (dashboard: KPI-карточки + live feed), `/requests` (+ боковая карточка по мокапу), `/signals` (фильтр needs_review), `/offers` (signals kind=sell_offer), `/prices`, `/sources` (список + health + **мастер добавления источника**: выбор типа → автоформа по config_schema → кнопка Тест с превью → включение), `/alerts` (+ rules), `/admin/users`. Фаза 2: `/reports` (approve-flow), `/counterparties` (+candidates).
- Live: SSE-хук с reconnect/backoff; на событие — инвалидация query ленты.
- Роли с сервера в JWT; UI скрывает недоступное, но авторизация — на API (фронт не граница безопасности).

### 6.2. Web App (React + Vite)

- @telegram-apps/sdk: initData, тема Telegram (CSS-переменные `var(--tg-theme-*)` — НЕ хардкодить тёмную тему, юзер может быть в светлой), MainButton для «Далее/Отправить», BackButton для шагов.
- Экраны: Home, мастер заявки (4 шага, стейт в zustand, переживает сворачивание), Мои заявки, детали заявки, Уведомления, Новости (Фаза 2), профиль/язык.
- i18n: react-i18next, словари ru/uz, ключи — полные фразы запрещены в коде.
- Бандл ≤300 КБ gzip; никаких тяжёлых UI-библиотек, формы — react-hook-form + zod.

---

## 7. Конфигурация, деплой, эксплуатация

ENV (полный список в `deploy/.env.example`): `DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY, LLM_EXTRACT_MODEL, LLM_REPORT_MODEL, LLM_DAILY_TOKEN_LIMIT, BOT_TOKEN, WEBHOOK_SECRET, TG_API_ID, TG_API_HASH, JWT_SECRET, S3_*, TZ_DISPLAY=Asia/Tashkent, SENTRY_DSN`.

- Один VPS (минимум 4 vCPU / 8 ГБ / 80 ГБ SSD), docker compose, nginx с TLS (certbot).
- Логи: structlog JSON → stdout → docker logs (+ опц. Loki). Ошибки — Sentry.
- Бэкапы: cron на хосте — `pg_dump -Fc` ежедневно 03:30, ротация 14 дн, еженедельный в офсайт (S3/другой сервер), скрипт восстановления в `deploy/restore.sh`, тест восстановления — пункт приёмки.
- CI (GitHub Actions): lint (ruff, mypy на services/ и schemas/; eslint+tsc) → tests → build образов. Деплой: пуш образов + `docker compose pull && up -d` по ssh (скрипт, не руками).
- Миграции: alembic, применяются entrypoint'ом api-контейнера с advisory lock.

---

## 8. Тестирование и качество

- Юнит: статусная машина заявок, интерпретатор alert-правил, нормализация алиасов, валидация initData, генерация номеров — покрытие этих модулей 90%+.
- Парсеры UZEX: тесты на сохранённых HTML-фикстурах (`tests/fixtures/uzex/*.html`); при поломке вёрстки фикстура обновляется и фиксируется — это и есть регрессионная база.
- LLM-извлечение: golden-set `tests/fixtures/extraction/*.json` (вход-сообщение → ожидаемый JSON); прогоняется отдельной командой `make eval-extraction` (не в CI — стоит денег), отчёт precision/recall по полям. Контрольные выборки приёмки (клиентское ТЗ п.6.3, 6.8) гоняются этим же инструментом.
- Интеграционные: docker-compose тестовый — поток raw_item → signal → alert → delivery (с моком Telegram API и моком LLM).
- E2E webapp: подача заявки через Playwright с фейковым initData (тестовый middleware, только в DEV).

Definition of Done задачи: код + тесты + прошедший CI + обновлённые docs при изменении контрактов API/схемы. Изменение схемы БД — только через alembic-миграцию + правку документа схемы в том же PR.

---

## 9. Разбивка работ (эпики → задачи, Фаза 1)

E1. Каркас (нед. 1): монорепо, docker-compose dev, FastAPI skeleton, alembic + полная схема + seed (products, синонимы, грейды UZ-производителей), CI, auth JWT, /health.
E2. Ингест-ядро + UZEX (нед. 2–3): **реестр адаптеров (SourceAdapter, registry, test-механизм)**, httpx-клиент с ретраями; адаптеры uzex offers/contracts/deals; raw-пайплайн + dedupe; rule-based парсер таблиц → signals; словарь синонимов + админ-пополнение; source health + алерт source_failure.
E3. Клиентский контур (нед. 3–5): бот (start, webhook, шаблоны ru/uz), Web App (мастер 4 шага, мои заявки, i18n), API webapp, файлы → MinIO, уведомления о статусах, request_service + статусная машина + история.
E4. Дашборд (нед. 5–7): login/роли, feed + SSE, requests-таблица + карточка + действия, prices-график, sources (health + вкл/выкл), alerts + rules-конструктор, admin/users, audit_log.
E4a. Конструктор источников (нед. 7–8): адаптеры `llm_page`, `html_table`, `rss`; автоформы по config_schema; кнопка Тест с превью; расход токенов по источнику; блокировка включения без успешного теста.
E5. TG-мониторинг (нед. 8–9.5): userbot-процесс + heartbeat (адаптер `telegram_channel` поверх реестра), LLM-извлечение + промпт v1 + parse_runs + бюджет, needs_review-поток в дашборде, eval-инструмент + golden-set, прогон контрольной выборки заказчика.
E6. Приёмка (нед. 10): критерии п.6.1–6.5 клиентского ТЗ + приёмка конструктора (см. ниже), restore-тест, runbook, передача.

Критерий приёмки конструктора: пользователь с ролью admin добавляет через UI новый публичный сайт типа `llm_page` и новый Telegram-канал без участия разработчика; извлечённые сигналы появляются в ленте; неуспешный тест блокирует включение источника.

Фаза 2 (нед. 11–16): E7 отчёты (генерация + валидация чисел + approve-flow + публикация), E8 внешние индексы (SunSirs, DCE, fx уже есть; верификация ETS — первые 2 дня), E9 международные каналы (промпт-расширение RU/EN/TR + golden-set + приёмка п.6.8), E10 контрагенты (нормализация, автолинк, candidates UI).

---

## 10. Зоны риска для разработчика (читать перед стартом)

1. **Вёрстка UZEX** — главный внешний риск. Первая задача E2 — снять и закоммитить фикстуры всех целевых страниц. Селекторы — в конфиге источника (`sources.config`), не в коде.
2. **LLM-JSON** — модель иногда нарушает схему. Валидация pydantic'ом, 1 ретрай с сообщением об ошибке валидации, после — failed + needs_review. Никогда не парсить «почти JSON» регексами.
3. **Часовые пояса** — UZS-торги в Ташкенте, SunSirs в Пекине, фьючерсы в UTC+8. В БД только UTC (timestamptz), `observed_on` для дневных рядов — локальная дата рынка (поле market определяет TZ). Зафиксировать хелпером, не решать в каждом месте заново.
4. **Идемпотентность ночной агрегации** — `DELETE WHERE observed_on = X AND kind='deal_avg'` + пересчёт в одной транзакции, чтобы повторный запуск был безопасен.
5. **initData** — валидировать на каждом запросе, не доверять client_id из тела. Известная уязвимость всех TWA-проектов — доверие к telegram_user_id из payload.
