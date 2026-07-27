# P2 — Deals: агрегат Deal, Trade Room, отклики на RFQ

> Prereq: `00-CONTEXT.md`. R3 contracts shipped — обязателен. ТЗ: блок A, FR-D1–D9.
> Ядро трека: комната сделки вокруг существующих Request / SellerOffer / Contract.
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> тест зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> Acceptance-блок волны — минимум тестов, не потолок. Transition-матрица deal_status
> пишется тестом ДО реализации `deal_service`.

**Demo (Definition of Done):** покупатель публикует RFQ → поставщик откликается
(цена/объём/срок) → покупатель акцептует → открывается Deal: чат, документы, таймлайн →
«Создать договор» (предзаполнен из сделки) → обе стороны подписывают (R3 E-IMZO) →
Deal `contract_signed` автоматически (по событию) → … (оплата — P3) → продавец `shipped`
→ покупатель `delivered` → (release — P3) → `completed`. Отмена и спор работают; staff
видит всё в dashboard `/deals`, чат — read-only; все переходы в audit + history.

---

## Wave 1 — Схема и домен

### T1.1 Миграция `0023_deals`
Enum'ы (`(str, Enum)` в `enums.py` + PG ENUM + DB-doc):
- `deal_status`: `negotiation, contract_pending, contract_signed, payment_pending,
  paid_escrow, shipped, delivered, completed, cancelled, disputed`
- `rfq_response_status`: `submitted, accepted, not_selected, withdrawn`
- `deal_document_kind`: `contract, invoice, lab_passport, transport, other`

Таблицы (`app/models/deals.py`, регистрация в `models/__init__.py` после contracts):
- `deals`: id BigInt PK; public_id UUID UQ default gen; number Text UQ
  (`DEAL-YYYY-NNNNNN`, генерация по образцу request number); buyer_company_id FK
  companies; seller_company_id FK companies; request_id FK NULL; offer_id FK NULL;
  contract_id FK NULL (contracts.id); status deal_status default negotiation;
  amount Numeric(16,2) NULL; currency CHAR(3) default 'UZS';
  created_by_user_account_id FK; cancelled_reason Text NULL; created_at/updated_at.
  CHECK buyer≠seller. Индексы: (buyer_company_id, status), (seller_company_id, status).
- `deal_status_history`: id; deal_id FK CASCADE; from_status/to_status;
  actor_kind Text ('buyer'|'seller'|'staff'|'system'); actor_id BigInt NULL;
  reason Text NULL; created_at. Append-only.
- `deal_messages`: id; deal_id FK CASCADE; author_account_id FK user_accounts;
  body Text; file_storage_path Text NULL; file_name Text NULL; created_at.
  Append-only (без UPDATE/DELETE путей). Индекс (deal_id, id).
- `deal_documents`: id; deal_id FK CASCADE; kind deal_document_kind;
  file_name; mime_type; size_bytes; storage_path; sha256 CHAR(64);
  uploaded_by_user_account_id FK; revoked bool default false; revoked_reason Text NULL;
  created_at. Append-only + пометка revoked (не удаление).
- `rfq_responses`: id; request_id FK requests; company_id FK companies;
  created_by_user_account_id FK; price Numeric(14,2); currency CHAR(3);
  qty Numeric(14,3); qty_unit Text; incoterms (существующий PriceBasis enum) NULL;
  lead_time_days Int NULL; comment Text NULL; status rfq_response_status
  default submitted; deal_id FK NULL (заполняется при акцепте); created_at/updated_at.
  UQ (request_id, company_id) — один активный отклик компании на RFQ
  (withdrawn → повторный: partial unique index WHERE status != 'withdrawn').

События (extend event_types + DB-doc): `DEAL_OPENED, DEAL_STATUS_CHANGED,
DEAL_MESSAGE_POSTED, DEAL_DOCUMENT_ADDED, RFQ_RESPONSE_SUBMITTED,
RFQ_RESPONSE_ACCEPTED, RFQ_RESPONSE_NOT_SELECTED`.

### T1.2 `deal_service` (mypy strict)
- `VALID_TRANSITIONS` (данные, по образцу `request_service`):
  `negotiation → {contract_pending, cancelled}`;
  `contract_pending → {contract_signed(system), negotiation(откат при decline контракта), cancelled}`;
  `contract_signed → {payment_pending, cancelled?*}`;
  `payment_pending → {paid_escrow(system/P3), disputed, cancelled}`;
  `paid_escrow → {shipped, disputed}`;
  `shipped → {delivered, disputed}`;
  `delivered → {completed(system/P3 release), disputed}`;
  `disputed → {cancelled(staff), paid_escrow(staff), shipped(staff), delivered(staff)}`
  (staff-разрешение = возврат в предыдущий статус или отмена);
  терминальные: `completed, cancelled`.
  \* отмена после contract_signed — только двусторонняя или через disputed; правило:
  `cancel` одной стороной разрешён строго ДО `paid_escrow` (FR-D8), после — disputed.
