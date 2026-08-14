"""Substance registry seed (R5 / P5 — T2.1).

Digitizes the official Uzbek lists into `substances`. There is no
machine-readable state registry (INTEGRATIONS.md §4), so this seed — not an
external API — is how regulated chemistry gets into the platform.

WARNING — the shipped revision is `v1-provisional` and is DELIBERATELY
INCOMPLETE. It carries only the entries confirmed by the legal map in
`.planning/deal-lifecycle/INTEGRATIONS.md` §4: the free polymers, plastic waste
under ПКМ-916, the Список IV precursors named there with their thresholds, and
one prohibited POP. The full appendices (all 29 Список IV positions, ПКМ-818,
ПКМ-782 categories, the three ПКМ-916 lists) are not served programmatically by
lex.uz and their current wording has to be checked by a lawyer — an operator
prerequisite. That check produces `substances_v2.json`, not an edit of this file.
Until it happens, treat a substance absent from the registry as UNKNOWN, not as
unregulated: the publish gate ships off (`dangerous_check_enforced=false`).

Idempotency has three cases, keyed on `code`:
  * no row            → insert, stamped with this revision;
  * row from an OLDER revision → update (a corrected threshold must reach prod);
  * row with `seed_revision IS NULL` → skip. NULL means an operator edited it in
    the admin panel, and silently undoing their correction on the next deploy
    would make the panel untrustworthy.

Usage:
    python -m app.seed.seed_substances
"""

from __future__ import annotations

import decimal
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.domains.compliance.models import Substance
from app.models.enums import RegulationLevel, RegulationRegime

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_DATA_FILE = _DATA_DIR / "substances_v1.json"

#: Bump together with a new data file. Stamped onto every row the seed owns.
REVISION = "v1-provisional"


@dataclass(frozen=True)
class SeedOutcome:
    """What one seed run changed (codes, so a log line is readable)."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _decimal(value: object) -> decimal.Decimal | None:
    return None if value is None else decimal.Decimal(str(value))


def _apply(row: Substance, entry: dict[str, Any], revision: str) -> None:
    row.name_ru = entry["name_ru"]
    row.name_uz = entry.get("name_uz")
    row.name_en = entry.get("name_en")
    row.hs_code = entry["hs_code"]
    row.cas = entry.get("cas")
    row.hazard_class = entry.get("hazard_class")
    row.regulation_level = RegulationLevel(entry.get("regulation_level", "free"))
    regime = entry.get("regulation_regime")
    row.regulation_regime = RegulationRegime(regime) if regime else None
    row.threshold_concentration_pct = _decimal(entry.get("threshold_concentration_pct"))
    row.exemption_annual_limit = _decimal(entry.get("exemption_annual_limit"))
    row.exemption_unit = entry.get("exemption_unit")
    row.license_category = entry.get("license_category")
    row.required_docs = list(entry.get("required_docs", []))
    row.synonyms = list(entry.get("synonyms", []))
    row.source_act = entry.get("source_act")
    row.seed_revision = revision


def load_revision(path: Path | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Read the data file; returns (revision, entries)."""
    payload = json.loads((path or _DATA_FILE).read_text(encoding="utf-8"))
    return str(payload["revision"]), list(payload["substances"])


def seed_substances(db: Session | None = None, *, path: Path | None = None) -> SeedOutcome:
    """Seed/refresh the substance registry (idempotent). Commits when it owns the session."""
    own = db is None
    session = db or SessionLocal()
    revision, entries = load_revision(path)
    outcome = SeedOutcome()
    try:
        existing = {row.code: row for row in session.query(Substance).all()}
        for entry in entries:
            code = entry["code"]
            row = existing.get(code)
            if row is None:
                row = Substance(code=code, name_ru=entry["name_ru"], hs_code=entry["hs_code"])
                _apply(row, entry, revision)
                session.add(row)
                outcome.created.append(code)
            elif row.seed_revision is None:
                # Operator-owned row — hands off.
                outcome.skipped.append(code)
            elif row.seed_revision != revision:
                _apply(row, entry, revision)
                outcome.updated.append(code)
            else:
                outcome.skipped.append(code)
        session.flush()
        if own:
            session.commit()
    finally:
        if own:
            session.close()
    logger.info(
        "seed_substances",
        extra={
            "revision": revision,
            "created": len(outcome.created),
            "updated": len(outcome.updated),
            "skipped": len(outcome.skipped),
        },
    )
    return outcome


if __name__ == "__main__":  # pragma: no cover
    result = seed_substances()
    print(  # noqa: T201
        f"seed_substances ({REVISION}): created {len(result.created)}, "
        f"updated {len(result.updated)}, skipped {len(result.skipped)}"
    )
