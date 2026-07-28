# P7 — Live-интеграции: Didox, Escrow-банк, гос-реестры (R6)

> Prereq: `00-CONTEXT.md`, P2 (Deal), P3 (`escrow_payments`, `provider_events`),
> R1 (`verification_cases`/`checks`), R3 (шлюз `integrations/eimzo`, evidence-паттерн).
> Факты и контракты адаптеров — **`INTEGRATIONS.md`** (главный документ этого плана).
> **Методология: строгий TDD** (тест до кода per task; полный `pytest tests/ -q` +
> фронт-гейты перед каждым коммитом). Внешние API в CI не вызываются никогда — клиенты
> мокаются по образцу `integrations/eimzo`; против реальных тест-контуров (testapi3,
> банковский sandbox) — только ручные интеграционные прогоны вне CI, журналируемые
> в Progress-секции.

## Что здесь на самом деле блокировано, а что нет

Скелет читался как «весь план ждёт доступов». Это неверно: доступ нужен **исходящему**
вызову, а у двух подпланов из четырёх основная работа — **входящая или наша собственная**.
Разделение проведено по одному критерию: *можно ли это написать и доказать тестом,
не имея чужого токена*.

| Подплан | Строится и доказывается сейчас | Требует доступа | Сессия |
|---|---|---|---|
| **P7.b** Escrow-банк | входящий контур целиком: маршрут вебхука, нормализация события, идемпотентность, `apply_provider_event`, provider-отметка платежа, правило дрейфа, очередь оператора | `LiveEscrowClient` (спека банка) — **только исходящая половина** | **эта** |
| **P7.c** Гос-реестры | контракт адаптера, immutable-снапшоты, два чека, **полуавтомат оператора** (реальная польза сегодня) | ПЦД/OneID — только `LiveGovRegistryClient` | **эта** |
| **P7.a** Didox | — (см. ниже, почему не сейчас) | partner-token + договор | отдельная |
| **P7.d** Chem-registry | нечего делать: источник истины — наш `substances` (P5) | гос-API не существует | — |

**Почему P7.a не в этой сессии.** У Didox единственный подплан, где *ничего* нельзя
проверить: и клиент, и доменный шов, и polling пишутся против пересказа документации
(`api-docs.didox.uz` программно не отдаётся), а первая же сверка с testapi3 перепишет
маппинг полей. Скелет сам требует «по одному провайдеру за сессию»; сессия без токена
даст ~600 строк недоказуемого кода и решение о схеме контракта, принятое вслепую.
Поэтому P7.a **детализирован здесь до задач** (W8–W10 ниже, вместе с четырьмя
проектными решениями, которые от токена не зависят), а реализуется в сессии, где
токен есть. Оценка INTEGRATIONS.md §5 («маппинг — дни») от этого не страдает.

**Demo (Definition of Done этой сессии):**
1. Банк-эмулятор шлёт `POST /api/v1/webhooks/escrow/generic` c `funded` → платёж
   становится `funded` **без оператора**, сделка уезжает в `paid_escrow`, повтор того же
   вебхука ничего не меняет; событие `refunded` платёж **не** трогает, а встаёт в
   очередь «банк говорит X, у нас Y» на `/escrow`.
2. Оператор на карточке верификации жмёт «Проверить в реестре», вносит результат
   открытого сервиса (my.soliq.uz / license.gov.uz) + прикладывает скриншот →
   в `registry_snapshots` ложится immutable-строка с sha256, чек `gov_registry`
   становится `passed`, кейс переоценивается.

---

## Поправки к скелету (правило 3 из `00-CONTEXT` — прав код)

1. **Миграция `0029`, не `0028`.** Голова — `0028_lab` (P6). Миграция в этом плане
   одна и обслуживает только P7.c; P7.b схемы не требует вовсе (см. п. 2–3).
2. **`provider_events` уже существует** (P3, миграция 0024) вместе с
   `UNIQUE (provider, external_id)`. Идемпотентность вебхука — уже инвариант схемы;
   P7.b пишет только маршрут и обработчик, ничего не добавляя в БД.
3. **`escrow_payments.*_marked_by` уже nullable**, и docstring модели уже говорит
   «NULL on the live rail, where the provider event is the evidence instead».
   Provider-отметка платежа ложится в существующие колонки.
