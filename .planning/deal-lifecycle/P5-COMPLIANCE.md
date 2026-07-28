# P5 — Compliance: справочник веществ, ТН ВЭД/CAS, гейт публикации (R5)

> Prereq: `00-CONTEXT.md`, P1 (форма оффера), P4 (портальная схема оффера —
> `CompanyOfferIn`/`PortalMarketOfferOut`). ТЗ: блок B, FR-C1–C6; правовая карта —
> `INTEGRATIONS.md` §4.
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> тест зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> **Табличный тест вердиктов `offer_compliance_service` пишется ДО реализации.**
> LLM в тестах не вызывается — мокать по образцу `parsing.extractor._client`.

**Demo (Definition of Done):** оффер «Метанол» при `dangerous_check_enforced=on` не
публикуется без активной лицензии нужного **режима**; после регистрации лицензии —
публикуется; оффер «PP H030» публикуется свободно; вещество из перечня ПКМ-916
(`prohibited`) не публикуется никогда и никакая загрузка документов этого не меняет;
AI предлагает вещество-кандидата по тексту оффера, продавец подтверждает или
отклоняет (подсказка журналируется); модерация видит комплаенс-статус оффера.

**Нумерация миграции: `0027`** — план-скелет говорил «0026_substances», но 0026 занят
`rfq_push_log` (P4 W3). Правило 3 из `00-CONTEXT`: прав код.

---

## Wave 1 — Схема

### T1.1 Миграция `0027_compliance` + модели
Один контекст — одна миграция (сид W2 и вердикт W3 стоят на ней целиком).

Enum-ы (`(str, Enum)` в `enums.py`, PG-типы создаются в миграции):
- `regulation_level`: `free | docs_required | license_required | prohibited`
- `regulation_regime`: `precursor_list_iv | explosive_toxic | strong_acting | pkm916_import`
- `license_status`: `pending_review | active | expired | revoked | rejected`
  (машина из `company-verification/ARCHITECTURE.md` §CompanyLicense)
- `offer_file_kind += sds, coa` (`ALTER TYPE … ADD VALUE` в `autocommit_block`, образец
  `0020_eimzo`): перечень обязательных документов вещества — SDS/TDS/COA, а в
  существующем enum есть только `tds`; без этих значений проверка `docs_required`
  проверять нечего.

Таблицы (модуль `app/models/compliance.py` — контекст `catalog/compliance` из
`00-CONTEXT`; скелет называл файл `substances.py`, но модуль владеет тремя таблицами
контекста, а не одной):
- `substances`: `code` UQ (slug — натуральный ключ идемпотентного сида),
  `name_ru/uz/en`, `hs_code` (первичный юр-идентификатор, индекс), `cas` UQ NULL,
  `hazard_class` NULL, `regulation_level` NOT NULL, `regulation_regime` NULL,
  `threshold_concentration_pct` Numeric(5,2) NULL, `exemption_annual_limit`
  Numeric(12,3) NULL + `exemption_unit` NULL, `license_category` NULL,
  `required_docs` JSONB (список кодов), `synonyms` JSONB, `source_act`,
  `seed_revision` NULL, `is_active`, timestamps.
- `company_licenses`: `company_id` FK CASCADE, `regime` NOT NULL, `category` NULL,
  `license_number` NULL, `issued_by` NULL, `issued_at`/`expires_at` DATE NULL,
  `status` NOT NULL, `document_id` FK `verification_documents` SET NULL (доказательство
  из R1-потока загрузки документов), `registered_by` FK `staff_users` NULL,
  `revoked_at`/`revoke_reason` NULL, timestamps; индекс (company_id, regime, status).
- `substance_suggestions` (журнал FR-C3): `offer_id` FK NULL CASCADE, `company_id` FK NULL,
  `input_text`, `substance_id` FK NULL, `suggested_cas`/`suggested_hs_code`/
  `suggested_name` NULL, `confidence` Numeric(3,2) NULL, `model`, `prompt_version`,
  `tokens_in`/`tokens_out`, `accepted` BOOL NULL (NULL = решения ещё нет),
  `decided_at`/`decided_by_user_account_id` NULL, `created_at`.
