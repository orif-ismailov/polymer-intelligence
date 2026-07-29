"""
Offer compliance verdicts and the publish gate (P5 W3 — T3.1/T3.3, FR-C4/C6).

`decide()` is the entire ruleset as a pure function so it can be read (and
tested) as a table; `evaluate()` is the part that goes to the database to find
the substance, the offer's documents and the company's licence.

Three decisions worth knowing before changing anything here:

1. **The gate holds an offer as a DRAFT; it does not reject the request.**
   A `docs_required` substance can only receive its documents after the offer
   row exists (files are uploaded against an offer id), so refusing creation
   would make such an offer impossible to publish at all. A held offer never
   enters the moderation queue, and attaching the missing document releases it.
2. **`prohibited` is not paperwork.** No document, licence or concentration
   unblocks it — the ПКМ-916 lists are bans.
3. **An undeclared concentration counts as regulated.** Otherwise leaving the
   field empty is the way past the gate.

Enforcement itself is the runtime setting `dangerous_check_enforced`, shipped
OFF: the registry is provisional until the lists are legally reviewed, and
blocking trade on an incomplete registry is worse than not blocking yet. With
the gate off the verdict is still computed and cached, so staff can see exactly
what would be blocked before flipping it.

Service axiom (DEC-dep-owns-commit): flush only — the caller owns the commit.
"""

from __future__ import annotations

import decimal
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.compliance import Substance
from app.models.enums import RegulationLevel, RegulationRegime
from app.models.marketplace import SellerOffer
from app.schemas.compliance import ComplianceOut, MissingOut
from app.schemas.substance import SubstanceBrief
from app.services import company_license_service, settings_service, substance_service

logger = logging.getLogger(__name__)

#: Kinds of thing that can be missing. Kept as plain strings: they are cached in
#: JSONB on the offer and rendered by two frontends.
MISSING_DOCUMENT = "document"
MISSING_LICENSE = "license"
MISSING_PROHIBITED = "prohibited"

EXEMPT_BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class Missing:
    """One thing standing between this offer and publication."""

    kind: str
    detail: str | None = None


@dataclass(frozen=True)
class ComplianceVerdict:
    """What publishing this offer would require right now."""

    level: RegulationLevel
    ok: bool
    missing: tuple[Missing, ...] = ()
    substance_id: int | None = None
    regime: RegulationRegime | None = None
    #: Why a regulated substance came out free — currently only a declared
    #: concentration below the substance's threshold.
    exempt_reason: str | None = None

    def as_json(self) -> list[dict[str, str | None]]:
        """The cached (JSONB) shape — part of the API contract, not a debug dump."""
        return [{"kind": m.kind, "detail": m.detail} for m in self.missing]


class CompliancePublishBlocked(Exception):
    """Publishing this offer is not allowed while the gate is on."""

    def __init__(self, verdict: ComplianceVerdict) -> None:
        super().__init__(f"compliance blocked: level={verdict.level}")
        self.verdict = verdict


def decide(
    *,
    level: RegulationLevel,
    regime: RegulationRegime | None,
    required_docs: Sequence[str],
    threshold_concentration_pct: decimal.Decimal | None,
    declared_concentration_pct: decimal.Decimal | None,
    attached_doc_kinds: Iterable[str],
    has_license: bool,
    source_act: str | None = None,
    substance_id: int | None = None,
) -> ComplianceVerdict:
    """The ruleset. Pure — every input is already resolved by the caller."""
    if level == RegulationLevel.prohibited:
        # First and unconditional: a ban is not satisfiable.
        return ComplianceVerdict(
            level=level,
            ok=False,
            missing=(Missing(MISSING_PROHIBITED, source_act),),
            substance_id=substance_id,
            regime=regime,
        )

    # Concentration decides whether the regime applies at all. Список IV catches
    # acetone at ≥60%; below that it is an ordinary solvent. A missing
    # declaration is NOT an exemption.
    if (
        threshold_concentration_pct is not None
        and declared_concentration_pct is not None
        and declared_concentration_pct < threshold_concentration_pct
    ):
        return ComplianceVerdict(
            level=RegulationLevel.free,
            ok=True,
            substance_id=substance_id,
            regime=regime,
            exempt_reason=EXEMPT_BELOW_THRESHOLD,
        )

    if level == RegulationLevel.free:
        return ComplianceVerdict(
            level=level, ok=True, substance_id=substance_id, regime=regime
        )

    missing: list[Missing] = []
    attached = set(attached_doc_kinds)
    # Documents and licences are independent requirements: a substance can name
    # both, and an SDS is not a licence.
    missing.extend(
        Missing(MISSING_DOCUMENT, kind) for kind in required_docs if kind not in attached
    )
    if level == RegulationLevel.license_required and not has_license:
        missing.append(Missing(MISSING_LICENSE, str(regime) if regime else None))

    return ComplianceVerdict(
        level=level,
        ok=not missing,
        missing=tuple(missing),
        substance_id=substance_id,
        regime=regime,
    )


