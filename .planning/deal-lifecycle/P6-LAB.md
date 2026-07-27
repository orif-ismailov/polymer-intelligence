# P6 — Lab: лабораторные паспорта, заказ анализа, образцы (R5 — скелет)

> Статус: **скелет — детализировать после приёмки R4**. Prereq: `00-CONTEXT.md`,
> P2 (лаб-док в сделке), желательно P5 (вещество в заявке). ТЗ: блок C, FR-L1–L5.
> **Методология: строгий TDD** (тест до кода per task; полный `pytest tests/ -q` +
> фронт-гейты перед каждым коммитом) — детализация плана обязана разложить работы на
> задачи с тестами. Статусные машины lab_order/sample_request — тест-матрицы до реализации.

**Demo (цель):** продавец загружает лаб-паспорт → бейдж на оффере + фильтр в маркете;
продавец без паспорта жмёт «Заказать анализ» → оператор ведёт заявку вручную →
паспорт загружен → бейдж «Laboratory Verified»; покупатель запрашивает образец →
`requested → accepted → sent (курьер+трек) → received`; уведомления всем сторонам.

## Контур работ (waves при детализации)

1. **Схема** — миграция `0027_lab`: `lab_partners` (name, contacts JSONB, is_active);
   `lab_orders` (company_id; offer_id NULL / deal_id NULL — CHECK хотя бы один;
   substance_id NULL; sample_volume Text; comment; status enum `lab_order_status`:
   submitted|accepted|sample_awaited|in_analysis|done|rejected; lab_partner_id NULL;
   result_document_path NULL; operator_note; timestamps);
   `sample_requests` (offer_id; buyer_company_id; status enum `sample_request_status`:
   requested|accepted|declined|sent|received|rejected_by_buyer; qty Text NULL;
   courier Text NULL; tracking_ref Text NULL; delivery_address Text;
   decline_reason NULL; timestamps). ALTER seller_offers: samples_available bool
   default false, sample_price Numeric NULL, sample_dispatch_days Int NULL;
   lab_verified bool default false (ставится только системой при done через платформу).
   Тип файла `lab_passport` — расширение `OfferFileKind` (enum-миграция).
2. **Сервисы** — `lab_service` (переходы — данные; статусы двигает staff в dashboard;
   `done` требует загрузку паспорта → прикрепление к офферу
   (`SellerOfferFile kind=lab_passport`) или сделке (`deal_documents kind=lab_passport`)
   + `lab_verified=true` для платформенного заказа); `sample_service` (гейт
   `samples_available`; переходы по ролям: продавец accept/decline/sent,
   покупатель received/rejected_by_buyer).
3. **API** — portal: загрузка паспорта (kind=lab_passport в существующий files-эндпоинт
   + валидация PDF), CRUD lab-order (создание+свой список), sample-request
   (создание покупателем, действия сторон); dashboard: очередь lab-orders
   (оператор), справочник лабораторий (admin).
4. **Frontend** — portal: блок «Лабораторный паспорт» в offer-form (загрузить ИЛИ
   кнопка «Заказать анализ через IMEX» с текстом «мы свяжемся и согласуем»);
   бейджи «Лаб. паспорт» / «Laboratory Verified» на карточках; фильтр маркета;
   секция образцов на странице оффера и в Trade Room. Dashboard: страницы
   lab-orders + lab-partners. Локали все.
5. **Уведомления** — стороны sample-request; оператор (staff Telegram) о новом
   lab-order; продавец о done.
6. **P4-хук** — включить член скоринга «лаб-паспорт» (+0.15).

## Интерфейс к соседним доменам
- Использует существующий files-механизм P1 и `deal_documents` P2 — без новых
  файловых подсистем.
- Кэшбэк-учёт с лабораторией — вне скоупа (журнал lab_orders достаточен).

## Progress
- [ ] детализация плана (после R4) → задачи T1.x…