- ALTER `seller_offers`: `substance_id` FK NULL, `cas_number` NULL, `hs_code` NULL,
  `declared_concentration_pct` Numeric(5,2) NULL + **кеш вердикта** (FR-C6):
  `compliance_level` NULL, `compliance_ok` BOOL NULL, `compliance_missing` JSONB NULL,
  `compliance_checked_at` NULL.

**Acceptance:** `test_migration_0027` (up → down → up на эфемерном Postgres, наличие
типов/таблиц/колонок/UQ), `alembic check` без дрейфа, DB-doc **v1.11** в том же коммите,
одноголовость (`alembic heads` == 0027) в существующих `test_migration_00XX`.

## Wave 2 — Справочник веществ

### T2.1 `seed_substances` + `app/seed/data/substances_v1.json`
Идемпотентный (ON CONFLICT по `code`), версионируемый: `revision` в JSON пишется в
`substances.seed_revision`; правка перечня = новый файл `substances_v{N+1}.json`.
Наполнение v1 — только то, что подтверждено `INTEGRATIONS.md` §4 и ТЗ:
полимеры PP/PE/PVC/PET/PS (`free`), отходы пластмасс ТН ВЭД 3915 (`pkm916_import`),
позиции Списка IV ПКМ-330 с порогами, названные в правовой карте (ацетон ≥60%,
толуол ≥70%, МЭК ≥80%, соляная ≥15%, серная ≥45%, перманганат ≥45%, ангидрид уксусной —
без порога; изъятие ≤12 кг/год), метанол (демо-сценарий ТЗ).
**Полную оцифровку 29 позиций Списка IV / ПКМ-818 / ПКМ-782 / ПКМ-916 в код НЕ
вписываем** — редакции приложений не проверяемы из этой сессии, а юр-сверка на lex.uz
объявлена операторской задачей (`INTEGRATIONS.md` §4, prerequisite 1). Поэтому: сид
помечен `revision: v1`, каждая строка несёт `source_act`, в докстринге сидера — WARNING
по образцу `seed_contract_templates` («перечень неполон, требует юр-сверки, дополняется
ревизией сида/админкой»), в `admin-guide-ru` — раздел, что делать после сверки.

### T2.2 `substance_service` (mypy strict)
`search(db, q, *, limit)` — по `code`/`name_ru|uz|en`/`synonyms` JSONB/`cas`/`hs_code`;
`get`, `create`, `update`, `set_active`; `resolve(db, *, cas=None, hs_code=None, name=None)`
для AI-подсказки и ручного ввода. Аудит на write-путях.

### T2.3 Admin CRUD `/admin/substances` (FR-C1)
GET (q + фильтр по уровню, для analyst+), POST/PATCH/DELETE→deactivate (admin only).
Типизированные ошибки на дубль `code`/`cas`.

### T2.4 Portal-поиск `GET /portal/substances?q=`
Для пикера в форме оффера: authed account, лёгкая проекция (id, name, cas, hs_code,
regulation_level), лимит.

### T2.5 `integrations/chem_registry/` — тонкий stub
`lookup_substance(hs_code|name)` + `ChemRegistryUnavailable` + фабрика по образцу
`get_escrow_client()`, режим `chem_registry_mode` (`stub` по умолчанию). Машиночитаемого
гос-реестра не существует (`INTEGRATIONS.md` §4) — источник истины наш справочник;
интерфейс закладывается, чтобы P7 подключил live без правки вердикт-сервиса.

**Acceptance:** сид дважды → 0 новых строк; поиск находит по синониму и по CAS;
RBAC (analyst read / admin write); портальный поиск требует аккаунт; `live`-режим
без адаптера → `ChemRegistryUnavailable`, вердикт при этом не ломается.

## Wave 3 — Вердикт и гейт публикации

### T3.1 `offer_compliance_service` (mypy strict) — табличный тест ДО кода
`evaluate(db, offer) -> ComplianceVerdict(level, ok, missing: list[Missing], substance_id,
regime, exempt_reason)`. Правила:
- вещество не указано и не резолвится по CAS/HS → `free`, ok (о неизвестном не судим);
- `free` → ok;
- `docs_required` → нужны файлы оффера видов из `substance.required_docs`;
- `license_required` → нужна **активная** `company_licenses` строка совпадающего
  `regime`; если у вещества задана `license_category` — категория должна совпасть;
