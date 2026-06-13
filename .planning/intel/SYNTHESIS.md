# Synthesis Summary

Single entry point for downstream consumers (e.g. gsd-roadmapper). Produced by gsd-doc-synthesizer
from the per-doc classifications and source documents.

Mode: new (net-new bootstrap)
Precedence applied: ADR > SPEC > PRD > DOC (no per-doc overrides; no ADR docs in set)
Source language: mostly Russian; synthesized intel and conflict report rendered in English.
Domain identifiers (table names, FR-IDs, ENUM values, endpoint paths, REQ-number format,
Incoterms) preserved verbatim.

---

## Doc counts by type (4 total)

- PRD (1): docs/polymer-intelligence-tz.md — client ТЗ (goals, phased scope, FR-1..FR-22, NFRs,
  acceptance criteria, fixed assumptions, risk allocation, staged timeline)
- SPEC (2):
  - docs/polymer-intelligence-dev-spec.md — developer implementation spec (repo, pipeline,
    services + REST API, Telegram layer, reports, frontend, deploy, epics E1-E10)
  - docs/polymer-intelligence-db-architecture.md — PostgreSQL 16 schema DDL (v1.1)
- DOC (1): docs/polymer-intelligence-ui-mockups.md — UI/design system + 3 frontend surfaces

All 4 classifications were high-confidence; none UNKNOWN/low.

## Cross-ref graph

DAG, no cycles. Edges (doc-to-doc): tz→db; dev-spec→tz, dev-spec→db; ui→db, ui→dev-spec.
db-architecture is a sink. Max depth 2 (cap 50). Non-doc cross-refs (jpeg images, extraction-schema.json,
runbook.md, deploy/*) noted but not part of synthesis.

## Decisions

- Source type with formal LOCKED status (ADR): 0. No ADR-typed documents in the set.
- Recorded technical decisions (SPEC-precedence, PRD wins on any "what" conflict): 18
  See .planning/intel/decisions.md (DEC-stack-backend, DEC-postgres-16, DEC-userbot-separate-process,
  DEC-bot-webhook-no-separate-container, DEC-raw-immutable, DEC-single-signal-stream, DEC-llm-models,
  DEC-llm-budget-degradation, DEC-source-adapter-registry, DEC-test-before-enable,
  DEC-human-in-the-loop-reports, DEC-file-storage, DEC-realtime-sse-not-websocket, DEC-auth-split,
  DEC-tz-handling, DEC-deploy-single-vps, ...).
- The DB doc records a concrete, fixed PostgreSQL 16 schema (DDL) treated as a hard schema contract.

## Requirements

- Extracted from the single PRD: 21 functional (FR-1..FR-22; FR-21 captured both as a requirement
  and a decision) + 2 Phase-2 scope items (counterparty-linking, intraday-channel-alerts)
  + 5 NFR groups.
- IDs (FR → REQ slug):
  REQ-uzex-parser (FR-1), REQ-telegram-monitoring (FR-2), REQ-international-feed (FR-3),
  REQ-fx-rates (FR-4), REQ-webapp-auth (FR-5), REQ-request-wizard (FR-6), REQ-my-requests (FR-7),
  REQ-webapp-news (FR-8), REQ-webapp-i18n (FR-9), REQ-live-feed (FR-10), REQ-purchase-requests (FR-11),
  REQ-price-trends (FR-12), REQ-sources-health (FR-13), REQ-alerts (FR-14), REQ-roles (FR-15),
  REQ-bot-team (FR-16), REQ-bot-clients (FR-17), REQ-reports (FR-18), REQ-ai-extraction (FR-19),
  REQ-lead-scoring (FR-20), REQ-llm-budget (FR-21), REQ-source-builder (FR-22),
  REQ-counterparty-linking, REQ-intraday-channel-alerts;
  NFRs: REQ-nfr-performance, REQ-nfr-reliability, REQ-nfr-security, REQ-nfr-observability,
  REQ-nfr-time-localization.
- Phase split preserved (P1 = MVP / domestic, P2 = content + international loop).
- No competing acceptance variants (single PRD).
- See .planning/intel/requirements.md.

## Constraints

- 16 constraint blocks. Type breakdown:
  - schema (3): C-schema-postgres16, C-schema-not-in-phase1, C-schema-open-questions
  - protocol (7): C-pipeline-rules, C-uzex-collector, C-userbot-protocol, C-llm-extract-schema,
    C-alert-engine, C-celery-schedule, C-report-pipeline (+ C-services-layer)
  - api-contract (2): C-source-adapters, C-rest-api
  - nfr (3): C-frontend, C-deploy-ops, C-testing
  - (C-services-layer tagged protocol, included above)
- See .planning/intel/constraints.md.

## Context topics

- 10 topics: project intent, design system, Surface A (landing), Surface B (dashboard),
  Surface C (Web App), screen→data mapping, design-derived planning constraints,
  fixed assumptions/scope boundaries, timeline & risk allocation, deliverables.
- See .planning/intel/context.md.

## Conflicts

- 0 blockers
- 0 competing variants
- 3 info (auto-resolved / reconciled): file-storage clarification (dev-spec refines PRD assumption,
  not a contradiction); landing paid-source strip (marketing-only, reconciled in DOC itself);
  SPEC concrete LLM/report specifics elaborating PRD.
- Detail: .planning/INGEST-CONFLICTS.md

## Pointers

- Decisions:    .planning/intel/decisions.md
- Requirements: .planning/intel/requirements.md
- Constraints:  .planning/intel/constraints.md
- Context:      .planning/intel/context.md
- Conflicts:    .planning/INGEST-CONFLICTS.md

STATUS: READY — no blockers, no competing variants. Safe to route to gsd-roadmapper.