- `open_deal_from_response(db, request, response, actor)` — обе компании verified
  (`CompanyNotVerified`), request принадлежит buyer-компании; response → accepted,
  остальные submitted-отклики этого request → not_selected (+ уведомления);
  amount/currency из response; событие DEAL_OPENED.
- `open_deal_from_inquiry(db, offer_request, actor)` — продавец открывает сделку из
  принятого inquiry (`OfferRequest`); buyer = компания inquiry (только если inquiry
  company-origin R2; telegram-origin без компании → `DealRequiresCompany`).
- `transition(db, deal, to_status, actor_kind, actor_id, reason=None)` — проверка по
  таблице (`InvalidDealTransition`), `SELECT … FOR UPDATE` на deal, history + audit +
  событие в одной транзакции. Права: `shipped` — только seller; `delivered` — только
  buyer; `cancelled` — любая сторона (до paid_escrow) с reason; `disputed` — любая
  сторона; из `disputed` — только staff. `contract_signed/paid_escrow/completed` —
  только `actor_kind='system'` (события contracts/P3, не руки).
- `post_message(db, deal, account, body, file=None)` — участник = активный member
  (owner/manager) buyer- или seller-компании (`NotDealParticipant`); файл через
  storage (≤10 МБ, jpeg/png/pdf/xlsx по существующему allow-list); событие.
- `add_document(db, deal, account, kind, file)` / `revoke_document(...)` (reason,
  audit; файл остаётся в S3 — только пометка).
- Обработчик события `CONTRACT_ACTIVATED` (R3): если contract.deal взаимосвязан
  (deal_id на контракте — см. T1.4) → `transition(contract_signed, system)`.
  Idempotent (deal уже в contract_signed → no-op). Аналогично `CONTRACT_DECLINED` →
  откат `contract_pending → negotiation`.

### T1.3 `rfq_response_service`
`submit(db, request, company, account, payload)` — company verified, request
в статусе, допускающем отклики (published/in_progress — сверить с фактическими
`RequestStatus`), не своя заявка (`CannotRespondOwnRequest`); UQ-конфликт →
`AlreadyResponded`. `withdraw` — автором до акцепта. `accept` → делегирует
`deal_service.open_deal_from_response`. Всё с audit + событиями.

### T1.35 Расширения RFQ (FR-D10, мокапы docs/new-design)
В миграцию 0023 добавить к `requests`: `required_docs JSONB NULL` (список кодов:
sds|coa|origin_cert|commercial_offer|other + note), `visibility Text default
'verified_only'` (enum `rfq_visibility`: verified_only|all|selected),
`visible_company_ids JSONB NULL` (для selected). `rfq_response_service.submit`
уважает visibility (selected/verified-гейт → `RfqNotVisible`); `GET /portal/market/requests`
фильтрует по видимости для компании-зрителя. Portal RFQ-визард: шаг «требуемые
документы» (чек-лист) + шаг «кто может видеть заявку»; required_docs показываются
поставщику в карточке RFQ и форме отклика. Канал получения предложений —
только внутри платформы (email/TG — вне скоупа, UI-переключатель не рисовать).

### T1.4 Связка с contracts (минимальное касание R3-кода)
Миграция добавляет `contracts.deal_id BigInt FK NULL` (nullable, без изменения
существующих флоу). `contract_service.create_contract` получает опциональный
`deal: Deal | None`: заполняет deal_id + предзаполняет variables (product, qty,
price, currency, incoterms из deal/response) + после `send` → deal
`negotiation → contract_pending` (system). Существующие contract-тесты не ломать.

**Acceptance Wave 1:** transition-таблица покрыта тестом-матрицей (все пары);
двойной акцепт двух откликов одного RFQ (гонка) → один Deal (UQ/FOR UPDATE тест);
права по ролям сторон; событийный переход contract_signed idempotent; отклик на
чужой/свой RFQ; verified-гейт; миграция up/down.

## Wave 2 — API

### T2.1 Portal — `backend/app/api/portal/deals.py`
- `GET /portal/companies/{id}/deals?role=buyer|seller&status=` — список (+counters).
- `GET /portal/companies/{id}/deals/{deal_id}` — карточка: статус, стороны (имя,
  logo_url, verified, роли-бейджи), request/offer/contract-ссылки, таймлайн (history),
  документы, escrow-блок (появится в P3 — сейчас поле `escrow: null`).