- `prohibited` → всегда not-ok, и **никакая загрузка документов/лицензий этого не
  снимает**;
- концентрация: `declared_concentration_pct` < `threshold_concentration_pct` →
  режим не применяется (`exempt_reason="below_threshold"`); концентрация не заявлена →
  считаем регулируемым (консервативно).

### T3.2 Лицензии компании
`company_license_service` (mypy strict): `register` (из принятого документа R1 или
вручную staff), `revoke`, `list_for`, `active_for(db, company_id, regime, category)`;
`active` = `status=active AND (expires_at IS NULL OR expires_at >= today) AND revoked_at
IS NULL` — истечение вычисляется на чтении, не «протухает» в БД.
API: `/admin/companies/{company_id}/licenses` (GET/POST/POST revoke, analyst read /
admin write, аудит) + `GET /portal/companies/{cid}/licenses` (read-only, свои).

### T3.3 Гейт публикации + кеш вердикта (FR-C4, FR-C6)
- `evaluate_and_stamp(db, offer)` пишет кеш-поля; вызывается на создании и **каждом**
  редактировании/переопубликации оффера (в т.ч. когда настройка off — вердикт
  информационный, блокирует только настройка).
- Гейт: `dangerous_check_enforced` (bool, off) в `_SPECS`. При on — `CompliancePublishBlocked`
  из `create_company_offer`/`update_company_offer` → **409** с телом
  `{code, level, missing:[…]}` (CTA на фронте); и повторная проверка в
  `moderate_offer(approve=True)` — лицензия могла истечь между подачей и одобрением;
  staff получает 409 с причиной, а не публикует просроченное.
- **Точка гейта — не `offer_service.publish`**: такой функции нет, публикация = подача
  (портал) + одобрение (модерация). Обе точки закрыты.

### T3.4 Комплаенс-статус для модерации и портала (FR-C5)
Блок `compliance` в `ModerationOfferOut` (вещество, уровень, режим, чего не хватает) +
`GET /portal/companies/{cid}/offers/{oid}/compliance` для экрана требований.

**Acceptance:** табличный тест вердиктов (все 4 уровня × наличие/отсутствие лицензии ×
порог концентрации); гейт off = публикуется всё; гейт on = блок с типизированным телом;
после регистрации лицензии — публикуется; `prohibited` не публикуется никогда;
истёкшая лицензия ⇒ модерация не одобряет; кеш пересчитывается на редактировании.

## Wave 4 — AI-подсказка вещества (FR-C3)

### T4.1 `substance_match_v1` + `substance_ai_service`
Новая prompt-семья `parsing/prompts/substance_match_v1.md` (immutable, версия — константа
модуля), схема результата в `app/schemas/substance_match.py`, сервис по образцу
`request_analysis_service`: instructor+Anthropic `Mode.TOOLS`, temperature 0,
prompt-кеш, **бюджет-гейт** `parsing.budget` (на исчерпании — тихий None, не падение),
журнал в `substance_suggestions` (модель, версия промпта, токены). Кандидат резолвится в
`substances` по CAS → HS → имени/синониму; ничего не пишется в оффер автоматически.

### T4.2 Endpoints + настройка
`POST /portal/substances/suggest {text, offer_id?}` → подсказка (или 200 с `null`, если
бюджет/выключено); `POST /portal/substances/suggestions/{id}/decision {accepted}` —
подтверждение продавцом (журналируется, `accepted`/`decided_at`).
Настройка `substance_ai_enabled` (bool, **on** — стоимость уже ограничена дневным
бюджетом токенов; выключатель нужен как kill switch).

**Acceptance:** `_client` пропатчен, сети нет; бюджет исчерпан → None + запись не
создаётся; подсказка не меняет оффер без `decision`; неизвестное вещество → `substance_id`
NULL, но строка журнала есть.

## Wave 5 — Фронтенды

### T5.1 Portal (ru/uz/en)
Блок «Вещество» в `offer-form`: поиск по справочнику (debounce), кнопка «Определить
по описанию» (AI-подсказка + подтверждение/отклонение), поле концентрации, ручной
ввод CAS/HS для веществ вне справочника. Панель требований на карточке своего оффера
(«для публикации нужны: …») + понятная ошибка при 409 с CTA (загрузить документ /
лицензию). Read-only блок «Лицензии» в профиле компании. Только примитивы `shared/ui`
и токены P0.

