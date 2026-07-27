# P4 — Matching: AI-push поставщикам по RFQ, бейджи ролей, доработки формы оффера

> Prereq: `00-CONTEXT.md`, P2 (нужны отклики на RFQ — CTA «Откликнуться»). ТЗ: блок E,
> FR-A1/A2. Существующее: `request_analysis_service` (AI-анализ RFQ),
> `company_business_roles` (роли уже в БД), `portal_notifications` (R2 bell).
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> тест зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> Табличный тест скоринга (роли меняют порядок) пишется ДО `supplier_matching_service`.
> LLM в тестах не вызывается — мокать по образцу `parsing.extractor._client`.

**Demo (Definition of Done):** при `rfq_supplier_push_enabled=on` публикация RFQ
рассылает top-10 подходящим компаниям-поставщикам уведомление «Новый запрос по вашему
профилю» со ссылкой на RFQ и кнопкой «Откликнуться»; производитель ранжируется выше
трейдера; повторная публикация того же RFQ не дублирует push; на карточках маркета и
в каталоге контрагентов видны бейджи бизнес-ролей; оффер «под заказ» требует срок
производства и показывает «Цена по запросу».

---

## Wave 1 — Доработки формы оффера (малый, независимый)

### T1.1 Миграция `0025_offer_sale_fields`
`ALTER TABLE seller_offers ADD COLUMN lead_time_days INT NULL,
ADD COLUMN sale_mode TEXT NULL` (enum `offer_sale_mode`: `from_stock, made_to_order,
recurring_contract`), **флаги готовности к сделке** (мокапы new-design):
`accepts_rfq BOOL default true, accepts_contract BOOL default false,
accepts_escrow BOOL default false`. Плюс избранное: таблица `offer_favorites`
(user_account_id FK, offer_id FK, created_at; UQ пара). DB-doc.

### T1.2 Backend + Portal
Валидация в offer-сервисе/схемах: `availability=on_order` ⇒ `lead_time_days`
обязателен, price допустимо NULL (UI показывает «Цена по запросу»); `in_stock` ⇒
price обязателен (сверить с текущим поведением — не ужесточать задним числом для
существующих строк, только для новых/редактируемых). Portal `offer-form`: переключатель
уже существующего `availability` дополняется полями срок производства + способ продажи
+ блок «Готовность к сделке» (3 чекбокса → бейджи на карточке маркета: RFQ / Договор /
Escrow). Избранное: сердечко на карточках маркета + `POST/DELETE
/portal/market/offers/{id}/favorite` + страница «Избранное» в кабинете.
Карточки маркета: «Цена по запросу» вместо пустой цены. i18n ru/uz/en.

**Acceptance:** unit-валидации, e2e публикация on_order-оффера без цены; существующие
оффер-тесты зелёные.

## Wave 2 — Бейджи бизнес-ролей

### T2.1 Payload + UI
В market/company payload'ы добавить `business_roles: []` (уже подтверждённые —
`BusinessRoleStatus` confirmed; сверить фактическое поле статуса в
`app/models/companies.py`). Portal: бейдж роли на карточке оффера (маркет, страница
оффера) и в каталоге контрагентов; словарь подписей/иконок: manufacturer 🏭,
distributor ✅, importer/supplier 📦, trader 🌍, laboratory 🧪. Dashboard: колонка
ролей в списке компаний (если ещё нет). Локали.

**Acceptance:** роли отображаются из фикстур; нет N+1 (joinedload).

## Wave 3 — AI supplier push

### T3.1 Миграция `0025b` (или в составе 0025) `rfq_push_log`
id; request_id FK; company_id FK; score Numeric(5,2); rank Int; notified_at;
UQ (request_id, company_id) — защита от дублей (FR-A2).

### T3.2 `supplier_matching_service` (mypy strict)
`match_suppliers(db, request) -> list[ScoredCompany]`:
кандидаты = verified-компании с активными/недавними (настройка, default 90 дней)
офферами, совпадающими по product_id ИЛИ polymer_type ИЛИ текстовому совпадению
продукта (существующая логика подбора в `request_analysis_service` — переиспользовать
её матчер, не дублировать; если там только LLM-анализ без структурного подбора —
строим SQL-подбор здесь и НЕ вызываем LLM).
Скоринг (веса — константы модуля): совпадение продукта (точное 1.0 / тип 0.6 /
текст 0.4) + verified (+0.2) + лаб-паспорт на оффере (+0.15, появится в P6 — до того
член суммы = 0) + свежесть оффера (+0.1) ; множитель приоритета роли:
manufacturer 1.3 / distributor 1.2 / importer|supplier 1.1 / trader 1.0.
Исключить компанию-автора RFQ.

### T3.3 Celery-задача + подписка на событие
Задача `notify_matched_suppliers(request_id)` (модуль в `_TASK_MODULES`, очередь
`notify`): гейт `rfq_supplier_push_enabled` (default off) → match → top-N (настройка
`rfq_supplier_push_top_n`, default 10) → для каждого: INSERT в `rfq_push_log`
(`ON CONFLICT DO NOTHING`; конфликт = уже слали, пропустить) → portal-notification
(«Новый запрос по вашему профилю: {product}, {volume}» + deeplink на
`pages/market/requests/{id}` с CTA «Откликнуться»). Триггер: существующая точка
публикации RFQ (сверить, где request переходит в published/submitted —
`request_service`) enqueue fail-soft. Никаких Telegram-DM поставщикам в этом плане.

### T3.4 Настройки + dashboard-наблюдаемость
`_SPECS`: `rfq_supplier_push_enabled` (bool, off), `rfq_supplier_push_top_n` (int, 10).
В dashboard-карточке заявки — блок «Уведомлённые поставщики» (из rfq_push_log,
score/rank/время; read-only).

**Acceptance Wave 3:** скоринг — табличный unit-тест (роли меняют порядок); дедуп по
UQ (повторный вызов задачи — 0 новых уведомлений); гейт off = задача no-op; уведомление
содержит рабочий deeplink; полный suite.

---

## Интерфейс к соседним доменам (не реализовывать здесь)
- CTA «Откликнуться» ведёт на API/страницы откликов из **P2** — только ссылка.
- Член скоринга «лаб-паспорт» активируется данными **P6** — здесь оставить 0 с TODO-констант.
- Поля формы оффера по образцам/веществам — **P5/P6**, не добавлять.

## Progress
- [ ] T1.1 … T3.4
