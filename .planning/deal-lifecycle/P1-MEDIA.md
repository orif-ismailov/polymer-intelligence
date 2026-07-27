# P1 — Медиа: логотип компании + фото продуктов

> Prereq: `00-CONTEXT.md`. Независим от других планов. ТЗ: блок F, FR-M1–M4.
> **Методология: строгий TDD.** Для каждой задачи T*: сначала тест (красный) → код →
> тест зелёный → прогон затронутого модуля; перед КАЖДЫМ коммитом — полный
> `cd backend && pytest tests/ -q` + `npm run lint`/`typecheck` затронутых фронтов.
> Acceptance-блок волны — минимум тестов, не потолок.
> Текущее состояние: у `Company` нет логотипа вовсе; у офферов backend готов
> (`SellerOfferFile kind=image`, `POST /portal/companies/{id}/offers/{offer_id}/files`
> в `backend/app/api/portal/offers.py:118`), но portal его не вызывает.

**Demo (Definition of Done):** компания загружает логотип в портале → виден в профиле,
шапке кабинета, каталоге контрагентов и карточках офферов; продавец публикует оффер
с 3 фото → обложка в списке маркета, галерея на странице оффера, фото в карточке
модерации dashboard; невалидный файл отклоняется с понятной ошибкой; добавление фото
к опубликованному офферу возвращает его на модерацию.

---

## Wave 1 — Логотип компании (backend)

### T1.1 Миграция `0022_company_logo`
`ALTER TABLE companies ADD COLUMN logo_storage_path TEXT NULL`. Down: drop column.
DB-doc правка в том же коммите.

### T1.2 Storage + сервис
В `storage_service`: `upload_company_logo(db, company, file)` по образцу
`upload_offer_file` — лимит **5 МБ**, допустимые MIME только `image/jpeg`, `image/png`
(magic-byte проверка уже в сервисе), ключ `companies/{company_id}/logo/{uuid}.{ext}`.
Замена: новый объект → обновить `logo_storage_path` → удалить старый объект из S3
(fail-soft: ошибка удаления старого логируется, не роняет запрос).
`delete_company_logo(db, company)` — удалить объект + NULL. Оба пишут audit
(`company.logo_upload` / `company.logo_delete`).

### T1.3 Portal API — `backend/app/api/portal/companies.py`
- `POST /portal/companies/{id}/logo` (multipart) — только owner/manager (существующий
  membership-guard); 201 + обновлённый company payload.
- `DELETE /portal/companies/{id}/logo` — 204.
- Во все company-схемы, где уместно (профиль, directory, offer payload с company),
  добавить `logo_url: str | None` — presigned ссылка TTL ≤ 600 s (образец — R3
  contracts document endpoint). N+1 не плодить: presign — дёшево, но в списках
  directory считать только для страницы выдачи.

**Тесты (перед кодом каждой задачи):** upload happy-path (jpeg, png); oversize → 413/422
typed; поддельное расширение (pdf с .jpg) → отклонён по magic bytes; replace удаляет
старый ключ (mock storage); RBAC — viewer-член и чужая компания → 403/404;
`logo_url` присутствует и подписан. Полный suite перед коммитом.

## Wave 2 — Логотип компании (frontend)

### T2.1 Portal
- `pages/company-view` ProfileSection: блок логотипа (превью/плейсхолдер, кнопки
  загрузить/заменить/удалить; клиентское сжатие/даунскейл до ~1024px перед загрузкой).
- Шапка кабинета (CompanySwitcher) и каталог контрагентов (directory picker из R3
  contracts) — аватар компании с фоллбеком на инициалы.
- i18n ru/uz/en; ошибки маппятся на typed-ответы бэка.

### T2.2 Dashboard
Карточка компании (verification/companies detail) — показ логотипа (read-only).
Локали ru/uz/tr/fa/zh.

**Тесты:** portal lint+typecheck; e2e: загрузка логотипа → виден в профиле и шапке
(fixture-изображение); dashboard e2e smoke не ломается.

## Wave 3 — Фото продуктов (замыкание существующего backend)

### T3.1 Ревизия существующего эндпоинта (backend, малые правки)
`POST /portal/companies/{id}/offers/{offer_id}/files`:
- убедиться/добавить: лимит **8 фото** на оффер (kind=image; 422 `TooManyFiles`),
  ≤ 10 МБ, MIME jpeg/png для kind=image;
- `DELETE /portal/companies/{id}/offers/{offer_id}/files/{file_id}` — только до
  модерации ЛИБО у черновика (если файл у опубликованного — см. T3.2);
- порядок = порядок создания (id ASC), первое фото = обложка; в offer payload —
  `files[]` c presigned `url` + `cover_url`;