### T5.2 Dashboard (ru/uz/tr/fa/zh)
Страница `/substances` — список с фильтром по уровню + создание/правка/деактивация.
Комплаенс-панель в карточке модерации (вещество, уровень, чего не хватает).
Блок лицензий в карточке компании (регистрация из принятого документа + отзыв).
`dangerous_check_enforced` появляется в админ-настройках автоматически.

**Acceptance:** lint+typecheck обоих фронтов; ключи локалей полны; живая браузерная
проверка демо-сценария (Playwright MCP) — блок публикации, регистрация лицензии,
разблокировка, AI-подсказка, комплаенс в модерации.

## Wave 6 — Документация

### T6.1 DB-doc, CLAUDE-дельты, RU-админгайд, Progress
DB-doc v1.11 (таблицы + ALTER), `backend/CLAUDE.md` (новый контекст, prompt-семья,
настройки), `portal/CLAUDE.md`/`dashboard/CLAUDE.md` (новые экраны),
`docs/admin-guide-ru.md` (как включать `dangerous_check_enforced`, как регистрировать
лицензию, что делать после юр-сверки перечней), Progress-секция с хешами.

---

## Интерфейс к соседним доменам (не реализовывать здесь)
- P4-скоринг читает substance-совпадение опционально — после P5 обновить константу.
- P6 (lab) ссылается на substance в `LabOrder` — FK появляется здесь; лаб-паспорт как
  вид файла оффера — домен P6.
- Live-реестр (если появится) — P7; интерфейс `lookup_substance` в
  `integrations/chem_registry/` — тонкий stub здесь.

## Progress

Реализовано полностью. Миграция одна — **`0027_compliance`** (скелет говорил «0026»,
занят `rfq_push_log` из P4).

- [x] детализация плана (после R4) → задачи T1.1…T6.1 — `b133432`
- [x] **T1.1** — enum'ы `regulation_level` / `regulation_regime` / `license_status`,
  `offer_file_kind += sds/coa`, таблицы `substances` / `company_licenses` /
  `substance_suggestions`, ALTER `seller_offers` (вещество + кеш вердикта), DB-doc v1.11 — `b133432`
- [x] **T2.1–T2.5** — сид `substances_v1.json` (`v1-provisional`), `substance_service`,
  `/admin/substances`, `GET /portal/substances`, stub `integrations/chem_registry` — `ec6c6fe`
- [x] **T3.1–T3.4** — `offer_compliance_service` (табличный тест до кода),
  `company_license_service` + админ/портальные API, гейт `dangerous_check_enforced`,
  комплаенс-блок в модерации — `f5ae9de`
- [x] **T4.1+T4.2** — prompt-семья `substance_match_v1`, `substance_ai_service`
  (бюджет-гейт, журнал), endpoints подсказки и решения, `substance_ai_enabled` — `d22080b`
- [x] **T5.1+T5.2** — портал (блок вещества, панель требований, лицензии) и dashboard
  (`/substances`, комплаенс в модерации, лицензии в карточке компании), i18n 3+5 — `7adb41f`
- [x] Правки после живой браузерной проверки (три дефекта) — `401df58`
- [x] **T6.1** — DB-doc, CLAUDE-дельты, раздел 9 в `admin-guide-ru`, Progress

### Отклонения от плана (и почему)

1. **`CompanyLicense` не существовало.** FR-C4 ссылается на «существующий compliance-поток
   R1», но в R1 отгружены только `verification_documents` (`kind=license`) — без режима,
   без срока как факта. Проверять «есть принятая лицензия» без режима нельзя: экологический
   сертификат разблокировал бы прекурсоры. Таблица `company_licenses` реализована по уже
   спроектированному в `company-verification/ARCHITECTURE.md` §CompanyLicense (урезанно: без
   `license_types`/`license_requirements` — это отдельная подсистема, план её не просит).
2. **Гейт ДЕРЖИТ оффер черновиком, а не отклоняет запрос.** Документы можно приложить только
   к существующему офферу (`POST /offers/{id}/files`), поэтому отказ на создании сделал бы
   `docs_required`-оффер непубликуемым в принципе. Оффер сохраняется как `draft` со списком
   требований; выполнение требования на следующем сохранении отправляет его на модерацию.
   409 остаётся у staff при одобрении.
