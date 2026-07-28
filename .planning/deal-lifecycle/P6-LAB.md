# P6 — Lab: лабораторные паспорта, заказ анализа, образцы (R5)

> Prereq: `00-CONTEXT.md`, P1 (файлы оффера), P2 (`deal_documents`, Trade Room),
> P4 (портальная схема карточки + инертный вес скоринга), P5 (вещество в оффере).
> ТЗ: блок C, FR-L1–L5.
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> **Матрицы переходов `lab_order` и `sample_request` пишутся тестом ДО реализации.**

**Demo (Definition of Done):** продавец загружает лаб-паспорт на оффер → бейдж
«Лаб. паспорт» на карточке маркета + фильтр находит оффер; продавец без паспорта жмёт
«Заказать анализ» → заявка попадает в очередь дашборда → оператор ведёт
`submitted → accepted → sample_awaited → in_analysis → done`, при `done` прикрепляет
паспорт → оффер получает бейдж **«Laboratory Verified»** (независимое подтверждение) и
попадает в отдельный фильтр; покупатель по офферу с включёнными образцами проходит
`requested → accepted → sent (курьер + трек) → received`; каждая смена статуса — колокол
в портале нужной стороне, новая лаб-заявка — карточка в staff-группу Telegram.

---

## Поправки к скелету (правило 3 из `00-CONTEXT` — прав код)

1. **Миграция `0028`, не `0027`.** Голова — `0027_compliance` (P5).
2. **`DealDocumentKind.lab_passport` уже существует** (P2, миграция 0023). Расширять
   нужен только `offer_file_kind` (`ALTER TYPE … ADD VALUE`).
3. **`lab_orders.result_document_path` заменён на пару FK** `result_offer_file_id` /
   `result_deal_document_id`. Путь в S3 уже живёт в `seller_offer_files.storage_path` /
   `deal_documents.storage_path`; второй экземпляр строки-пути разъедется с файловой
   строкой при первом же удалении. FK + CHECK «`done` ⇒ есть результат» — инвариант БД,
   а не соглашение.
4. **Уведомления не отдельная волна.** Колокол пишется в той же транзакции, что и
   переход (правило `escrow_service._notify_both`), поэтому живёт в W2/W3 рядом с
   переходами; в W6 остаётся только staff-карточка Telegram (через outbox) и документация.
5. **Бейдж «Лаб. паспорт» не кешируется колонкой.** `lab_verified` — колонка (его
   ставит только система), наличие паспорта — производное от `files` (в каталожном
   запросе они уже `selectinload`-нуты) + `EXISTS` в SQL-фильтре маркета.

---

## Wave 1 — Схема

### T1.1 Миграция `0028_lab` + модели + enum'ы
Один контекст — одна миграция (сервисы W2/W3 стоят на ней целиком).

Enum'ы (`enums.py`, PG-типы создаются в миграции):
- `lab_order_status`: `submitted | accepted | sample_awaited | in_analysis | done | rejected`
- `sample_request_status`: `requested | accepted | declined | sent | received | rejected_by_buyer`
- `offer_file_kind += lab_passport` — `ALTER TYPE … ADD VALUE` внутри
  `op.get_context().autocommit_block()` (образец `0020_eimzo`, `0027_compliance`).

Таблицы — модуль `app/models/lab.py` (контекст `lab` из `00-CONTEXT`):

- **`lab_partners`**: `id`, `name` NOT NULL, `contacts` JSONB (`{phone, email, address,
  contact_name}` — свободная форма, справочник ведёт админ), `company_id` FK
  `companies` NULL (партнёр может быть зарегистрированной компанией с ролью
  `laboratory` — enum уже есть; связь опциональная и ни на что не влияет),
  `note` NULL, `is_active` default true, timestamps.
