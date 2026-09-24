# Technologists — a B2B expert marketplace inside IMEX

Status: approved in chat 24.09.2026 (parts 1–2). Parts 3–5 are listed for order only.

## Why

IMEX already connects buyers with manufacturers, traders, carriers and laboratories.
Factories also need *people*: a process technologist to set up a line, switch a grade,
fix an unstable film. IMEX is **not** the employer and not a technology company — it is
the marketplace where a factory's request meets an independent expert's offer.

## Decomposition

| Part | Scope | This spec |
|---|---|---|
| 1 | Technologist account + profile + moderation + public catalog + menu item | ✅ |
| 2 | Factory request → open feed + invites → offers → chat → accept (contacts) → complete + review | ✅ |
| 3 | AI intake: a conversation becomes a structured `tech_requests` row (`source='ai'`) | later |
| 4 | AI matching: % match of profiles to a request | later |
| 5 | AI in the chat (document analysis), identity/experience/certificate verification | later |

## Decisions (from the user)

1. **A technologist is a private person**, not a company. No INN, no company row.
2. **Access = the existing application flow.** «Я технолог» files the same access request
   with `applied_as='technologist'`; staff issue credentials; the expert fills a profile;
   the profile is listed only after staff moderation.
3. **Requests are posted by verified companies only** and are visible to **every published
   technologist** (open feed). The factory's name is hidden until a thread exists. A factory
   may also **invite** a specific expert from the catalog.
4. **Accepting an offer = assignment + contacts.** Contract and payment stay off-platform.
   Afterwards the factory marks the work done and leaves a 1–5 review (the rating).
5. **Architecture A**: a separate bounded context `backend/app/domains/technologists/`,
   technologist routes keyed by the account (`/portal/me/technologist/...`), never a
   hidden «personal company».

## Data model (migration 0055)

`user_accounts.applied_as` — Text, NOT NULL, default `'company'`, check in (`company`,`technologist`).

`technologist_profiles` (1:1 `user_accounts`, unique `user_account_id`)
- identity: `full_name`, `title`, `country`, `city`, `photo_key` (S3, nullable)
- experience: `years_experience` int, `projects_count` int null, `countries_count` int null, `bio` text
- expertise (closed sets, `text[]`): `industries`, `processes`, `materials`
- `equipment_brands text[]` (free), `work_formats text[]` (`online`,`on_site`), `languages text[]` (ISO 639-1)
- `contact_phone`, `contact_email` (shown only to a factory whose offer it accepted)
- moderation: `status` (`draft`,`pending_review`,`published`,`rejected`,`suspended`),
  `submitted_at`, `reviewed_at`, `reviewed_by` (staff), `rejection_reason`
- `published_snapshot jsonb` — the last approved public card; editing a published profile
  re-submits it while the snapshot keeps the catalog showing the approved version.
- `rating_avg numeric(3,2) null`, `rating_count int default 0` — maintained on review insert.

