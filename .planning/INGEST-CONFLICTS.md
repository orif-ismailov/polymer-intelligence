## Conflict Detection Report

Mode: new (net-new bootstrap, no existing .planning artifacts to compare against)
Precedence: ADR > SPEC > PRD > DOC (no per-doc overrides; no ADR-typed docs present)
Docs in set: 4 (1 PRD, 2 SPEC, 1 DOC)
Cross-ref cycle check: PASS (DAG; db-architecture is a sink; max depth 2, well under cap 50)

### BLOCKERS (0)

None. No LOCKED-vs-LOCKED ADR contradictions (no ADR-typed docs), no UNKNOWN/low-confidence
classifications, no cross-ref cycles, and no contradiction of any existing locked decision
(none exist in new mode).

### WARNINGS (0)

None. Only one PRD is present, so there are no competing acceptance-criteria variants across PRDs.
Each FR maps to a single requirement with a single acceptance variant.

### INFO (3)

[INFO] Auto-resolved: SPEC clarifies PRD on request-file storage (no contradiction)
  Found: docs/polymer-intelligence-tz.md assumption 2.3.2 states files stored as telegram_file_id,
    downloaded to storage on first manager open.
  Note: docs/polymer-intelligence-dev-spec.md §4.2 refines this to direct upload to S3-compatible
    storage (MinIO bundled), with telegram_file_id as the fallback for files sent to the bot.
    docs/polymer-intelligence-db-architecture.md explicitly records this as RESOLVED (open question
    #1, v1.1) and the schema already carries request_files.storage_path. The dev-spec frames it as
    a clarification ("Уточнение к допущению 2.3.2"), and per the dev-spec's own deference clause the
    PRD wins only on genuine conflict — this is an additive refinement, not a contradiction.
    Synthesized as DEC-file-storage with primary = direct upload, fallback = telegram_file_id.

[INFO] Reconciled: landing "Sources we monitor" lists paid sources that are out of scope as inputs
  Found: docs/polymer-intelligence-ui-mockups.md §2 landing strip lists ChemOrbis, Polymerupdate,
    Argus, Platts, ETS Kazakhstan, Petkim alongside UZEX.
  Note: docs/polymer-intelligence-tz.md §2.3.5 puts paid international sources (ChemOrbis, Argus,
    Platts, Polymerupdate, ETS) fully out of scope as data inputs. The UI doc itself reconciles
    this in §2 — those logos are brand/marketing coverage claims only; actual Phase-1 ingestion is
    UZEX + Telegram + free indices (SunSirs, DCE). DOC is lowest precedence and the doc agrees with
    the PRD on the substantive point, so no override needed. Recorded in context.md.

[INFO] SPEC sets concrete LLM model + report-validation specifics atop PRD's abstract requirements
  Found: docs/polymer-intelligence-tz.md FR-19/FR-20/FR-21 specify extraction, scoring, and a token
    budget abstractly (model "класса Haiku" for extraction, "класса Sonnet" for reports).
  Note: docs/polymer-intelligence-dev-spec.md §2.3/§5 pins concrete values (claude-haiku-4-5,
    configurable via LLM_EXTRACT_MODEL/LLM_REPORT_MODEL; confidence<0.5 → needs_review; strict
    JSON schema; report number-validation against data_snapshot). These elaborate, not contradict,
    the PRD; SPEC is the appropriate precedence layer for the "how". Captured in decisions.md
    (DEC-llm-models, DEC-llm-budget-degradation) and constraints.md (C-llm-extract-schema,
    C-report-pipeline).