- **`lab_orders`**: `id`, `number` Text UQ (`LAB-YYYY-NNNNNN`, генерится сервисом по
  образцу `deal_service` — оператор называет его в телефонном разговоре),
  `company_id` FK NOT NULL (заказчик), `created_by_user_account_id` FK NOT NULL,
  `offer_id` FK `seller_offers` NULL, `deal_id` FK `deals` NULL,
  **CHECK `offer_id IS NOT NULL OR deal_id IS NOT NULL`** (заявка всегда о чём-то
  конкретном), `substance_id` FK `substances` NULL, `sample_volume` Text NULL,
  `comment` Text NULL, `status` NOT NULL default `submitted`,
  `lab_partner_id` FK NULL, `result_offer_file_id` FK `seller_offer_files` SET NULL,
  `result_deal_document_id` FK `deal_documents` SET NULL,
  **CHECK `status <> 'done' OR (result_offer_file_id IS NOT NULL OR
  result_deal_document_id IS NOT NULL)`**, `operator_note` Text NULL,
  `rejected_reason` Text NULL, `handled_by` FK `staff_users` NULL,
  `completed_at` NULL, timestamps; индексы `(status, id)`, `(company_id, id)`, `(offer_id)`.
- **`sample_requests`**: `id`, `offer_id` FK NOT NULL, `buyer_company_id` FK NOT NULL,
  `seller_company_id` FK NOT NULL (копируется из оффера в момент создания — иначе
  список продавца зависит от того, не переписали ли оффер), `created_by_user_account_id`
  FK NOT NULL, **CHECK buyer ≠ seller**, `status` NOT NULL default `requested`,
  `qty` Text NULL, `delivery_address` Text NOT NULL, `courier` Text NULL,
  `tracking_ref` Text NULL, `decline_reason` Text NULL,
  `accepted_at`/`sent_at`/`received_at` NULL (таймлайн из трёх штампов вместо таблицы
  истории — машина линейная и короткая, `deal_status_history` тут был бы оверкилл),
  timestamps; **partial UQ `(offer_id, buyer_company_id) WHERE status IN
  ('requested','accepted','sent')`** — один живой запрос на пару (образец
  `uq_rfq_response_active`); индексы `(seller_company_id, status)`, `(buyer_company_id, id)`.
- **ALTER `seller_offers`**: `samples_available` bool NOT NULL default false,
  `sample_price` Numeric(14,2) NULL (NULL при `samples_available` = бесплатно),
  `sample_dispatch_days` Integer NULL, `lab_verified` bool NOT NULL default false.

Модель `SellerOffer` получает property `has_lab_passport` (по `files`, рядом с
`photos`/`cover_file_id`) и `lab_passport_file_id`.