4. **`ESCROW_WEBHOOK_SECRET` — секрет с пустым дефолтом**, а не «без дефолта».
   Правило «секреты без дефолтов» защищает от тихой мисконфигурации на старте, но
   рельс `live` — **runtime-настройка**, и стартовый валидатор её не видит: обязательный
   секрет заставил бы каждый деплой (включая тех, кто escrow вообще не включает)
   его придумывать. Образец уже есть — `ESKIZ_EMAIL`/`ESKIZ_PASSWORD` (пустой дефолт,
   обязательны только при `SMS_PROVIDER=eskiz`). Проверка переезжает в маршрут.
5. **Ответ на вопрос, оставленный P3** в docstring `apply_provider_event`
   (`cancelled` недостижим для `system` — нужен сервисный аккаунт или расширение
   `_ACTOR_RULES`): **ни то, ни другое**. См. решение в W2 — `funded`/`released`
   применяются автоматически, `refunded` — никогда.
6. **`registry_snapshots` не существует** — таблица упомянута только в docstring
   `models/integration.py` («evidence lives in … `registry_snapshots` instead»).
   Создаётся здесь.
7. **`gov_registry`/`vat_status` в `VerificationCheckType`** — docstring enum'а обещает
   их как «P2 adds»; фактически добавляются здесь (`ALTER TYPE … ADD VALUE`).
8. **`chem_registry_mode` уже в `_SPECS`** (P5) и `integrations/chem_registry/` уже
   существует stub-ом. P7.d не добавляет ни строки — только абзац в документации о том,
   что это осознанно.
9. **Скелет просил очередь `integrations`** — не заводим. `00-CONTEXT` разрешает
   выделять её «только если появится реальная конкуренция за воркеров». Исходящие
   вызовы идут на существующую `verify`, входящий применятель — на `default`
   (он не звонит наружу, он двигает сделку).

---

# P7.b — Escrow-банк: входящий контур

Банк неизвестен, но **форма события известна нам**: у нас есть `EscrowPayment`,
`provider_ref` и машина `pending → funded → released/refunded`. Поэтому контур
строится от нашей нормализованной формы, а адаптер конкретного банка — это одна
функция-маппер в реестре.

## Wave 1 — Нормализация события и применение

### T1.1 `integrations/escrow/events.py` — нормализованное событие + реестр мапперов
Тест первым: `tests/test_escrow_events.py`.

```python
@dataclass(frozen=True)
class NormalizedEscrowEvent:
    external_id: str      # идемпотентность (provider_events.external_id)
    provider_ref: str     # ключ к escrow_payments.provider_ref
    status: str           # 'pending' | 'funded' | 'released' | 'refunded'
    amount: Decimal | None
    currency: str | None
    occurred_at: datetime | None
    raw_status: str       # что банк сказал буквально — в evidence
```
- `MAPPERS: dict[str, Callable[[dict], NormalizedEscrowEvent]]`, одна запись —
  `"generic"` (наш собственный контракт: те же имена полей). Добавить `kapitalbank` =
  добавить функцию, ничего больше.
- `extract_external_id(provider, body) -> str` — вызывается **до** маппинга (сырой
  инбокс пишется раньше разбора); если провайдер не дал id — `sha256(body)`, чтобы
  повторная доставка того же тела схлопнулась по существующему UNIQUE.
- Исключения `UnknownProvider`, `MalformedEvent`.
- **Границы:** `integrations/` не импортирует доменные модели — статус нормализуется
  в `str` из константного набора, `EscrowStatus` из него делает сервис.

### T1.2 `escrow_service.mark_from_provider` (рефакторинг `mark`)
`mark()` требует `staff_user` и note (`StaffRequired`, `NoteRequired`) — это правильно
для stub-рельса и неверно для live. Общее ядро выносится в `_apply_mark(db, payment,
to_status, *, note, staff_user_id, provider_event_id)`; публичные двери:
- `mark(...)` — сигнатура и семантика не меняются (staff обязателен) — **все
  существующие тесты P3 остаются зелёными без правок**;
- `mark_from_provider(db, payment, to_status, event)` — `*_marked_by = NULL`,
  `note = f"provider:{event.provider}:{event.external_id}"`, тот же row-lock, тот же
  `_drag_the_deal`, то же событие и аудит (`escrow.mark_provider`).