- `POST …/deals/{deal_id}/transition {to_status, reason?}` — человеческие переходы
  (shipped/delivered/cancel/dispute).
- Чат: `GET …/deals/{deal_id}/messages?after_id=` (инкрементально, limit 100) +
  `POST …/messages` (body или multipart с файлом). Опрос фронтом каждые 15 с
  (SSE — не в этом плане).
- Документы: `POST …/documents` (kind+файл), `GET …/documents/{doc_id}` → presigned
  (TTL ≤600 s), `POST …/documents/{doc_id}/revoke {reason}`.
- Отклики: `POST /portal/companies/{id}/requests/{request_id}/responses` (payload
  отклика — от лица компании-поставщика); `GET /portal/companies/{id}/requests/{request_id}/responses`
  (владелец RFQ видит все; поставщик — только свой); `POST …/responses/{rid}/accept`
  (владелец RFQ; создаёт Deal, возвращает его); `POST …/responses/{rid}/withdraw`.
- Открытые RFQ для поставщиков: `GET /portal/market/requests?product=&page=` —
  анонимизированный список опубликованных RFQ (без контактов; продукт/объём/
  инкотермс/срок/валидность) — источник для CTA «Откликнуться».

### T2.2 Admin — `backend/app/api/admin_deals.py`
`GET /admin/deals?status=&q=&company_id=` + detail (таймлайн, документы-метаданные,
чат read-only с пагинацией). `POST /admin/deals/{id}/resolve-dispute
{action: cancel|restore, restore_to?, comment}` — только `require_admin`; audit.

**Acceptance Wave 2:** authz-матрица (buyer-член / seller-член / третья компания 404 /
staff / viewer-роль члена — read-only); чат: не-участник 404, staff GET ok POST 403;
инкрементальный `after_id`; presigned TTL; отклики видимость (поставщик не видит чужие).

## Wave 3 — Уведомления

### T3.1 Portal-notifications (R2 bell) + Telegram staff
На события: новый отклик (владельцу RFQ), акцепт/not_selected (поставщикам),
DEAL_OPENED (обеим), смена статуса сделки (контрагенту), новое сообщение чата
(контрагенту, с дедупом: не чаще 1 уведомления в 10 мин на сделку), новый документ.
Telegram: карточка в staff-группу на DEAL_OPENED и disputed (read-only, шаблоны
ru/uz/tr) — задачи в `tasks/notify.py`, очередь `notify`, fail-soft.

**Acceptance:** уведомления создаются в тех же транзакциях/тасках, что события;
дедуп чата покрыт тестом.

## Wave 4 — Frontend

### T4.1 Portal
- `pages/deals` — список (табы: все / требуют действия / активные / завершённые;
  чипы статусов; роль-фильтр покупка/продажа).
- `pages/deals/[id]` — Trade Room: шапка (стороны + статус-степпер по машине),
  вкладки: **Чат** (поллинг 15 с, отправка текст+файл), **Документы** (список по kind,
  загрузка, revoked-стиль), **Таймлайн** (history), **Контракт** (ссылка/CTA «Создать
  договор» → существующий contracts-флоу с предзаполнением), Escrow-вкладка — заглушка
  «после P3». Action-bar по статусу и роли (отгружено/получено/отменить/спор).
- RFQ: на странице своей заявки — блок откликов (список, акцепт с подтверждением
  «остальные будут отклонены»); `pages/market/requests` — список открытых RFQ +
  форма отклика (для компаний с seller-ролями).
- zustand-store не требуется — TanStack Query с поллингом; i18n ru/uz/en.

### T4.2 Dashboard
`(dashboard)/deals/` — таблица (фильтры), карточка: таймлайн, документы, чат
read-only, кнопка разрешения спора (только admin). Nav-пункт + локали (5 языков).

**Acceptance Wave 4:** e2e полный demo-сценарий (без escrow-части) на стабах;
lint/typecheck оба фронта; ре-использование contracts-флоу не ломает его e2e.

---

## Интерфейс к соседним доменам (не реализовывать здесь)
- **P3 (payments)** добавит: `escrow_payments.deal_id`, перевод
  `contract_signed → payment_pending` (создание EscrowPayment) и system-переходы
  `payment_pending → paid_escrow`, `delivered → completed`. В этом плане Deal просто
  останавливается на `contract_signed`; ручной transition в `payment_pending`
  разрешить как временный (staff/system) — P3 его переключит на автоматический.
- **P4 (matching)** вызовет `rfq_response`-флоу через push-уведомления — API готово здесь.
- **P6 (lab)** будет писать `deal_documents(kind=lab_passport)` — kind уже есть.

## Progress
- [ ] T1.1 … T4.2
