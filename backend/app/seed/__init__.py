"""
Reference seed scripts for Polymer Intelligence.

Seed scripts populate the reference tables on a clean database and are
idempotent — running them multiple times creates no duplicates.

Usage:
    python -m app.seed.seed_reference

Seed scope (dev-spec §9, E1):
- products: polymer product types (PP, HDPE, LDPE, etc.)
- product_grades: UZ-producer grades (Shurtan GCC, Uz-Kor)
- synonyms: product relevance synonyms dictionary for the UZEX relevance filter
  (stored in a separate synonyms table; see note below)

Synonyms storage note (per schema contract): the locked DDL v1.1 does not define
a separate synonyms table. Per dev-spec §2.1, synonyms are used by the UZEX
relevance filter as a lookup dictionary. This seed stores them in a dedicated
`product_synonyms` table created by migration 0002 (future plan), or as a
config artifact. For Phase 1, the synonyms JSON is loaded and stored as a
products association (many synonyms → one product_id). Plan 01-02 notes that
"store in a synonyms table if one exists in the schema" — since it does not
exist yet, synonyms.json is stored as-is in the seed data directory for Phase-2
migration to pick up. The seed_reference.py function logs the synonyms dictionary
count without DB write so the data is ready when the table is created.

WARNING: Do not invent new tables without a migration (Rule 4 — architecture).
"""
