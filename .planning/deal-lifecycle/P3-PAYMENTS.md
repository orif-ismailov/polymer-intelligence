# P3 — Payments: EscrowPayment (stub-first) + контур банковского адаптера

> Prereq: `00-CONTEXT.md`, P2 (deals) реализован. ТЗ: FR-P1/P2; факты — `INTEGRATIONS.md` §2.
> Банковское API гарантировано (гос-проект), сроки неизвестны → статусная машина и
> операторский stub — постоянная часть системы, live-адаптер подключится в P7.
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> тест зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> Особо: тест «funded двигает Deal в той же транзакции» и гонка двойного mark —
> пишутся ДО реализации `escrow_service.mark`.

**Demo (Definition of Done):** Deal в `contract_signed` → система создаёт EscrowPayment
(`pending`) и Deal → `payment_pending`; обе стороны видят реквизиты/статус оплаты в
Trade Room; оператор в dashboard отмечает «средства поступили» (двойное подтверждение)
→ EscrowPayment `funded` → Deal `paid_escrow` автоматически; после `delivered` оператор
отмечает «средства выплачены продавцу» → `released` → Deal `completed`; возврат
(`refunded`) из спора → Deal `cancelled`. Прямой перевод Deal в эти статусы руками —
невозможен. Переключение `escrow_mode` — runtime.

---

## Wave 1 — Схема и домен

### T1.1 Миграция `0024_escrow`
- Enum `escrow_status`: `pending, funded, released, refunded`.
- `escrow_payments` (`app/models/payments.py`): id; deal_id FK UQ (одна запись на
  сделку); amount Numeric(16,2); currency CHAR(3); status escrow_status default
  pending; mode Text ('stub'|'live') — зафиксированный на момент создания;
  provider_ref Text NULL (идентификатор операции банка, live); funded_at/released_at/
  refunded_at TIMESTAMPTZ NULL; funded_marked_by/released_marked_by/refunded_marked_by
  BigInt NULL (staff id, stub-режим); note Text NULL; created_at/updated_at.
  **Никаких банковских реквизитов счетов в БД.**
- `provider_events` (webhook-inbox, готовим заранее — используется и P7):
  id; provider Text; external_id Text; payload JSONB; processed bool default false;
  processed_at NULL; error Text NULL; created_at. UQ (provider, external_id).
- События: `ESCROW_OPENED, ESCROW_FUNDED, ESCROW_RELEASED, ESCROW_REFUNDED`.
- DB-doc в том же коммите.

### T1.2 `escrow_service` (mypy strict)
- `_TRANSITIONS`: `pending → {funded, refunded}`; `funded → {released, refunded}`;
  терминальные `released, refunded`.
- `open_for_deal(db, deal)` — вызывается обработчиком события `DEAL_STATUS_CHANGED
  (to=contract_signed)`: amount/currency из deal (нет суммы → `DealAmountMissing`,
  deal остаётся в contract_signed с задачей-алертом staff); создаёт EscrowPayment
  (mode = текущая настройка) + `deal_service.transition(payment_pending, system)`.
  Idempotent (существует → no-op).