- **правило ре-модерации**: добавление/удаление image-файла у оффера в статусе
  `published`/`approved` переводит оффер обратно в pending-модерацию (переход через
  существующий `offer_service`, аудит + событие) — только при включённой модерации.

### T3.2 Portal — dropzone в форме оффера
`features/offer-form`: секция «Фото» — dropzone (мультивыбор, ≤8, превью-сетка,
удаление, первый = «Обложка» с бейджем), клиентское сжатие. Создание оффера:
сначала `POST` оффер (draft), затем последовательная загрузка файлов, потом submit
(существующий флоу сохранений не ломать — файлы догружаются к уже созданному id).
Редактирование: показать существующие фото + предупреждение «изменение фото отправит
оффер на повторную модерацию».

### T3.3 Отображение
- Portal маркет: обложка в карточке списка (`entities/market`), плейсхолдер без ломки
  сетки; `MarketOfferPage` — галерея (миниатюры + основной кадр, свайп на мобиле).
- Dashboard: карточка модерации оффера — сетка фото (клик = открыть полный размер
  через presigned URL).

**Тесты:** backend — лимит 8, ре-модерация на добавление к published, delete-правила,
cover в payload; portal e2e — публикация оффера с 3 фото → обложка в списке → галерея
на странице; модерация в dashboard видит фото.

---

## Интерфейс к соседним доменам (не реализовывать здесь)
- P2 (deals) и P4 (matching) будут читать `cover_url`/`logo_url` из готовых payload'ов —
  ничего специально не готовить.
- Никаких изменений схемы `seller_offer_files` не требуется.

## Progress

Ветка `redesign-architecture`. P0 (дизайн-система) сдан — экраны W2/W3 строить из его
примитивов (`docs/design-system.md` Part II, правила в `portal/CLAUDE.md`).

- [x] **W1** — логотип компании, backend · `b3e8c12`
  - T1.1 миграция `0022_company_logo` (`companies.logo_storage_path text NULL`);
    проверено upgrade → downgrade → re-upgrade на отдельной БД; DB-doc в том же коммите
    (раздел «R4 / P1» + запись v1.6).
  - T1.2 `storage_service.upload_company_logo` / `delete_company_logo`:
    только JPEG/PNG (строже `VERIFICATION_MIMES`), 5 МБ (`MAX_LOGO_SIZE_BYTES`), ключ
    `companies/{id}/logo/{token}.{ext}` из **определённого** MIME — имя файла клиента
    в S3 не попадает вообще. Замена и удаление — fail-soft (`_discard_object`).
  - T1.3 `POST`/`DELETE /portal/companies/{id}/logo`, `logo_url` (presigned, TTL ≤ 600 с)
    в summary+detail, аудит на оба пути.
    **Добавлено сверх плана:** до сих пор все portal-эндпоинты авторизовали только по
    факту членства — роли owner/manager не проверялись нигде. Появился
    `company_service.require_company_role` + `COMPANY_ADMIN_ROLES`. Порядок проверок
    важен: сначала membership-404, потом роль-403, иначе для чужака 404 превратится
    в 403 и утечёт факт существования компании.
  - 28 тестов (сначала красные): миграция, правила стораджа (включая PDF под именем
    `.jpg`, границы 5 МБ, оба fail-soft пути, traversal), API (presigned+TTL,
    replace→delete, идемпотентный delete, типизированные 422, manager можно /
    member 403 / не-член 404, аудит).
  - Головной ассерт «единственный head» в тестах 0017/0018/0020/0021 переведён на 0022
    (так же поступил коммит 0021 со своими предшественниками).
  - Гейты: ruff · mypy (services+schemas) · `pytest tests/ -q` → **1349 passed**.
- [ ] W2 — логотип, frontend (portal + dashboard)
- [ ] W3 — фото офферов (backend-доводка + dropzone + галерея + модерация)

### Замечания для следующих сессий
- Новые API-тесты — в guarded real-DB семье: запускать с
  `DATABASE_URL=postgresql+psycopg://pi_user:devpassword@localhost:5432/test_polymer`
  (см. память `real-db-tests-via-test-polymer`).
- **Осторожно:** при выставленном `DATABASE_URL=…/test_polymer` активируются ДВЕ разные
  семьи DB-тестов на одной базе, и старая (`test_seed_sources`, `test_synonyms_migration`,
  `test_source_failure_alert`) конфликтует — она сама гоняет alembic-downgrade. Это
  **не регресс P1**: проверено на родительском коммите в отдельном worktree (те же ошибки).
  В CI не проявляется — там имя БД `polymer_intelligence_test`, гейт `test_polymer`
  не срабатывает. Общий прогон делать без `DATABASE_URL` (как в CI).