Closed sets live in `technologists/catalog.py` as `Literal`s + tuples (shared with the portal
through the API's `/public/technologists/facets`):
- industries: petrochemical, polymer, packaging, automotive, recycling, chemical
- processes: extrusion, injection_molding, blow_molding, compounding, film, pipe, recycling, thermoforming
- materials: PE, HDPE, LDPE, LLDPE, PP, PVC, PET, PS, ABS, PA, PC, EVA
- need types: equipment_setup, material_selection, production_launch, troubleshooting, process_optimization, other
- urgency: urgent, week, month, date
- work format: online, on_site, both (request) / online, on_site (profile)

`tech_requests`
- `number` `IMX-TECH-000001` (sequence), `public_id uuid`
- `company_id` FK companies, `created_by_user_account_id`
- `need_type`, `process`, `equipment` text, `equipment_model` text null, `product` text,
  `current_material` text null, `target_material` text null, `problem` text,
  `capacity` numeric null + `capacity_unit` (`kg_h`,`t_day`,`t_month`), `country`, `city`,
  `urgency` + `needed_by` date null, `work_format`, `languages text[]`, `budget_note` text null
- `source` (`form`,`ai`) default `form`
- `status` (`open`,`assigned`,`completed`,`cancelled`), `assigned_offer_id` null,
  `completed_at`, `cancelled_at`, timestamps

`tech_request_invites` — (`request_id`, `profile_id`) unique, `created_at`.

`tech_offers` — `request_id`, `profile_id`, `scope` text, `price` numeric(14,2), `currency`
(`USD`,`UZS`,`EUR`), `duration_days` int, `work_format`, `status`
(`submitted`,`accepted`,`declined`,`withdrawn`), timestamps. Partial unique index: one
`submitted|accepted` offer per (request, profile).

`tech_threads` — (`request_id`, `profile_id`) unique, timestamps.
`tech_messages` — `thread_id`, `author_kind` (`company`,`technologist`), `author_account_id`,
`body`, `file_key`/`file_name` null, `created_at`. Append-only.

`tech_reviews` — `request_id` unique, `profile_id`, `company_id`, `rating` 1–5, `text` null,
`created_by_user_account_id`, `created_at`. Immutable.

## Rules

- Profile write: only its own account; submit requires the required fields; staff
  approve/reject/suspend from the dashboard.
- Request create/update/cancel: members of a verified company (same gate as RFQ). Update only
  while `open` and without offers.
- Feed: `open` requests, visible to a caller whose profile is `published`. The company is
  anonymised (`company: null`) unless a thread exists for (request, caller).
- Offer: only a published technologist on an `open` request; edit/withdraw while `submitted`.
- Accept (company): request `open → assigned`, offer `accepted`, all other `submitted`
  offers `declined`; both sides now see contacts. Decline individual offers any time while `open`.
- Complete (company): `assigned → completed` + mandatory review in the same call.
- Cancel (company): `open|assigned → cancelled`; submitted offers become `declined`.
- Thread: the company side or the technologist may open it; only the two parties read it.
- Every state change writes `audit_log` (`tech_request.*`, `tech_offer.*`, `technologist.*`).
- Notifications (`portal_notifications`, i18n keys, deep links):
  new matching request (process ∈ profile.processes) → technologists; invite → invited;
  new offer / message → the other side; accepted/declined → technologist; profile decided → technologist.

## API

Public (anonymous, SSR): `GET /public/technologists` (filters: process, material, language,
country, q; paged), `GET /public/technologists/{id}`, `GET /public/technologists/facets`.
Only `published`, rendered from `published_snapshot`. No contacts.

Portal — technologist (`/portal/me/technologist`): `GET/PUT` profile, `POST .../submit`,
`POST .../photo`, `GET .../requests` (feed, `?invited=1`), `GET .../requests/{id}`,
`POST/PUT/DELETE .../requests/{id}/offer`, `GET .../threads`.

Portal — company (`/portal/companies/{cid}/tech-requests`): list/create/get/update,
`POST {id}/cancel`, `GET {id}/offers`, `POST {id}/offers/{oid}/accept|decline`,
`POST {id}/complete` (with review), `POST {id}/invites` (`profile_id`).

Threads (both sides, party check server-side): `/portal/tech-threads/{tid}/messages`
(GET `after_id`, POST multipart), `.../messages/{mid}/file`; `mine` computed server-side.

Admin (dashboard): `GET /admin/technologists?status=`, `GET {id}`, `POST {id}/approve|reject|suspend`.
The account application queue gains an `applied_as` filter/column.

## Portal screens

- **Menu** (public header + cabinet nav): «Технологи» after «Лаборатории».
- `/technologists` (SSR): hero «Найдите промышленного эксперта для вашего производства» with two
  CTAs — «Мне нужен технолог» (→ `/cabinet/tech-requests/new`, via login) and «Я технолог»
  (→ `/cabinet/register?as=technologist`); filterable catalog of cards (name, title, years,
  processes, materials, country, rating).
- `/technologists/:id` (SSR): full profile; signed-in company member sees «Пригласить к заявке».
- `/cabinet/register?as=technologist`: same form, company name field replaced by «Специализация».
- **Technologist cabinet** — an account with `applied_as='technologist'` and no company skips
  onboarding (`RequireCompany` lets it through to a technologist shell):
  `/cabinet/expert` (profile editor + status banner), `/cabinet/expert/requests` (feed with
  «Приглашения» tab), `/cabinet/expert/requests/:id` (request + my offer form + chat).
- **Company side**: `/cabinet/tech-requests` (list), `/new` (form), `/:id` (details, offers
  list with accept/decline, chat per technologist, invite, complete + review).
- Chat: the shared `ThreadChat`, switched to the server's `mine` flag.

Dashboard: `/admin/technologists` moderation queue + profile review; applications list shows
«Технолог».

## Out of scope (this spec)

AI intake/matching/assistant, identity/experience verification badges, on-platform contract
or payment, public request pages, email notifications, Telegram pushes.

## Testing

TDD per task. Backend real-DB tests (`test_polymer`) for rules and state machines; API tests
for access control (non-party 404, member vs anonymous, unpublished profile invisible, feed
anonymisation). Full `pytest tests/`, ruff, mypy; portal lint/typecheck/build; dashboard
lint/typecheck. Browser: the whole loop — apply as technologist → staff issue creds + approve
profile → company posts request → technologist sees it anonymised → offer + chat → accept →
contacts visible → complete + review → rating on the public card. Temp data removed after.
