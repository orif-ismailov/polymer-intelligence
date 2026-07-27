# P5 — Compliance: справочник веществ, ТН ВЭД/CAS, гейт публикации (R5 — скелет)

> Статус: **скелет — детализировать после приёмки R4** (P1–P4). Prereq: `00-CONTEXT.md`,
> P1 (форма оффера). ТЗ: блок B, FR-C1–C6; правовая карта — `INTEGRATIONS.md` §4.
> **Методология: строгий TDD** (тест до кода per task; полный `pytest tests/ -q` +
> фронт-гейты перед каждым коммитом) — детализация плана обязана разложить работы на
> задачи с тестами. Вердикты `offer_compliance_service` — табличный тест до реализации.

**Demo (цель):** оффер «Метанол» при `dangerous_check_enforced=on` не публикуется без
активной лицензии нужного режима; «PP H030» публикуется свободно; AI предлагает
вещество-кандидата, продавец подтверждает; модерация видит комплаенс-статус.

## Контур работ (waves при детализации)

1. **Схема** — миграция `0026_substances`: `substances` (name ru/uz/en; hs_code —
   первичный юр-идентификатор; cas UQ NULL; hazard_class; regulation_level
   free|docs_required|license_required|prohibited; regulation_regime
   precursor_list_iv|explosive_toxic|strong_acting|pkm916_import NULL;
   threshold_concentration_pct; exemption_annual_limit; license_category;
   required_docs JSONB; synonyms JSONB; source_act) + ALTER seller_offers:
   substance_id FK NULL, cas_number, hs_code, declared_concentration_pct NULL.
2. **Сид** — `seed_substances` (идемпотентный, версионируемый): оцифровка Списка IV
   ПКМ-330 (29 позиций, пороги: ацетон ≥60%, толуол ≥70%, соляная к-та ≥15%,
   серная ≥45%, перманганат ≥45%, МЭК ≥80%, ангидрид уксусной — без порога; изъятие
   ≤12 кг/год), ПКМ-818 (сильнодействующие), категорий ПКМ-782 (взрывчатые/ядовитые),
   перечней ПКМ-916 (по ТН ВЭД). **Перед оцифровкой — юр-сверка текущих редакций на
   lex.uz** (операторская задача, вход — приложения к ПКМ).
3. **Сервис** — `offer_compliance_service.evaluate(offer) -> ComplianceVerdict`
   (уровень, чего не хватает: лицензия режима / документы по списку); учёт
   `declared_concentration_pct` против порога; вердикт кешируется на оффере,
   пересчёт при каждом редактировании/переопубликации (FR-C6). Гейт в
   `offer_service.publish` за `dangerous_check_enforced` (default off).
   `prohibited` и Список-IV-без-лицензии → не публикуется независимо от гейта
   документов (решение ТЗ).
4. **AI-подсказка** — новая prompt-семья `substance_match_v1`
   (`parsing/prompts/`, бюджет-гейт как у остальных): текст оффера → кандидат
   substance + concentration; только suggestion, подтверждение продавцом; журнал
   в parse_runs-паттерне.
5. **API/Frontend** — админ-CRUD справочника (dashboard), поле «вещество» с поиском
   в portal offer-form (автозаполнение HS/CAS), комплаенс-панель в карточке
   модерации, экран требований («для публикации нужны: …») в portal.
6. **Настройки** — `dangerous_check_enforced` (bool, off) в `_SPECS`.

## Интерфейс к соседним доменам
- P4-скоринг читает substance-совпадение опционально — после P5 обновить константу.
- P6 (lab) ссылается на substance в `LabOrder` — FK появляется здесь.
- Live-реестр (если появится) — P7; интерфейс `lookup_substance` в
  `integrations/chem_registry/` — тонкий stub уже при детализации.

## Progress
- [ ] детализация плана (после R4) → задачи T1.x…
