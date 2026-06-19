# Phase 6: Acceptance & Handover - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 6-acceptance-handover
**Areas discussed:** Acceptance protocol form, Restore test (§6.1.5), Handover docs scope, Channel acceptance (§6.1.6), Dependency-reproducibility todo

---

## Acceptance protocol form

| Option | Description | Selected |
|--------|-------------|----------|
| Protocol doc + local synthetic smoke | One consolidated 06-ACCEPTANCE.md (each §6.1.1–6.1.6 → procedure → automated evidence → blocking customer input + sign-off) AND a local full-stack docker-compose smoke against synthetic data; only customer-gated bits remain for deploy day | ✓ |
| Consolidated protocol doc only | 06-ACCEPTANCE.md as the single sign-off artifact; rely on existing per-phase automated gates, no new local bring-up | |

**User's choice:** Protocol doc + local synthetic smoke
**Notes:** Smoke doubles as deployment-guide validation (compose up → migrate+seed → /health → synthetic request → feed → forced fake-source failure → isolation+alert). Maps to D-01 / D-02.

---

## Channel acceptance (§6.1.6)

| Option | Description | Selected |
|--------|-------------|----------|
| Close locally, fixture/mock-driven | Prove wizard → Test → enable-gate → fixture MTProto message → parse_telegram_item → signal in v_live_feed, no real account; live ingestion stays the deploy drill | ✓ |
| Fold entirely into deploy drill | No local fixture path; document channel onboarding as a deploy-time step with the customer's real account | |

**User's choice:** Close locally, fixture/mock-driven
**Notes:** Mirrors Phase 5's key-free fixture approach; retires the SC#5 telegram cross-phase caveat carried since Phase 4. Maps to D-03.

---

## Restore test (§6.1.5)

| Option | Description | Selected |
|--------|-------------|----------|
| Run locally now + record timing | pg_dump → fresh PG16 container → restore via runbook → verify → record wall-clock; self-contained, validates the procedure | ✓ |
| Document-only, deploy-time drill | Keep §6.1.5 as a deploy-time step on the customer VPS; Phase 6 only refines the runbook | |

**User's choice:** Run locally now + record timing
**Notes:** Fresh container = clean environment for proving the procedure; deploy-day rerun confirms VPS hardware timing. Runbook gaps fixed in-phase. Maps to D-04.

---

## Handover docs scope

| Option | Description | Selected |
|--------|-------------|----------|
| Production docker-compose.yml | Full container set (api, worker, beat, userbot, dashboard, postgres, redis, nginx) | ✓ |
| Deployment guide | Env/secrets, TLS certbot, first-run migrate+seed, bot webhook + userbot session, backup cron | ✓ |
| Admin guide | Non-developer operator: add-source wizard, alert rules, needs_review, token budget | ✓ |
| HANDOVER.md index | Single entry point linking all §9 deliverables | ✓ |

**User's choice:** All four
**Notes:** Existing runbook/extraction-schema/dev-spec reused, not rewritten. Maps to D-05.

### Sub-decision — Doc language

| Option | Description | Selected |
|--------|-------------|----------|
| Admin guide RU, deployment/compose EN | Admin guide in Russian (operator audience); deployment guide + compose + index in English (ops audience, consistent with existing dev docs) | ✓ |
| All handover docs in English | Consistency with existing docs/ set | |
| All handover docs in Russian | Match client TZ language throughout | |

**User's choice:** Admin guide RU, deployment/compose EN
**Notes:** Maps to D-06.

---

## Dependency-reproducibility todo (cross-reference)

| Option | Description | Selected |
|--------|-------------|----------|
| Fold into Phase 6 | Commit uv.lock (or pinned reqs), fix 2 stale route tests, reproducible CI — handover hygiene | ✓ |
| Keep as deferred tech-debt | Leave in backlog; revisit post-handover | |

**User's choice:** Fold into Phase 6
**Notes:** Todo `backend-dep-reproducibility-and-stale-route-tests.md` (score 0.6, tooling). Reproducible/green build is part of "documented and handed over." Maps to D-07.

---

## Claude's Discretion

- Synthetic/fixture data shape for the D-02 smoke and D-03 channel close (reuse existing fixtures).
- Structure/section ordering of 06-ACCEPTANCE.md, deployment guide, and admin guide.
- D-02 smoke wired as a scripted make/CI target vs. documented manual sequence.
- Pin mechanism for D-07 (`uv.lock` vs. pinned `requirements.txt`) consistent with `pyproject.toml`.

## Deferred Ideas

- Live customer-gated drills (real BOT_TOKEN + public HTTPS §6.1.1; real userbot account/session + live channel §6.1.6 ingestion; customer 100-message sample + synonyms + trader sign-off §6.1.3; live source-failure on the VPS §6.1.4; restore rerun on the customer VPS §6.1.5) — documented in 06-ACCEPTANCE.md as deploy-day steps, run via `/gsd-verify-work` when inputs land. Product decision, not a gap.
- Phase-2 / Future-Milestone items remain out of this milestone.
