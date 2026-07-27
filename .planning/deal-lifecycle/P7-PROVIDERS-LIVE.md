# P7 — Live-интеграции: Didox, Escrow-банк, гос-реестры (R6 — скелет)

> Статус: **скелет — детализируется по мере получения внешних доступов**, по одному
> провайдеру за раз (каждый — отдельная сессия/подплан). Prereq: `00-CONTEXT.md`,
> P2+P3; факты и контракты адаптеров — **`INTEGRATIONS.md`** (главный документ этого
> плана). Внешние блокеры — операторские: partner-token Didox, договор+спека банка,
> доступ к ПЦД.
> **Методология: строгий TDD** (тест до кода per task; полный `pytest tests/ -q` +
> фронт-гейты перед каждым коммитом). Внешние API в CI не вызываются никогда — клиенты
> мокать по образцу `integrations/eimzo` (тесты с mocked adapter); против реальных
> тест-контуров (testapi3, банковский sandbox) — только ручные интеграционные прогоны
> вне CI, журналируемые в Progress-секции.

## P7.a Didox (первый — доки публичны, тест-контур доступен)
- `integrations/didox/client.py` по контракту из INTEGRATIONS.md §1 (auth_user по ЭЦП
  → user-key TTL 360 мин в Redis; create «Договор НК»; timestamp; sign;
  join_signatures; list_updated; fetch_archive → S3 evidence + sha256).
  Секреты: `DIDOX_PARTNER_TOKEN`, `DIDOX_BASE_URL` (testapi3 → api-partners) —
  без дефолтов, `.env.example` + CI в том же коммите.
- `contracts.signing_provider` ('eimzo'|'didox', default eimzo) + выбор в
  contract-флоу; рендер наших variables → структура `ContractDoc` (Parts[] из
  шаблона, Products[] из variables).
- Подпись в portal: существующий `features/eimzo-sign` + шаг timestamp.
- Celery `poll_didox_statuses` (беат, инкрементально по dateFromUpdated; модуль в
  `_TASK_MODULES`) → маппинг статусов Didox (1/2/3/4/50) на contract-переходы →
  события → Deal (обработчики P2 уже есть).
- Приёмка: контракт через Didox на testapi3 двумя тест-компаниями; отказ; архив
  сохранён и sha256 совпадает; недоступность Didox не блокирует eimzo-путь.

## P7.b Escrow-банк (по получении спецификации)
- `LiveEscrowClient` (маппинг спеки банка на протокол P3), webhook-роут
  `POST /api/v1/webhooks/escrow/{provider}` (подпись/секрет банка → строка в
  `provider_events`, 200 всегда после записи) + Celery-обработчик →
  `escrow_service.apply_provider_event`; fallback-polling beat.
- Переключение `escrow_mode=live`; операторские mark-кнопки остаются как аварийный
  путь (с предупреждением).
- Приёмка: sandbox-цикл funded→released; идемпотентность повторного webhook;
  расхождение статусов (банк released, deal не delivered) → алерт, не авто-переход.

## P7.c Гос-реестры (по получении ПЦД / OneID)
- `integrations/gov_registry/client.py` (lookup_company/lookup_licenses/lookup_vat
  по фактической спеке ПЦД) → immutable snapshots (evidence-паттерн R3) →
  upsert авто-чеков `VerificationCase` (`method: registry`) → re-run evaluator.
  Очередь `verify`; недоступность → чек `unavailable`, ручной путь работает.
- Опционально OneID как доп. канал входа (отдельное решение, не смешивать с этим
  подпланом).
- Приёмка: авто-approve кейса при зелёных registry-чеках + E-IMZO; drift-сценарий
  (компания ликвидирована) → re-verification флоу R1.

## P7.d Chem-registry (только если появится гос-API — мониторить закон «О химбезопасности»)
`integrations/chem_registry/lookup_substance` → сверка/обогащение нашего справочника
(P5 остаётся источником истины до официального реестра).

## Правила для всех подпланов
Паттерн шлюза из `00-CONTEXT.md` (circuit breaker, call log, stub-фабрика, деградация);
каждый подплан детализируется в задачи только после получения фактической документации
провайдера; ничего не менять в моделях P2/P3/P5 — только клиенты, задачи и маппинг.

## Progress
- [ ] P7.a … P7.d (по мере доступов)