- Инвариант, который тест обязан зафиксировать: **provider не может отметить платёж,
  открытый на stub-рельсе** (`payment.mode == 'stub'` → `WrongRail`). Иначе флип
  runtime-настройки задним числом изменил бы правила для уже открытых платежей —
  ровно то, ради чего `mode` заморожен на строке.

### T1.3 `escrow_service.apply_provider_event` — настоящее тело
Заменяет заглушку P3. Порядок: `processed?` → маппер → платёж по `provider_ref` →
проверки → отметка **или** удержание.

**Решение по вопросу P3 (`cancelled` недостижим для `system`):** не расширяем
`_ACTOR_RULES` и не заводим сервисный аккаунт.
- `funded`, `released` — **применяются автоматически**: они только двигают сделку
  вперёд и целевые статусы (`paid_escrow`, `completed`) и так `system`-only.
- `refunded` — **никогда не применяется автоматически**. Возврат убивает сделку, а
  решение убить сделку имеет причину и человека (FR-D8: из `paid_escrow` возврат
  вообще требует сперва спора). Событие записывается, помечается `processed` и
  удерживается с префиксом `hold:` в `provider_events.error` — это и есть очередь
  оператора.
- `released`, пришедший на неотгруженную сделку, тоже удерживается
  (`EscrowReleaseBeforeDelivery` остаётся в силе для provider-пути — тест обязателен).
- Прочие удержания: неизвестный `provider_ref`, платёж на stub-рельсе, недопустимый
  переход. Каждое — со своим суффиксом, чтобы оператор в дашборде читал причину, а
  не «409».
- `HOLD_PREFIX = "hold:"` — модульная константа; «очередь» = выборка по префиксу.
  Новой колонки не заводим: `provider_events` — evidence, `error` уже свободный текст,
  а строка **самоочищается** — как только оператор отметит платёж вручную, событие
  перестаёт попадать в выборку (условие сверяет заявленный статус с фактическим).

### T1.4 Тесты W1 (красные до кода)
`tests/test_escrow_provider_events.py`: идемпотентность повторной доставки; `funded`
двигает сделку; повтор `funded` — no-op; `refunded` не двигает ничего и удерживается;
`released` до `delivered` удерживается; неизвестный `provider_ref` удерживается;
stub-платёж отказывает provider-отметке; неизвестный провайдер; кривой payload.

## Wave 2 — Маршрут вебхука и задача

### T2.1 `POST /api/v1/webhooks/escrow/{provider}` (`app/api/webhooks_escrow.py`)
- Аутентификация: заголовок `X-Escrow-Token`, сверка `hmac.compare_digest` с
  `settings.ESCROW_WEBHOOK_SECRET` (образец `telegram_webhook.py`).
  **Секрет не задан → 404** (эндпоинт не должен подтверждать своё существование
  неаутентифицированному сканеру), **не совпал → 401**.
- Порядок ровно такой: прочитать сырое тело → `extract_external_id` →
  `record_provider_event` → **commit** → поставить Celery-задачу → `200 {"ok": true}`.
  Разбор и применение — в задаче, поэтому банк получает 200 даже на payload, который
  мы не поняли: непонятое событие всё равно evidence.
- Не-JSON тело записывается как `{"_raw": "<text>"}` — 200, разбор упадёт в задаче.
- Роутер регистрируется в `create_app()`; в OpenAPI помечен `include_in_schema=False`
  (внешний контур, не часть публичного API).

### T2.2 Celery: применятель + подметатель
- `app.tasks.payments.apply_escrow_provider_event(event_id)` — очередь `default`
  (наружу не звонит), идемпотентен, никогда не поднимает исключение наружу.
- Beat `sweep_provider_events` (каждые 5 мин) — берёт `processed=false` пачкой:
  страховка на случай, когда commit прошёл, а `apply_async` не долетел (Redis моргнул).
  Именно ради этого запись и постановка задачи разделены.
- Модуль уже в `_TASK_MODULES`; в `schedule.py` добавляется одна запись.

### T2.3 Тесты W2
404 без секрета; 401 с чужим токеном; 200 + строка инбокса; повторная доставка → одна
строка; не-JSON → 200 и `_raw`; падение брокера не роняет 200; подметатель добирает
незаявленное событие.