def substance_for(db: Session, offer: SellerOffer) -> Substance | None:
    """The registry row this offer is about, if any.

    An explicit link wins; otherwise a hand-typed CAS/HS is resolved (FR-C2 lets
    a seller type an identifier for something they think we do not carry — and
    quite often we do). A deactivated substance still counts: retiring a list
    entry must not silently unblock the offers it was blocking.
    """
    if offer.substance_id is not None:
        return db.get(Substance, offer.substance_id)
    if offer.cas_number or offer.hs_code:
        return substance_service.resolve(db, cas=offer.cas_number, hs_code=offer.hs_code)
    return None


def evaluate(db: Session, offer: SellerOffer) -> ComplianceVerdict:
    """Compute the verdict for one offer. Read-only."""
    substance = substance_for(db, offer)
    if substance is None:
        return ComplianceVerdict(level=RegulationLevel.free, ok=True)

    has_license = False
    if (
        substance.regulation_level == RegulationLevel.license_required
        and substance.regulation_regime is not None
        and offer.company_id is not None
    ):
        # A Telegram-origin offer has no portal company, so there is nobody who
        # could hold a licence — it stays blocked rather than passing by default.
        has_license = (
            company_license_service.active_for(
                db,
                offer.company_id,
                substance.regulation_regime,
                category=substance.license_category,
            )
            is not None
        )

    return decide(
        level=substance.regulation_level,
        regime=substance.regulation_regime,
        required_docs=list(substance.required_docs or []),
        threshold_concentration_pct=substance.threshold_concentration_pct,
        declared_concentration_pct=offer.declared_concentration_pct,
        attached_doc_kinds=[str(f.kind) for f in offer.files],
        has_license=has_license,
        source_act=substance.source_act,
        substance_id=substance.id,
    )


def evaluate_and_stamp(db: Session, offer: SellerOffer) -> ComplianceVerdict:
    """Evaluate and cache the verdict on the offer (FR-C6). Does NOT commit."""
    verdict = evaluate(db, offer)
    offer.compliance_level = verdict.level
    offer.compliance_ok = verdict.ok
    offer.compliance_missing = verdict.as_json()
    offer.compliance_checked_at = utcnow()
    db.flush()
    return verdict


def verdict_out(db: Session, offer: SellerOffer) -> ComplianceOut:
    """The verdict as the API shape shared by the seller panel and moderation.

    Evaluated live rather than read from the cache: a licence can expire between
    a seller submitting an offer and a moderator opening the card, and the card
    is where the decision to publish is made.
    """
    verdict = evaluate(db, offer)
    substance = substance_for(db, offer)
    return ComplianceOut(
        ok=verdict.ok,
        level=verdict.level,
        regime=verdict.regime,
        exempt_reason=verdict.exempt_reason,
        missing=[MissingOut(kind=m.kind, detail=m.detail) for m in verdict.missing],
        substance=SubstanceBrief.model_validate(substance) if substance else None,
        enforced=enforcement_enabled(db),
        checked_at=offer.compliance_checked_at,
    )


def enforcement_enabled(db: Session) -> bool:
    """Whether a failing verdict actually blocks (runtime setting, default off)."""
    return bool(settings_service.get(db, "dangerous_check_enforced"))


def assert_publishable(db: Session, offer: SellerOffer) -> ComplianceVerdict:
    """Re-evaluate at the moment of publication; raise when the gate says no.

    Used by moderation approval: a licence can expire between a seller
    submitting an offer and staff approving it.
    """
    verdict = evaluate_and_stamp(db, offer)
    if not verdict.ok and enforcement_enabled(db):
        logger.info(
            "compliance.blocked",
            extra={"offer_id": offer.id, "level": str(verdict.level)},
        )
        raise CompliancePublishBlocked(verdict)
    return verdict