- `mark(db, payment, to_status, staff_user, note)` — stub-режим: проверка перехода,
  `SELECT … FOR UPDATE`, простановка *_at/*_marked_by, audit (обязательный note),
  событие; связанный Deal-переход **в той же транзакции**:
  funded → `paid_escrow`; released → `completed` (только если Deal в `delivered`,
  иначе `EscrowReleaseBeforeDelivery`); refunded → `cancelled` (reason='escrow_refund').
- `apply_provider_event(db, event)` — live-путь (P7): парсинг провайдер-события →
  тот же `mark`-механизм с actor system. Здесь — только скелет + тест на идемпотентность
  по `provider_events` UQ.
- Убрать временное правило P2: ручной transition `contract_signed → payment_pending`
  запретить (только system).

### T1.3 Адаптер-контур — `backend/app/integrations/escrow/`
`client.py` по образцу eimzo: протокол `EscrowClient` (`open_escrow`, `get_status`,
`request_release`, `request_refund`) + `StubEscrowClient` (no-op, возвращает
локальные данные) + фабрика `get_escrow_client()` по настройке `escrow_mode`
(`_SPECS`: `escrow_mode: stub|live`, default `stub`). Live-реализации нет (P7) —
`ProviderUnavailable` при выборе live без конфигурации.

**Acceptance Wave 1:** transition-матрица; open idempotent; funded двигает Deal в той же
транзакции (тест с откатом: ошибка Deal-перехода откатывает mark); release до delivered
запрещён; refund из funded → deal cancelled; UQ deal_id; гонка двух параллельных mark →
одна применяется (FOR UPDATE тест); provider_events идемпотентность; миграция up/down.

## Wave 2 — API + операторский stub

### T2.1 Portal (обе стороны сделки)
Расширить deal-detail payload (P2 API): блок `escrow: {status, amount, currency,
funded_at, released_at}` + человекочитаемые подписи статусов. Отдельных мутаций у
клиентов нет (двигает банк/оператор).

### T2.2 Dashboard admin — `backend/app/api/admin_escrow.py`
- `GET /admin/escrow?status=` — очередь платежей (join deal + компании).
- `POST /admin/escrow/{id}/mark {to_status, note}` — `require_admin`; UI с двойным
  подтверждением (чекбокс «я подтверждаю фактическое движение средств в банке» +
  обязательный комментарий). 409 на недопустимый переход.

### T2.3 Frontend
- Dashboard: страница `/escrow` (очередь: ожидают подтверждения оплаты / ожидают
  выплаты) + панель escrow в карточке сделки с кнопками mark; локали ×5.
- Portal: Escrow-вкладка Trade Room — статус-степпер оплаты, суммы, даты; баннер
  «оплата производится по счёту через банк-партнёр» (текст — i18n, финальную
  формулировку даст оператор). i18n ru/uz/en.

### T2.4 Уведомления
Обеим сторонам при `ESCROW_OPENED/FUNDED/RELEASED/REFUNDED` (portal bell);
staff-группа Telegram при `FUNDED` (шаблоны ru/uz/tr, fail-soft).

**Acceptance Wave 2:** authz (admin-only mark; analyst read-only); e2e: полный
Deal-демо теперь проходит до `completed` через операторские отметки; portal
отображает статусы; RBAC-тест на portal (нет мутаций).

---

## Интерфейс к соседним доменам (не реализовывать здесь)
- **P2**: использует `deal_service.transition` c actor system — контракт уже в P2.
- **P7 (live)**: реализует `LiveEscrowClient` + webhook-роут, пишущий в
  `provider_events`, + Celery-обработчик → `apply_provider_event`. Схема и сервис
  готовы здесь — P7 не трогает модели.

## Progress

Реализовано полностью (миграция — **0024**, как и планировалось).

- [x] **T1.1** — enum `escrow_status`, `app/models/payments.py` (`EscrowPayment`,
  `ProviderEvent`), миграция `0024_escrow`, события `ESCROW_*`, DB-doc v1.8 — `472ab93`
- [x] **T1.3** — `app/integrations/escrow/client.py` + runtime-настройка `escrow_mode` — `4c09500`
- [x] **T1.2** — `escrow_service` (`_TRANSITIONS`, `open_for_deal`, `mark`,
  `record_provider_event`/`apply_provider_event`) + снятие временного правила P2 — `a5c8479`
- [x] **T1.4** — consumer `DEAL_STATUS_CHANGED (to=contract_signed)` → `open_for_deal` — `190a395`
- [x] **T2.1 + T2.2** — блок `escrow` в portal-payload сделки + `app/api/admin_escrow.py` — `dc28019`
- [x] **T2.4** — уведомления (колокольчик обеим сторонам + Telegram-карточка на FUNDED) — `5469b8f`
- [x] **T2.3** — dashboard `/escrow` + вкладка «Оплата» в Trade Room, локали ×5 / ×3 — `fbbdeb9`
- [x] Правки после живой браузерной проверки — `044c94d`

### Отклонения от плана (и почему)

1. **T1.3 сделан ДО T1.2.** `EscrowPayment` фиксирует `mode` в момент создания, значит
   рельса должна существовать раньше, чем сервис сможет открыть платёж. Нумерация плана
   не менялась.
2. **`SettingSpec` получил поле `choices`.** Переключатель режима — закрытое множество;
   опечатка в админке должна падать при записи, а не всплывать позже недоступным
   runtime-значением. Dashboard рисует `<select>` при наличии `choices` и обычный input
   иначе — есть тест, что существующие строковые настройки не задеты.
3. **`mark` требует staff-пользователя.** План допускал actor `system` для live-пути, но
   `cancelled` в машине сделок недостижим для `system`, а расширять правило под ещё не
   существующий путь — спекуляция. `apply_provider_event` — скелет, в докстроке зафиксирован
   вопрос, который решает P7 (сервисный staff-аккаунт или расширение `_ACTOR_RULES`).
4. **Возврат из `funded` требует спора.** План говорил «refunded → Deal cancelled»; в машине
   P2 `paid_escrow → cancelled` не существует (FR-D8). Это не обход, а сознательный отказ:
   возврат живых денег становится зафиксированным решением staff, а не тихим откатом.
   Есть тест на обе половины (отказ без спора + успех после спора).
5. **`API` требует `confirmed: true`.** План описывал двойное подтверждение как UI-элемент;
   чекбокс, который проверяет только фронт, — не подтверждение.
6. **`GET /admin/escrow` возвращает ещё и `blocked`** — подписанные сделки без суммы.
   Consumer их только логирует (иначе диспетчер ретраил бы вечно), и без этого списка они
   висели бы в `contract_signed` невидимыми.
7. **Правка чужого домена:** степпер сделки в портале при `cancelled` показывал нулевой
   прогресс. Баг родом из P2, но именно возврат средств делает отменённые сделки частыми;
   исправлено здесь (`044c94d`).

### Живая проверка (браузер, Playwright MCP)

Полный сценарий из Definition of Done пройден на живом стеке: договор подписан → consumer
сам создал `EscrowPayment(pending)` и перевёл сделку в `payment_pending` → оператор отметил
«средства поступили» (комментарий + чекбокс обязательны) → сделка `paid_escrow` → досрочная
выплата **отклонена** с внятной причиной → продавец отгрузил, покупатель принял → выплата →
сделка `completed`. На второй сделке: спор → возврат → сделка `cancelled`. Третья сделка (без
суммы) попала в список «Сделки без счёта». Колокольчики обеих сторон получили оба события.

Пять дефектов, которые нашёл только экран, исправлены в `044c94d` (см. коммит).

### Осознанные пробелы

- **Нет e2e-спеки на escrow.** Как и для P1/P2: в репозитории нет пути к *верифицированной*
  компании из e2e, а построить его — отдельная инфраструктурная работа крупнее самой фичи.
  Покрытие даёт связка «guarded real-DB тесты + живая браузерная проверка».
- **Live-рельса не реализована** (это P7 по плану). Выбор `escrow_mode=live` осознанно
  падает с `ProviderUnavailable`, а не молча возвращает stub.
- **`provider_events` пока только заполняется** — маршрут webhook и разбор payload в P7.