## Wave 3 — Сверка (дрейф) и очередь оператора

### T3.1 Beat `reconcile_escrow_payments` (очередь `verify`)
Единственное место, которое **звонит наружу**, поэтому `verify`. Для каждого
не-терминального платежа на live-рельсе: `client.get_status(provider_ref)`.
- Провайдер продвинулся и переход автоприменим → применить (тот же путь, что вебхук).
- Провайдер разошёлся с нами (банк `released`, сделка не `delivered`; банк `refunded`)
  → **алерт, не автопереход** (требование скелета) + удержанная запись в инбоксе.
- `ProviderUnavailable`/отсутствие клиента → тихий no-op: недоступность банка не
  двигает и не ломает пайплайн (инвариант деградации).
- Клиент инжектится параметром, чтобы тест гонял сценарии на фейке.
- `LiveEscrowClient` **не пишется** — `get_escrow_client` для `live` по-прежнему
  поднимает `ProviderUnavailable` с текстом «нужна спека банка». Так задача сегодня
  честно ничего не делает, а правило дрейфа уже зафиксировано тестом.

### T3.2 `GET /admin/escrow/provider-events` + блок в дашборде
Аналитик читает, admin действует существующей кнопкой отметки. Список удержаний:
что сказал банк, что у нас, почему удержано, ссылка на платёж. Отдельной кнопки
«разрешить» нет — разрешение это и есть ручная отметка платежа, после которой строка
уходит из выборки сама.

---

# P7.c — Гос-реестры: контракт, снапшоты, полуавтомат

ПЦД нет и, судя по INTEGRATIONS.md §3, может не быть долго. Но открытые сервисы
(my.soliq.uz — НДС, license.gov.uz — лицензии) работают **сегодня** и их результат
сегодня же никуда не записывается: оператор смотрит в браузер и решает в уме.
Полуавтомат превращает это в evidence.

## Wave 4 — Схема и шлюз

### T4.1 Миграция `0029_gov_registry` + модель + enum'ы
- `ALTER TYPE verification_check_type ADD VALUE 'gov_registry'`, `'vat_status'` —
  внутри `op.get_context().autocommit_block()` (образец `0020_eimzo`, `0027`, `0028`).
- **`registry_snapshots`** (`app/models/registry.py`, регистрируется в
  `models/__init__.py`): `id`, `company_id` FK NOT NULL, `kind` Text NOT NULL
  (`company | licenses | vat`), `source` Text NOT NULL (`registry | manual`),
  `provider` Text NOT NULL (`pcd | oneid | manual`), `payload` JSONB NOT NULL
  (нормализованный DTO), `raw_status` Text NULL, `evidence_path`/`evidence_sha256`
  Text NULL (скриншот полуавтомата — тот же паттерн, что `signature_evidence`),
  `note` Text NULL, `created_by` FK `staff_users` NULL (NULL = автоматический),
  `fetched_at` timestamptz NOT NULL, `created_at`.
  Индекс `(company_id, kind, id DESC)` — «последний снапшот вида X» единственный
  горячий запрос. CHECK на допустимые `kind`/`source`.
  **Строка immutable:** нет `updated_at`, нет ни одного пути на UPDATE. Новая проверка —
  новая строка; история проверок компании — это и есть история строк.

### T4.2 `integrations/gov_registry/`
DTO `CompanySnapshot` (name, status, director, oked, address, registered_at),
`LicenseSnapshot` (regime, number, issued_at, expires_at, issuer, status),
`VatSnapshot` (registered: bool, certificate_no, valid_from).
Protocol `GovRegistryClient` (`lookup_company/lookup_licenses/lookup_vat`),
`StubGovRegistryClient` (все методы → `ProviderUnavailable`: у нас нет канала, и
делать вид, что есть, хуже, чем сказать «нет»), фабрика `get_gov_registry_client(db)`
по новой runtime-настройке `gov_registry_mode` (`stub | live`, ships `stub`, `choices`).

### T4.3 `registry_service`
`record_snapshot(...)` — immutable-вставка + аудит в той же транзакции;
`latest(db, company_id, kind)`; `fetch_and_record(db, company, kind)` — live-путь,
`ProviderUnavailable` → `None` (не исключение наружу).