3. **`offer_service.publish` не существует.** Публикация = подача (портал) + одобрение
   (модерация). Закрыты обе точки, включая телеграм-путь модерации.
4. **«Независимо от гейта документов» прочитано так:** настройка `dangerous_check_enforced`
   гейтит саму блокировку (инвариант «no enforcement flips in code»), а `prohibited` внутри
   блокировки не снимается ничем — ни документами, ни лицензией. Тест фиксирует обе половины.
5. **Демо идёт на ацетоне, а не на метаноле.** ТЗ приводит «Метанол» как пример
   `license_required`, но его принадлежность к Списку IV из правовой карты не подтверждается,
   а сид не выдумывает позиции. Ацетон (≥60%) подтверждён `INTEGRATIONS.md` §4 и заодно
   показывает работу порога концентрации.
6. **Сид намеренно неполон** (`v1-provisional`, 14 позиций): полные приложения к ПКМ не
   отдаются программно, юр-сверка — операторская задача. Ревизия видна в админке; правка
   строки руками снимает метку ревизии, и следующая ревизия сида её не перезапишет.
7. **Модуль моделей — `app/models/compliance.py`**, а не `substances.py` из `00-CONTEXT`:
   он владеет тремя таблицами контекста, а не одной.
8. **Срок действия лицензии считается на чтении**, а не ночной развёрткой статуса: свип
   оставил бы окно, в котором просроченная лицензия ещё разблокирует продажу прекурсора.
   Значение `license_status.expired` в enum есть — под будущий live-реестр (P7).
9. **`offer_file_kind += sds, coa`** — перечень обязательных документов вещества называет
   SDS/TDS/COA, а в enum был только `tds`; проверять `docs_required` было нечем.
10. **Оффер отдаёт саму строку справочника** (`substance`), а не только `substance_id`:
    без неё форма редактирования не могла показать выбранное вещество, и «очистить» было
    неотличимо от «не трогал».

### Живая проверка (браузер, Playwright MCP)

Форма оффера: поиск «ацетон» → «Нужна лицензия» ещё до сохранения, выбор автозаполняет
CAS/ТН ВЭД. AI-подсказка (клиент замокан канонным ответом — ключ в стенде плейсхолдерный):
карточка «Ацетон · CAS 67-64-1 · 2914.11» с «Подтвердить/Не подходит», подтверждение
заполняет поле, в журнале строка с моделью, версией промпта, токенами и `accepted=true`.
Гейт on: оффер сохранён черновиком с «Предложение не публикуется → Нужна действующая
лицензия: Прекурсоры (Список IV, ПКМ-330)»; ДДТ — «Размещение запрещено» с основанием
ПКМ-916 и явным «загрузка документов этого не изменит». Регистрация лицензии в карточке
компании → повторное сохранение оффера → «На модерации». Отзыв лицензии → карточка
модерации показывает «публикация заблокирована», кнопка «Одобрить» возвращает причину.
Dashboard `/substances`: пороги, акты-основания, баннер о provisional-ревизии; правка
порога сохраняется и снимает метку ревизии.

**Три дефекта нашёл только экран** (`401df58`): держащийся черновик нельзя было
разблокировать лицензией (её нельзя приложить к офферу); очередь модерации падала на
офферах портальных компаний (`seller` = null, баг с R1); в русском дашборде печаталось
`precursor_list_iv`.

### Осознанные пробелы

- **Нет e2e-спеки на P5** — та же причина, что в P1–P4: в репозитории нет пути к
  *верифицированной* компании из e2e. Покрытие даёт связка guarded real-DB тестов
  (114 в P5-семействе) и живой браузерной проверки.
- **Сид v1 неполон** — см. отклонение 6; включать `dangerous_check_enforced` до юр-сверки
  нельзя (написано в баннере админки и в `admin-guide-ru` §9).
- **`license_category` не используется сидом** — механизм реализован и покрыт тестами
  (лицензия без категории не закрывает категорированное требование), но ни одна позиция v1
  категорию не называет: выдумывать названия категорий лицензий нельзя.
- **`chem_registry` — только stub**: машиночитаемого реестра не существует; `live` падает
  громко, чтобы P7 не подключил тишину вместо реестра.
