# Deal Lifecycle track — контекст реализации (читать первым)

Этот файл — общий контракт для всех планов трека `deal-lifecycle`. Каждый план (`P*.md`)
самодостаточен и реализуется в отдельной сессии; этот файл + профильный план = всё,
что нужно для работы. Дизайн-обоснование: `TZ.md` (что и зачем), `INTEGRATIONS.md`
(факты о внешних провайдерах).

## Наследование правил

**Полностью действует** `.planning/company-verification/00-IMPLEMENTATION-CONTEXT.md`:
TDD per task + полный `pytest tests/ -q` перед каждым коммитом; conventional commits без
AI-футеров; модели в `models/__init__.py` в FK-порядке; enum'ы `(str, Enum)` + правка
DB-doc в том же коммите; Celery-модули в `_TASK_MODULES`; secrets без дефолтов (+
`.env.example` + CI placeholders в том же коммите); mypy strict для services/schemas;
аудит в той же транзакции; storage через `storage_service`; runtime-настройки через
`_SPECS`; i18n полный (portal ru/uz/en, dashboard ru/uz/tr/fa/zh, telegram ru/uz/tr);
**`webapp/` заморожен**; store UTC / display Asia/Tashkent.

## Порядок реализации и зависимости

| # | План | Домен | Зависит от | Миграция* |
|---|------|-------|-----------|-----------|
| P0 | `P0-DESIGN-SYSTEM.md` | рестайлинг портала под `docs/new-design/` (решение оператора: вариант C — дизайн-система ДО функциональности) | — (первый) | — (без БД) |
| P1 | `P1-MEDIA.md` | медиа (лого компании, фото офферов) | P0 (UI-примитивы) | 0022 |
| P2 | `P2-DEALS.md` | сделки: Deal, Trade Room, отклики на RFQ | P0 + R3 contracts (shipped) | 0023 |
| P3 | `P3-PAYMENTS.md` | escrow-платежи (stub) | P2 | 0024 |
| P4 | `P4-MATCHING.md` | AI-push поставщикам, бейджи ролей, доработки формы оффера | P2 (CTA «Откликнуться») | 0025 |
| P5 | `P5-COMPLIANCE.md` (R5) | вещества, ТН ВЭД/CAS, гейт публикации | P1 (форма оффера) | 0026 |
| P6 | `P6-LAB.md` (R5) | лаборатории, образцы | P2 (лаб-док в сделке), P5 (вещество в заявке) | 0027 |
| P7 | `P7-PROVIDERS-LIVE.md` (R6) | live: Didox, банк, гос-реестры | P2+P3; внешние доступы | 0028+ |

\* Номера миграций номинальные от головы `0021`; на момент реализации брать
**следующий свободный** номер и не менять чужие. Один план = свои миграции, не трогать
таблицы чужого домена (связь — через FK по id и события).

P0 — строго первый (все фронтовые работы P1+ строятся из его примитивов/токенов).
После P0: P1 можно делать параллельно с P2. P5/P6 детализируются после приёмки R4
(сейчас — скелеты). Фронтовые волны P1–P6 обязаны использовать только `shared/ui`
примитивы и токены P0 — новый цвет = новый токен, не инлайн-hex.

## Новые bounded-контексты

| Контекст | Модели | Сервисы | Правило границы |
|---|---|---|---|
| `deals` | `app/models/deals.py` | `deal_service`, `rfq_response_service` | не импортирует модели contracts/verification напрямую — реагирует на события |
| `payments` | `app/models/payments.py` | `escrow_service` | двигает Deal только через `deal_service.transition()` |
| `catalog/compliance` | `app/models/substances.py` | `substance_service`, `offer_compliance_service` | расширяет marketplace, не меняя его инварианты |
| `lab` | `app/models/lab.py` | `lab_service`, `sample_service` | — |
| медиа | без новых моделей (ALTER companies; `seller_offer_files` существует) | расширение `storage_service` | — |

Кросс-контекстные эффекты — **только** через `domain_events` outbox (запись в той же
транзакции, что и смена состояния). Пример: контракт активирован (`CONTRACT_ACTIVATED`,
пишет contracts-контекст R3) → обработчик в deals переводит Deal в `contract_signed`.

## Интеграции — общий паттерн (см. INTEGRATIONS.md)

Каждый провайдер: `backend/app/integrations/<provider>/client.py` по образцу
`integrations/eimzo/client.py` — typed-клиент, timeouts (5s/15s), circuit breaker
(`integrations/circuit_breaker.py`), строка в `integration_call_log` на каждый вызов,
`ProviderUnavailable` вместо сырых HTTP-ошибок, режим stub|live через runtime-настройку
`<provider>_mode` (в `_SPECS`), stub-фабрика как `get_eimzo_client()`. Вызовы — на
Celery-очереди `verify` (существующая; выделение отдельной `integrations`-очереди — только
если появится реальная конкуренция за воркеров). Недоступность провайдера деградирует
(retry/`unavailable`/ручной путь) и никогда не блокирует Deal-пайплайн.

## Существующий код — что зеркалить (дополнение к таблице R1-R3)

| Нужно | Образец |
|---|---|
| Таблица переходов статусов | `request_service.VALID_TRANSITIONS` + `contract_service._TRANSITIONS` |
| Гонка финального перехода (double-activation) | `contract_service.sign` (SELECT … FOR UPDATE) |
| Portal-уведомления | R2 `portal_notifications` (bell) — `notification_service` |
| Файлы к сущности | `SellerOfferFile` + `storage_service.upload_offer_file` |
| Presigned-выдача документов | R3 contracts `GET …/document` (TTL ≤ 600 s) |
| Immutable evidence + sha256 | R3 `signature_evidence`, `verify_contract_integrity` beat |
| Директория верифицированных компаний | R3 `GET /portal/companies/directory` (rate-limit, только verified) |
| Идемпотентный сид | `app/seed/seed_contract_templates.py` |
| Экран-визард portal | `portal/src/features/company-wizard`, `request-wizard` |

## Анти-галлюцинационные правила для сессий реализации

1. Реализуешь план P<N> — **не читай и не выполняй другие P-планы**; всё нужное из них
   уже продублировано в твоём плане в разделе «Интерфейс к соседним доменам».
2. Перед использованием любого упомянутого символа (сервис, модель, эндпоинт) — открой
   файл и проверь фактическую сигнатуру; план может отставать от кода.
3. Если в плане и коде расходятся имена/номера миграций — прав код, план правится
   в том же коммите (плюс пометка в Progress-секции плана).
4. Каждый план завершается Progress-секцией — отмечай выполненные задачи (`[x]`) с хешем
   коммита, чтобы следующая сессия могла продолжить без пересканирования.