## Wave 5 — Чеки и полуавтомат оператора

### T5.1 Чистые функции чеков (`verification_checks.py`)
`check_gov_registry(company, snapshot)`:
нет снапшота → `unavailable`; реестр говорит «ликвидирована» → `failed`; ИНН/название
совпали → `passed`; название разошлось → `warning` (реестр авторитетен, но у нас может
лежать вариант написания — это повод посмотреть, а не отказать).
`check_vat_status(company, snapshot)`: нет снапшота → `unavailable`; есть свидетельство
→ `passed`; **нет свидетельства → `warning`, не `failed`** — не каждая компания
обязана быть плательщиком НДС, и отказ по этому основанию был бы неверен юридически.

### T5.2 Эвалюатор перестаёт залипать на `unavailable`
**Найденный при детализации латентный баг R1**, который P7.c обязан починить до того,
как заведёт первый чек, способный стать `unavailable`: `on_check_completed` считает
`unavailable` «ещё не закончился», а `approve()` работает только из `pending_review` —
значит чек, исчерпавший 5 ретраев, навсегда запирает кейс в `checks_running`, и
**ручной путь перестаёт работать**, что прямо нарушает инвариант R1 («недоступность
провайдера не блокирует ручной путь»).
Правка минимальна и точна: `unavailable` блокирует эвалюацию, **пока ретраи не
исчерпаны** (`check.attempts < MAX_CHECK_ATTEMPTS`), после чего перестаёт. Константа
`MAX_CHECK_ATTEMPTS = 5` объявляется в `verification_service` и используется в
`tasks/verification.py` (сейчас `max_retries=5` зашит) — одно число в одном месте.
Тест: чек с исчерпанными ретраями не мешает кейсу уехать в `pending_review`.

### T5.3 Чеки заводятся только когда есть чему их наполнять
`_R1_CHECK_TYPES` не трогаем. Registry-чеки добавляются к кейсу **по факту появления
снапшота** (полуавтомат оператора или успешный live-fetch), а автоматически при
`submit_case` — только когда `gov_registry_mode='live'`. Настройка ships `stub`,
поэтому сегодня поведение сабмита не меняется ни на йоту.

### T5.4 `POST /admin/verification/cases/{case_id}/registry-check`
multipart: `kind`, `outcome` (нормализованные поля формы), `note`, опциональный
скриншот (PDF/JPEG/PNG, `storage_service.validate_upload`). Делает в одной транзакции:
снапшот `source='manual'` + evidence → upsert `VerificationCheck` нужного типа →
пересчёт `on_check_completed` → аудит. Гард — `require_analyst_or_admin`
(это работа верификатора, не админа).
`GET /admin/verification/cases/{case_id}` дополняется блоком `registry` —
последние снапшоты по трём видам.

## Wave 6 — Дашборд и i18n

### T6.1 Карточка кейса: блок «Реестры»
Три вида, для каждого — дата, источник (`реестр`/`вручную`), кто внёс, ссылка на
скриншот (presigned, TTL 600 s), кнопка «Проверить в реестре» → диалог с полями по
виду. Плюс блок удержанных provider-событий на `/escrow` (T3.2).
Только примитивы `components/ui`, тёмная тема P0.

### T6.2 Локали дашборда `ru/uz/tr/fa/zh` — полное дерево ключей.

## Wave 7 — Документация и Progress
DB-архитектура (`registry_snapshots` DDL + changelog), `docs/admin-guide-ru.md` §11
(как проверять в реестре и что значит каждый исход; что делать с удержанным
provider-событием), дельты в `backend/CLAUDE.md` / `dashboard/CLAUDE.md` /
`deploy/CLAUDE.md`, `deploy/.env.example` + CI-плейсхолдеры для `ESCROW_WEBHOOK_SECRET`,
Progress-секция.

---

# P7.a — Didox (отдельная сессия; нужен partner-token)

Детализация сделана сейчас, чтобы сессия с токеном была прямой реализацией.
Четыре решения, которые от токена не зависят и должны быть приняты до кода:

