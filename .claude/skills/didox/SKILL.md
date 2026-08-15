---
name: didox
description: Expert knowledge of the Didox (didox.uz) EDI/e-invoicing partner API for Uzbekistan — E-IMZO signing, the two-token auth model, document lifecycle (ЭСФ/акт/договор/ТТН/доверенность), JSON payload schemas, and polling. Use when integrating, debugging, or reviewing anything that talks to api-partners.didox.uz / testapi3.didox.uz, signs documents with E-IMZO/CAPIWS, or implements the polymer-intelligence P7.a Didox track.
---

# Didox partner API

Didox (ООО «DIDOX TECH», ИНН 310529901) is Uzbekistan's largest private EDI operator
(~350k companies). Its partner API creates, signs, and delivers legally significant
documents — счёт-фактура (ЭСФ), акт, договор, ТТН, доверенность — which sync to the
roaming centre `my.soliq.uz` and the other 27 UZ operators. **One integration reaches
every counterparty**, whoever their operator is.

| | |
|---|---|
| Test | `https://testapi3.didox.uz/` |
| Prod | `https://api-partners.didox.uz/` |
| Docs | `https://api-docs.didox.uz/ru/` — mirrored in `reference/` (see [Reference map](#reference-map)) |
| Partner token | offline onboarding via account manager — [t.me/Didox_account](https://t.me/Didox_account), +998 50 122 05 18 |
| Change channel | [t.me/didoxapiupdates](https://t.me/didoxapiupdates) — **watch it; there is no changelog in the docs** |

---

## 1. The auth model — two independent tokens

Every request carries **both**. Confusing them is the most common integration failure.

```http
Partner-Authorization: <PARTNER_TOKEN>   # your integrator identity — a server-side SECRET
user-key: <USER_TOKEN>                   # the acting user/company — UUID, TTL 360 minutes
```

- `Partner-Authorization` is **required on every endpoint**, including auth and `/v1/dsvs/*`.
  It identifies you as an integrator, never a person. **It must never reach a browser.**
- `user-key` is obtained per user and is what makes an action attributable. It expires after
  **360 minutes** — cache it with a shorter TTL and re-mint, never assume it is alive.

Three ways to mint a `user-key` (all `POST`, all return `{"token": "<uuid>", ...}`):

| Method | Endpoint | Notes |
|---|---|---|
| By E-IMZO | `/v1/auth/{taxId}/token/{locale}` | body `{"signature": "<timeStampTokenB64>"}` — signature over the **INN in base64** |
| By password | `/v1/auth/{taxId}/password/{locale}` | body `{"password": …}`; password set at registration |
| Enter a company | `/v1/auth/company/{companyTaxId}/login/{locale}` | header `user-key` = the *individual's* token; returns a company token + `permissions.roles[]` |

**Password lockout ladder** (page 03): 3 wrong/min → 10 min block · 10 wrong → 24 h · 25 wrong →
**permanent**. Never retry a password login in a loop.

Errors: `422 User not registered` · `401 Unauthorized. Invalid signature` · `423` blocked ·
`429` too many attempts.

> **Architectural consequence.** Minting a user-key by E-IMZO requires the client's private key,
> which lives only on their machine. You *cannot* mint one server-side. So either (a) the user
> signs in the browser each time the cached key expires, or (b) you use password auth for
> unattended flows. Plan the UX around the 360-minute wall before writing code.

---

## 2. The signing pipeline — the one flow everything reuses

**Didox never signs for the user.** The PKCS#7 is produced by the local E-IMZO module on the
client's machine; Didox only attaches a TSA timestamp and delivers. Every signature in the
whole API is these four steps:

```
1. list keys      CAPIWS  {"plugin":"pfx","name":"list_all_certificates"}   → certificates[]
2. load key       CAPIWS  {"plugin":"pfx","name":"load_key",
                           "arguments":[disk, path, name, alias]}           → keyId
3. create pkcs7   CAPIWS  {"plugin":"pkcs7","name":"create_pkcs7",
                           "arguments":[<data b64>, keyId, "no"]}           → pkcs7_64, signature_hex
4. timestamp      POST /v1/dsvs/timestamp {pkcs7, signatureHex}             → timeStampTokenB64
```

- CAPIWS is the local E-IMZO desktop module: `wss://127.0.0.1:64443/service/cryptapi`, headers
  `Host: 127.0.0.1:64443` and `Origin: https://<your site>`. With E-IMZO installed, its own API
  doc is at `https://127.0.0.1:64443/apidoc.html`. USB-token variant uses `plugin: "ckc"` /
  `list_ckc` (see `reference/01-eimzo.md`).
- **Step 4 is not optional.** `timeStampTokenB64` is what goes in the `signature` field —
  a bare `pkcs7_64` is rejected everywhere.
- What you sign in step 3 differs per action; that is the *only* thing that varies:

| Action | Data signed (base64 of…) |
|---|---|
| Auth by E-IMZO | the **INN** string |
| Sign an **outgoing** document | `data.json` from `GET /v1/documents/{id}?owner=1` |
| Sign an **incoming** document | `GET /v1/documents/{id}/documentBase64`, then joined (below) |
| reject / cancel / accept / ТТН actions | the `data` returned by `POST /v1/documents/{id}/tosign` |

### The three sign shapes

**Outgoing** — `POST /v1/documents/{id}/sign` with `{"signature": timeStampTokenB64}`.

**Incoming** — same endpoint, but the signature must be *joined* with the sender's:

```
GET  /v1/documents/{id}/documentBase64      → sign it → timestamp it       (yours)
GET  /v1/documents/{id}?owner=0             → data.toSign                  (theirs)
POST /v1/dsvs/signature/join {signature1: <toSign>, signature2: <yours>}  → pkcs7B64
POST /v1/documents/{id}/sign {"signature": <pkcs7B64>}
```
Requires **E-IMZO ≥ 6.3.5** on the client machine.

**Action** — `POST /v1/documents/{id}/tosign` `{"action": …, "comment": …}` first, then the
matching endpoint (`/reject`, `/delete`, `/give`, `/return`, `/tillreturn`).
`action` ∈ `accept · cancel · reject · responsibleGive · responsibleAccept ·
responsibleTillReturn · responsibleReturn · consignorReturn · consignorReturnAccept ·
accountantAccept · agentAccept`. Unknown → `Unsupported action`; wrong doc type →
`Not supported operation`.

> ⚠️ **`tosign` returns two different shapes.** `data` is either an **object to sign** or an
> **already-built base64 signature string** — and for some (action, docType) pairs it is empty.
> Branch on the runtime type; do not assume. See `reference/06-documents.md` §8.

---

## 3. Document lifecycle

```
create draft ──sign──▶ awaiting partner (1) ──partner signs──▶ signed (3)
    │                        │
  update/delete           reject (4) / cancel-delete (5)
```

Sending **is** signing — there is no separate send call. The counterparty sees the document the
moment you sign it.

| # | Method | Endpoint | Purpose |
|---|---|---|---|
| 1 | GET | `/v2/documents` | list — **`page` and `limit` are mandatory** (limit ≤ 100) |
| 2 | GET | `/v2/documents/statistics/all` | counters |
| 3 | GET | `/v1/documents/{id}` | detail (`?owner=1` outgoing / `?owner=0` incoming) |
| 5 | POST | `/v1/documents/{docType}/create/{locale}` | create draft |
| 6 | POST | `/v1/documents/{id}/update/{docType}/{locale}` | update draft |
| 7 | POST | `/v1/documents/{id}/delete/draft` | delete draft |
| 8 | POST | `/v1/documents/{id}/tosign` | get data to sign for an action |
| 9/10 | POST | `/v1/documents/{id}/sign` | sign outgoing / incoming |
| 11 | POST | `/v1/documents/{id}/reject` | refuse (`comment` **must match** the `tosign` comment) |
| 12 | POST | `/v1/documents/{id}/delete` | cancel a sent document |
| 16 | GET | `/v1/documents/view/{id}/html\|pdf/{locale}` | printable form |
| 17 | GET | `/v1/documents/{id}/archive` | **evidence pack** — ZIP (signatures + PDF + JSON) in the response body |
| 18 | GET | `/v1/documents/contract/{contractId}/info/{locale}` | contract data to prefill an ЭСФ |

**docType codes** — `002` ЭСФ · `008` ЭСФ ФАРМ · `023` гибридная ЭСФ · `041` ТТН · `005` акт ·
`006` доверенность · `062` доверенность (новая) · **`007` договор (ГНК / «Договор НК»)** ·
`000` произвольный · `010` многосторонний произвольный · `052` акт сверки · `054` акт
приёма-передачи · `075` протокол собрания · `031` письмо НК.

**Statuses** — `0` черновик · `1` ждёт подписи партнёра · `2` ждёт вашей подписи · `3` подписан ·
`4` отказ · `5` удалён · `55` черновик удалён · `40` недействительный · `50` аннулирован НК ·
`60` ждёт подписи агента.
**ТТН uses a different ladder**: `110` отправлено · `140` принято отв. лицом · `150` груз
возвращён · `160` доставлено · `170` отказано грузополучателем · `190`/`200` возвраты.
Доверенность (новая): `310`/`340`/`360`. Full tables: `reference/09-catalogs.md` §6.

### There are no webhooks

Not for partners, not in any published page. **Poll** `GET /v2/documents` with
`dateFromUpdated` / `dateToUpdated` (`yyyy-mm-dd`) as the incremental cursor, plus `status`,
`doctype`, `partner`, `owner` filters (comma-separated multi-values allowed:
`?doctype=002,008,001`). Ask your account manager whether partner webhooks exist yet — the
public docs are the only source and they say no.

---

## 4. Gotchas that cost hours

1. **PascalCase in, lowercase out.** You POST `{"ContractDoc": {"ContractNo": …}}`; Didox stores
   and returns `document_json` with **every key lowercased** (`contractdoc.contractno`). Your
   serializer and your parser are not symmetric. This bites on every document type.
2. **The offer must be signed before the first document.** Otherwise `422` with
   `{"context": {"offer": "required"}}`. It is a one-time per-user/company step:
   `GET /v1/newoffer/base64` → `POST /v1/documents/offer/create` → `POST /v1/documents/offer/sign`
   (`reference/11-offer-signing.md`). Build it into onboarding or every first send fails.
3. **`200 OK` can still carry a warning.** `{"data": true, "warningDetails": {…}}` — the tax
   committee accepted with remarks. Log it; do not treat non-null `warningDetails` as failure.
4. **Errors carry `errorDetails`** `{id, title, message, description}` where `id` is the
   `x-trace-id` — quote it to support. `title`/`description` language follows `Accept-Language`,
   and are `null` when no explanation exists.
5. **`signature` vs `pkcs7`.** `/reject` and `/delete` accept either field name. `/sign` wants
   `signature`. Send `signature` everywhere and move on.
6. **Reject comment must be byte-identical** to the comment passed to `tosign`, or it fails.
7. **`/v2/documents` without `page` + `limit` misbehaves** — the docs make both mandatory.
8. **`locale` is a path segment** (`/ru`, `/uz`), not a query param, on most endpoints.
9. **CAPIWS `Origin` must be your real site origin** — the module rejects mismatches, which
   presents as a generic connection failure in the browser console.
10. **`user-key` is a UUID, not a JWT.** You cannot read an expiry out of it. Track issue time.
11. **The archive is the legal evidence.** ZIP with signatures + PDF + JSON, returned directly
    in the body. Fetch it once on transition to signed, hash it, store it — do not re-fetch on
    demand and do not treat the PDF alone as proof.
12. **`503` from a `/sign` means the tax committee's service was slow, not that you failed.**
    Retry idempotently; check the document status before re-signing.

---

## 5. Reference map

Full verbatim mirrors of every published page (Russian, as authored). Read the specific file
rather than guessing — these are the authority.

| File | Page | Read it for |
|---|---|---|
| `reference/01-eimzo.md` | 01. Работа с E-IMZO | CAPIWS protocol, .pfx + USB token, `create_pkcs7`, `/v1/dsvs/timestamp` |
| `reference/02-registration.md` | 02. Регистрация | `POST /v1/auth/signup` — first-time user registration by ЭЦП |
| `reference/03-login.md` | 03. Логин | the three auth methods, token TTL, lockout ladder, `permissions.roles` |
| `reference/04-account.md` | 04. Аккаунт | account state, password set/change |
| `reference/05-profile.md` | 05. Профиль | company profile, branches, employees, roles/permission codes |
| `reference/06-documents.md` | 06. Документы | **the lifecycle** — 22 methods, every request/response/error table |
| `reference/07-document-json.md` | 07. JSON документов | **payload schemas** for all 16 document types, field by field |
| `reference/08-utils.md` | 08. Утилиты | 26 helpers — VAT privilege checks, ИКПУ, INN/PINFL lookup, transport, ж/д stations, regions |
| `reference/09-catalogs.md` | 09. Каталоги | banks, measures, regions, districts, rail lines, **status tables** |
| `reference/10-document-templates.md` | 10. Шаблоны договоров | contract-template CRUD |
| `reference/11-offer-signing.md` | 11. Подписание оферты | the one-time offer signature that unblocks sending |

Document-type sections inside `07-document-json.md`: `1` ЭСФ · `2` ЭСФ ФАРМ · `3` гибридная ·
`4` ТТН · `5` акт · `6` доверенность · **`7` Договор НК** · `8` произвольный · `9` акт сверки ·
`10` акт приёма-передачи · `11` многосторонний · `12` протокол · `13` письмо НК ·
`14`/`15` гибридные · `16` доверенность (новая).

---

## 6. Browsing the live docs

The mirror can go stale — Didox ships changes without a changelog. Re-read the source whenever
a detail matters.

**`WebFetch` on `api-docs.didox.uz` returns almost nothing** — it is a Wiki.js SPA and the
fetcher sees only the shell. Three ways that do work:

```bash
# 1. Page index — public GraphQL (pages.single is NOT public; it 403s)
curl -s -X POST https://api-docs.didox.uz/graphql -H "Content-Type: application/json" \
  -d '{"query":"{pages{list(locale:\"ru\"){id path title}}}"}'

# 2. Full content — the HTML *is* server-rendered, inside <template slot="contents">
curl -sL -A "Mozilla/5.0" https://api-docs.didox.uz/ru/integrators-documents

# 3. Refresh the whole mirror in place (does 1 + 2 + HTML→Markdown)
uv run --no-project --with html2text python scripts/refresh_docs.py
```

Or drive it with the Playwright MCP tools (`browser_navigate` → `browser_snapshot`) when you
need the rendered tabs/anchors rather than the raw markdown.

---

## 7. Scripts

| Script | What it is |
|---|---|
| `scripts/didox_client.py` | Standalone typed `httpx` client covering auth, dsvs, documents, catalogs. Runnable (`python didox_client.py --help`) and the intended base for `backend/app/integrations/didox/client.py`. |
| `scripts/sign_flow.py` | The three signing flows as pure orchestration over an injectable `Signer` — the ordering is the hard part and it is encoded here, testable without a smart card. |
| `scripts/refresh_docs.py` | Re-pulls `reference/*.md` from the live wiki. |

---

## 8. Integrating in polymer-intelligence

The repo already has the client-side half of this working — R3 shipped E-IMZO company
confirmation and contract e-signing. **Didox is P7.a of the deal-lifecycle track, and it is
the only piece still waiting on an external credential (the partner token).** The design was
settled in `.planning/deal-lifecycle/INTEGRATIONS.md` §1 — read it before changing the shape.

### What already exists — reuse, do not rebuild

| Piece | Where | Reuse as |
|---|---|---|
| Browser E-IMZO bridge | `portal/src/shared/lib/eimzo/capiws.ts` | steps 1–3 of the signing pipeline, already written (`probe`/`listCertificates`/`sign`) |
| Signing UI | `portal/src/features/eimzo-sign/` | the dialog + `useEimzoSign` hook |
| Gateway pattern | `backend/app/integrations/eimzo/client.py` | copy its shape verbatim: `CircuitBreaker`, `ProviderUnavailable`, `integration_call_log` on an **isolated session**, 4xx = domain result / 5xx = outage |
| Breaker | `backend/app/integrations/circuit_breaker.py` | as-is |
| Contract state machine | `backend/app/domains/contracts/` | Didox doc id + status live here, next to the existing e-sign flow |

### The shape to build

```
backend/app/integrations/didox/
  client.py     DidoxClient — port scripts/didox_client.py, wrapped in the eimzo/client.py pattern
  __init__.py   module-level entry points + ProviderUnavailable re-export
```

- **Config** (`app/core/config.py`): `DIDOX_BASE_URL` (default the test host) and
  `DIDOX_PARTNER_TOKEN` — a **secret with no default**, per the repo's fail-fast contract. Add
  both to `deploy/.env.example`.
- **Runtime mode**: a `didox_mode` `SettingSpec` (`stub` | `live`) in
  `app/services/settings_service.py` `_SPECS`, mirroring `escrow_mode` / `gov_registry_mode`.
  Ship `stub`. Follow `StubGovRegistryClient`'s rule: **a stub raises rather than returning
  empty data** — an empty document list reads as "the counterparty never signed", which turns
  our missing integration into a false statement about a real company.
- **The partner token is server-side only.** The browser signs and posts `pkcs7_64` +
  `signature_hex` to *our* API; the backend calls `/v1/dsvs/timestamp` and then `/sign`.
  Never proxy `Partner-Authorization` to the client.
- **user-key caching**: Redis, keyed by company INN, TTL well under 360 min. Because it can only
  be minted with the client's key, expiry means re-prompting the user — surface that in the UI
  rather than failing the action.
- **Polling task**: `poll_didox_statuses` in `app/tasks/`. There is no "integrations" queue —
  put it on **`verify`**, where the other isolated provider work already lives
  (`reconcile_escrow_payments`), and register the module in `_TASK_MODULES` in
  `app/tasks/celery_app.py` (autodiscover is a no-op here). Must be idempotent.
- **Migration**: check the current head with `ls backend/alembic/versions | tail -1` (it was
  `0040` when this skill was written; the root `CLAUDE.md` chain description lags reality).
- **Document type**: use **`007` Договор (ГНК)** for deal contracts — it is legally significant
  and syncs to the roaming centre. `000` «Произвольный документ» is a PDF ≤ 10 MB that never
  leaves Didox, so it is not a substitute.
- **Evidence**: fetch `/archive` on transition to signed, store to S3 with its sha256 — the same
  discipline the escrow rail uses for provider events.

### Working rules on this track

- **Strict TDD** for verification/portal/contract work — write the test per task, run tests after
  each task.
- Run the **full** `pytest tests/` (not a subset) green before committing.
- Gates: `ruff check .` · `mypy app --ignore-missing-imports` · `pytest tests/ -q`, all from
  `backend/`.
- No `Co-Authored-By` / attribution footer in commits.
- Start against `https://testapi3.didox.uz/`; prod is a different host *and* a different token.