**Acceptance:** `test_migration_0028` (up → down → up на эфемерном Postgres; наличие
типов/таблиц/колонок; оба CHECK'а и partial-UQ реально отвергают нарушение),
одноголовость (`alembic heads == 0028`) в существующих `test_migration_00XX`,
DB-doc **v1.12** и `models/__init__.py` (FK-порядок) в том же коммите.

---

## Wave 2 — Лаборатории

### T2.1 `lab_service`: справочник партнёров + создание заявки (mypy strict)
- `list_partners(db, *, active_only)`, `create_partner`, `update_partner`,
  `set_partner_active` — аудит на write-путях, без DELETE (образец `substance_service`).
- `create_order(db, *, company, account, offer=None, deal=None, substance_id, sample_volume,
  comment) -> LabOrder`: номер `LAB-YYYY-NNNNNN`; ровно один из offer/deal обязателен
  (`LabOrderTargetMissing`); оффер должен принадлежать компании-заказчику, сделка —
  включать её стороной (`LabOrderNotAllowed`); эмит `LAB_ORDER_SUBMITTED` в outbox
  (карточку в staff-группу вешает W6), аудит.
- `list_for_company`, `list_queue(db, *, status=None)`, `get`.

### T2.2 Матрица переходов + `done` с результатом (тест ДО кода)
`_TRANSITIONS: dict[LabOrderStatus, set[LabOrderStatus]]`:
```
submitted     → accepted, rejected
accepted      → sample_awaited, rejected
sample_awaited→ in_analysis, rejected
in_analysis   → done, rejected
done          → ∅        rejected → ∅   (терминальные)
```
`transition(db, order, to, *, staff_user, note=None)` — статусы двигает **только staff**
(процесс ручной, ТЗ §3.3); `rejected` требует причину (`ReasonRequired`);
`done` через `transition` запрещён (`LabResultRequired`) — есть отдельный вход:

`complete_with_result(db, order, *, staff_user, content, filename)`:
1. валидирует **PDF** (`storage_service.validate_upload` + `mime == application/pdf`;
   паспорт — документ, не фотография);
2. кладёт файл: заявка по офферу → `storage_service.upload_offer_file(kind=lab_passport)`;
   заявка по сделке → `storage_service.store_deal_file` + строка `deal_documents`
   (`kind=lab_passport`, sha256 — как в P2);
3. проставляет FK результата, `status=done`, `completed_at`;
4. **`offer.lab_verified = True`** — только этот путь его ставит (ТЗ: «независимое
   подтверждение через платформу»); ручная загрузка паспорта продавцом даёт бейдж
   «Лаб. паспорт», но не «Laboratory Verified»;
5. колокол компании-заказчику (`KIND_LAB_ORDER_STATUS`), аудит, эмит
   `LAB_ORDER_COMPLETED`.

Всё — одной транзакцией: отказ на любом шаге не должен оставить `done` без файла
(инвариант продублирован CHECK'ом из T1.1).

**Защита результата:** файл-результат платформенной заявки продавец удалить не может —
`DELETE /portal/…/files/{id}` отвечает 409 `lab_result_locked`. Его загрузил оператор,
это доказательство того, что подтвердила платформа; иначе бейдж «Laboratory Verified»
пережил бы удаление собственного основания.

### T2.3 Portal API (FR-L1, FR-L2)
- `POST /portal/companies/{company_id}/lab-orders` (создание с оффера или по сделке),
  `GET …/lab-orders` (свой список), `GET …/lab-orders/{id}`.
- Загрузка паспорта продавцом — **существующий** `POST …/offers/{id}/files` с
  `kind=lab_passport`: в роутере к ветке «не image» добавляется валидация PDF и
  ре-модерация (см. ниже). Новый эндпоинт не нужен.
- Просмотр паспорта: у владельца — существующий `GET …/offers/{id}/files/{file_id}`;
  в маркете — существующий публичный `GET /webapp/market/offers/{id}/images/{file_id}`
  (он отдаёт любой файл **одобренного** оффера, media_type из строки; ровно так же уже
  отдаются фото и P5-документы).

**Ре-модерация:** `lab_passport` — публичный знак доверия, поэтому его загрузка/появление
на `approved`-оффере возвращает оффер в очередь (`requeue_for_photo_change`, тот же
приём, что для фото), в отличие от SDS/COA, которые только пересчитывают комплаенс.

### T2.4 Dashboard API (очередь оператора + справочник)
- `app/api/admin_lab.py`: `GET /admin/lab-orders` (analyst+, фильтр по статусу),
  `GET /admin/lab-orders/{id}`, `POST /admin/lab-orders/{id}/transition`
  (analyst+, `{to, note}`), `POST /admin/lab-orders/{id}/result` (multipart PDF),
  `POST /admin/lab-orders/{id}/partner` (назначить лабораторию);
  `GET/POST/PATCH /admin/lab-partners` (**admin**), `POST …/{id}/deactivate|activate`.
- Ошибки типизированы: 409 `{code:"invalid_transition", from, to}`,
  422 `{code:"lab_result_required"}`.

**Acceptance:** табличный тест матрицы (все разрешённые и запрещённые пары);
`done` без файла невозможен ни через API, ни через сервис; не-PDF отвергается **до**
записи в S3; `lab_verified` ставится только через `complete_with_result`; ручная
загрузка паспорта даёт `has_lab_passport`, но не `lab_verified`; удаление
файла-результата → 409; заявка по чужому офферу/сделке → 404/403; RBAC
(analyst ведёт заявки, admin правит справочник); колокол приходит заказчику.

---

## Wave 3 — Образцы

### T3.1 `sample_service` (тест-матрица ДО кода, mypy strict)
Машина + **кто именно** имеет право на переход (образец `deal_service._ACTOR_RULES`):
```
requested → accepted (seller) | declined (seller)
accepted  → sent (seller)
sent      → received (buyer)  | rejected_by_buyer (buyer)
declined / received / rejected_by_buyer — терминальные
```
- `request(db, *, offer, buyer_company, account, qty, delivery_address)`:
  гейт `offer.samples_available` (`SamplesNotAvailable`), оффер должен быть `approved` и
  **company-origin** (у TG-продавца нет портального аккаунта, чтобы принять запрос —
  `SamplesNotAvailable`), покупатель ≠ продавец (`OwnOfferSample`), живой запрос уже
  есть → `SampleRequestExists` (ловим IntegrityError partial-UQ в savepoint,
  образец `escrow_service.record_provider_event`).
  `delivery_address` — обязателен; портал предзаполняет его `company.legal_address`
  (ТЗ: «адрес из профиля компании покупателя»), но поле редактируемо: юридический
  адрес и склад — разные места.
- `mark_sent(db, sr, *, account, company, qty, courier, tracking_ref)` — курьер и трек
  обязательны (FR-L3), пишутся штампом `sent_at`.
- `decline(reason)`, `accept()`, `receive()`, `reject_by_buyer(reason)`.
- `list_for_company(db, company_id, *, side)` — `side='incoming'|'sent'`.
- Каждый переход: колокол противоположной стороне (`KIND_SAMPLE_REQUEST_NEW` /
  `KIND_SAMPLE_REQUEST_STATUS`, `dedup=False` — «принят» и «отправлен» разные
  предложения об одном запросе), аудит, эмит в outbox.

### T3.2 Portal API
`POST /portal/market/offers/{offer_id}/samples` (покупатель, `company_id` в теле),
`GET /portal/companies/{company_id}/samples?side=incoming|sent`,
`POST /portal/samples/{id}/{accept|decline|sent|received|reject}` — сторона выводится из
членства вызывающего в buyer/seller компании; чужой запрос → 404.

### T3.3 Поля образцов в форме оффера
`CompanyOfferIn`/`CompanyOfferOut` += `samples_available`, `sample_price`,
`sample_dispatch_days`. Валидация: `sample_price`/`sample_dispatch_days` без
`samples_available` → 422 (иначе в карточке появится цена образца, которого нет);
`sample_price` ≥ 0, `sample_dispatch_days` 1..365.
`PortalMarketOfferOut` += те же три поля (**только портальная схема** — `CatalogOfferOut`
не трогаем, `webapp/` заморожен и его contract-тест обязан остаться зелёным).

**Acceptance:** табличный тест матрицы включая «чужой роли нельзя» (продавец не может
`received`, покупатель не может `sent`); запрос на оффер без образцов → 422; повторный
живой запрос → 409; отправка без курьера/трека → 422; оба списка возвращают только своё;
contract-тест паритета `CatalogOfferOut` зелёный.

---

## Wave 4 — Витрина и скоринг

### T4.1 Бейджи и фильтры маркета (FR-L1, FR-L5)
- `PortalMarketOfferOut` += `has_lab_passport: bool`, `lab_verified: bool`
  (первый — из уже загруженных `files`, второй — колонка).
- `offer_service.list_catalog(..., has_lab_passport: bool|None, lab_verified: bool|None)`:
  первый — `EXISTS (SELECT 1 FROM seller_offer_files WHERE offer_id = seller_offers.id
  AND kind = 'lab_passport')`, второй — равенство по колонке. Два **разных** фильтра
  (ТЗ: «и отдельно — независимо подтверждённые»).
- `GET /portal/market?has_lab_passport=&lab_verified=` — прокидка параметров.

### T4.2 Включение веса «лаб-паспорт» в P4-скоринге
`supplier_matching_service.match_suppliers` перестаёт передавать дефолтный
`has_lab_passport=False`: в group-by запрос добавляется
`bool_or(EXISTS(lab_passport на этом оффере))`, результат идёт в `score_candidate`.
Считаем по **паспорту**, а не по `lab_verified` — так называется вес, и покупателю
важно наличие анализа, а не то, кто его заказывал.
Докстринг модуля («term is wired but inert») правится в том же коммите — иначе он врёт.
Табличный тест `score_candidate` уже покрывает вес; новый тест — что
`match_suppliers` действительно поднимает компанию с паспортом над такой же без него.

**Acceptance:** фильтры возвращают ровно ожидаемые офферы (в т.ч. «паспорт есть, но
`lab_verified=false`»); карточка несёт оба флага; ранжирование меняется предсказуемо;
существующие тесты P4 не переписываются под новый результат без причины.

---

## Wave 5 — Frontend

### T5.1 Portal (`shared/ui`-примитивы и токены P0 — новый цвет = новый токен)
- `entities/lab`: types/api/hooks + `LabBadges` (два бейджа: «Лаб. паспорт» —
  нейтральный, «Laboratory Verified» — verified-тон).
- `entities/sample`: types/api/hooks + `SampleStatusBadge`.
- `features/lab-passport`: блок в форме оффера — загрузить PDF **или** кнопка «Заказать
  анализ через IMEX» с текстом «мы свяжемся и согласуем лабораторию, стоимость и
  порядок передачи образцов»; после отправки — статус заявки прямо в блоке.
- `features/sample-request`: форма запроса на странице оффера маркета (кол-во + адрес,
  предзаполненный из профиля) и панель действий сторон.
- Форма оффера += секция «Образцы» (чекбокс + цена + срок отправки).
- `pages/lab-orders/LabOrdersPage.tsx` — свои заявки со статус-таймлайном.
- `pages/samples/SamplesPage.tsx` — вкладки «Входящие»/«Отправленные» (образец
  `InquiriesPage`), действия по роли, ввод курьера и трека.
- `MarketPage`: два фильтра-чекбокса; `MarketOfferCard`: бейджи; `MarketOfferPage`:
  секция образцов + ссылка на паспорт.
- Trade Room: `features/deal-room/ui/DealLabPanel.tsx` — заказ анализа по сделке и его
  статус; результат виден в существующем блоке документов (`kind=lab_passport`).
- Роуты + пункты меню; локали **ru/uz/en** (включая ключи `notifications.lab_order_status.*`,
  `notifications.sample_request_new.*`, `notifications.sample_request_status.*` —
  колокол рендерится по ключам, отсутствие ключа = ошибка в рантайме).

### T5.2 Dashboard
- `/lab-orders` — очередь оператора: фильтр по статусу, карточка заявки (компания,
  оффер/сделка, вещество, объём, комментарий), кнопки переходов **из ответа API**
  (не переписывать машину на TypeScript — образец `available_marks` в escrow),
  назначение лаборатории, загрузка результата (PDF).
- `/lab-partners` — справочник (admin): создание/правка/деактивация.
- Пункты в `Sidebar`; локали **ru/uz/tr/fa/zh** ×5, включая человекочитаемые названия
  статусов (P5 научил: сырой `sample_awaited` в интерфейсе оператора — дефект).

**Acceptance:** `npm run lint`/`typecheck` в обоих приложениях; паритет ключей локалей;
**визуальная проверка каждого куска в реальном браузере через Playwright MCP** (демо-скрипт
целиком: загрузка паспорта → бейдж → фильтр → заявка → очередь оператора → `done` →
«Laboratory Verified»; запрос образца обеими сторонами до `received`).

---

## Wave 6 — Уведомления в Telegram и документация

### T6.1 Staff-карточка новой лаб-заявки
`app/tasks/notify.py::send_lab_order_to_group` — потребитель outbox на
`LAB_ORDER_SUBMITTED`, чат `_verification_notify_chat_id()` (как карточки верификации,
сделок и escrow), регистрация в `_register_consumers()`. Задача fail-soft, не бросает.
Новые константы в `event_types` + `ALL_EVENT_TYPES` (`LAB_ORDER_SUBMITTED`,
`LAB_ORDER_COMPLETED`, `SAMPLE_REQUEST_CREATED`, `SAMPLE_REQUEST_STATUS_CHANGED`).

### T6.2 Документация
`docs/polymer-intelligence-db-architecture.md` (раздел R5/P6 — в коммите W1),
`docs/admin-guide-ru.md` §10 (очередь лаб-заявок: что значит каждый статус, что `done`
требует PDF, чем «Лаб. паспорт» отличается от «Laboratory Verified», справочник
лабораторий), дельты `backend/CLAUDE.md`, `portal/CLAUDE.md`, `dashboard/CLAUDE.md`,
Progress-секция этого плана с хешами коммитов и списком отклонений.

---

## Интерфейс к соседним доменам

- **Файлы** — только существующие подсистемы: `storage_service.upload_offer_file`
  (P1/Phase 2) и `store_deal_file` + `deal_documents` (P2). Новых файловых механизмов нет.
- **P5 (комплаенс)** — `lab_passport` не входит в `required_docs` ни одного вещества и на
  вердикт не влияет; но он попадает в `offer.files`, поэтому его загрузка идёт через ту же
  ветку роутера, что SDS/COA, и **дополнительно** возвращает оффер в модерацию.
- **P4 (скоринг)** — единственная правка: `has_lab_passport` перестаёт быть дефолтом.
  Веса и порядок сортировки не трогаем.
- **P2 (сделки)** — lab-заявка ссылается на `deals.id` и кладёт результат в
  `deal_documents`; статусы сделки не двигает, событий в deals не пишет.
- **Публичная отдача паспорта** — существующий маршрут одобренного оффера. Он публичен
  by design (под `<img src>`), это поведение Phase 2, и P6 его не расширяет.
- **Кэшбэк-учёт с лабораторией — вне скоупа** (журнала `lab_orders` достаточно).

## Заведомые пробелы (не молча)

- **e2e-спека для P6 не пишется** — в репозитории нет e2e-пути к верифицированной
  компании (тот же пробел, что у P1/P2/P3/P5); проверка — ручная браузерная по демо-скрипту.
  Построение такого хелпера — инфраструктурная работа крупнее самой фичи.
- **SLA лаборатории не моделируется** — ни дедлайнов, ни напоминаний: процесс ручной,
  сроки вне контроля платформы (ТЗ §5, п. 160).
- **AI-совместимость по лаб-параметрам** (MFI/плотность → «подходит ли под литьё») —
  опция R5+ из ТЗ §3.3, в этот план не входит: она требует структурированного разбора
  паспорта, которого нет.

---

## Progress
- [ ] детализация плана → задачи T1.1…T6.2
- [ ] W1 T1.1 — миграция 0028 + модели + enum'ы
- [ ] W2 T2.1–T2.4 — lab_service, матрица, portal + admin API
- [ ] W3 T3.1–T3.3 — sample_service, portal API, поля образцов
- [ ] W4 T4.1–T4.2 — бейджи, фильтры, включение веса P4
- [ ] W5 T5.1–T5.2 — portal + dashboard
- [ ] W6 T6.1–T6.2 — staff-карточка Telegram + документация