1. **Чей документ юридический.** При `signing_provider='didox'` юридический артефакт —
   «Договор НК» внутри Didox (уходит в роуминг my.soliq.uz), а наш отрендеренный PDF
   становится превью. Поэтому Didox-архив кладётся в **отдельную** пару
   `provider_archive_path`/`provider_archive_sha256`, а не переписывает
   `generated_document_path`/`document_sha256`: два артефакта — две пары хешей.
2. **Провайдер замораживается**, как `escrow_payments.mode`: выбран при создании,
   после появления `provider_doc_id` не меняется.
3. **Статус `50` (аннулирован НК) не добавляет состояние в нашу машину.** `active`
   терминален, и на активном контракте уже может ехать Deal; тихий перевод в новое
   терминальное состояние оставил бы сделку без опоры. Пишем `provider_status`,
   поднимаем алерт стаффу — это юридическое событие для человека.
4. **Активация по Didox идёт не через `_maybe_activate`.** Тот требует двух строк
   `contract_signatures` с нашим `signature_evidence`; подписи Didox мы не видели.
   Нужна отдельная дверь `contract_service.activate_from_provider(contract, archive)`,
   которая пишет архив как evidence — подделывать наши строки подписей нельзя.

Волны: **W8** шлюз (`integrations/didox/`: `auth_user` с кэшем user-key в Redis на
360 мин, `create_contract`, `timestamp`, `sign`, `join_signatures`, `get_document`,
`list_updated`, `fetch_archive`; `StubDidoxClient`; `didox_mode`; секреты
`DIDOX_PARTNER_TOKEN`/`DIDOX_BASE_URL`) → **W9** доменный шов (миграция 0030:
`contracts.signing_provider|provider_doc_id|provider_status|provider_synced_at|
provider_archive_*`; маппинг наших variables в `ContractDoc`; `didox_service`) →
**W10** `poll_didox_statuses` (инкрементально по `dateFromUpdated`, идемпотентно) +
шаг timestamp в портальном `features/eimzo-sign` + приёмка на testapi3.

**Первое, что делает та сессия, — сверяет пути и имена полей с api-docs.didox.uz**;
всё, что написано о путях в INTEGRATIONS.md §1, — пересказ, а не первоисточник.

---

# P7.d — Chem-registry: осознанно ничего

`integrations/chem_registry/` (stub) и `chem_registry_mode` уже стоят с P5.
Машиночитаемого гос-реестра не существует (INTEGRATIONS.md §4), источник истины —
наш `substances`. Live-адаптер появится, только если НРОХВ/ПЦД дадут API; триггер —
принятие закона «О химической безопасности». Мониторинг — операторская задача, не код.

---

## Правила для всех подпланов
Паттерн шлюза из `00-CONTEXT.md` (circuit breaker, `integration_call_log`, stub-фабрика,
`ProviderUnavailable`, деградация); каждый подплан детализируется в задачи только после
получения фактической документации провайдера; **ничего не менять в моделях P2/P3/P5** —
только клиенты, задачи и маппинг (единственное исключение оговорено в T5.2 и является
починкой бага, а не изменением модели).

## Заведомые пробелы (не молча)
- **`LiveEscrowClient` не написан** — исходящая половина ждёт спеку банка. Правило
  дрейфа и автоприменение уже зафиксированы тестами на фейковом клиенте.
- **`LiveGovRegistryClient` не написан** — ждёт ПЦД. Полуавтомат заменяет его функцию
  на 90 % и даёт то, чего у ПЦД-пути не будет: подпись оператора под результатом.
- **P7.a целиком** — см. выше.
- **e2e-спеки нет** (общий пробел P1–P6: в репозитории нет e2e-пути к верифицированной
  компании). Проверка — ручная браузерная.

---

## Progress
- [ ] детализация плана → задачи T1.1…T7.1
- [ ] W1 — нормализация provider-события + `mark_from_provider` + `apply_provider_event`
- [ ] W2 — маршрут вебхука + применятель + подметатель
- [ ] W3 — сверка/дрейф + очередь оператора
- [ ] W4 — миграция 0029 + `integrations/gov_registry` + `registry_service`
- [ ] W5 — чеки + починка эвалюатора + полуавтомат оператора
- [ ] W6 — дашборд + i18n
- [ ] W7 — документация + Progress
- [ ] P7.a (W8–W10) — отдельная сессия, нужен partner-token
