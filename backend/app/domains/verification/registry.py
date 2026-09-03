"""State-registry snapshots (R6 / P7.c — T4.3).

Writes and reads `registry_snapshots`. The whole service exists to keep one
property true: **a snapshot is written once and never edited.** There is no
update function here, and there is no "current registry state" column anywhere —
`latest()` reads the newest row. Re-checking a company appends history rather
than replacing an answer, which is what makes the difference between "the
registry said X in June" and "an operator transcribed Y in July" survive.

Two writers, one shape:

  * `record_snapshot(source='manual', created_by=…)` — the operator path, which
    is the one that works today: staff read an open service (my.soliq.uz for the
    VAT register, license.gov.uz for licences) and record what they saw with a
    screenshot. INTEGRATIONS.md §3 sanctions this as the pre-ПЦД bridge.
  * `fetch_and_record()` — the live path, which returns `None` when the registry
    is unreachable. Not an exception, and emphatically not an empty snapshot: an
    empty `CompanySnapshot` reads as "no such company", turning our missing
    integration into a verification finding about a real business. The check then
    lands as `unavailable` and the manual path stays open (the R1 degradation
    invariant).

Service axiom (DEC-dep-owns-commit): flush only — the router/task owns the commit.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.domains.companies.models import Company
from app.domains.verification.registry_models import (
    SNAPSHOT_KIND_COMPANY,
    SNAPSHOT_KIND_LICENSES,
    SNAPSHOT_KIND_VAT,
    SNAPSHOT_KINDS,
    SNAPSHOT_SOURCE_MANUAL,
    SNAPSHOT_SOURCE_REGISTRY,
    SNAPSHOT_SOURCES,
    RegistrySnapshot,
)
from app.integrations import gov_registry
from app.services import audit_service

logger = logging.getLogger(__name__)

#: Provider recorded for the operator path. Kept distinct from any real registry
#: name so a transcription can never be mistaken for an API answer.
PROVIDER_MANUAL = "manual"


class UnknownSnapshotKind(Exception):
    """Not one of the three registry lookups."""


class UnknownSnapshotSource(Exception):
    """Not `registry` or `manual`."""


def record_snapshot(
    db: Session,
    company: Company,
    *,
    kind: str,
    source: str,
    provider: str,
    payload: dict[str, object],
    raw_status: str | None = None,
    evidence_path: str | None = None,
    evidence_sha256: str | None = None,
    note: str | None = None,
    created_by: int | None = None,
    fetched_at: datetime.datetime | None = None,
) -> RegistrySnapshot:
    """Append one immutable observation about a company.

    `kind`/`source` are validated here as well as by the table's CHECKs: the
    constraint is the backstop, the typed error is the message an operator reads.

    `fetched_at` defaults to now but is caller-supplied on purpose — an operator
    may be transcribing a page they read yesterday, and when the observation was
    MADE is a different fact from when we wrote it down.
    """
    if kind not in SNAPSHOT_KINDS:
        raise UnknownSnapshotKind(kind)
    if source not in SNAPSHOT_SOURCES:
        raise UnknownSnapshotSource(source)

    snapshot = RegistrySnapshot(
        company_id=company.id,
        kind=kind,
        source=source,
        provider=provider,
        payload=payload,
        raw_status=raw_status,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        note=note,
        created_by=created_by,
        fetched_at=fetched_at or utcnow(),
    )
    db.add(snapshot)
    db.flush()

    audit_service.write_audit(
        db,
        created_by,
        "registry.snapshot",
        "registry_snapshots",
        str(snapshot.id),
        {
            "company_id": company.id,
            "kind": kind,
            "source": source,
            "provider": provider,
            "has_evidence": evidence_path is not None,
        },
    )
    logger.info(
        "registry_service.snapshot",
        extra={"company_id": company.id, "kind": kind, "source": source},
    )
    return snapshot


def latest(db: Session, company_id: int, kind: str) -> RegistrySnapshot | None:
    """The newest snapshot of `kind` for a company, or None if never checked.

    The only read path, and the reason for the `(company_id, kind, id)` index.
    """
    return db.execute(
        select(RegistrySnapshot)
        .where(RegistrySnapshot.company_id == company_id, RegistrySnapshot.kind == kind)
        .order_by(RegistrySnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def all_latest(db: Session, company_id: int) -> dict[str, RegistrySnapshot]:
    """The newest snapshot of each kind — what the case page shows."""
    found: dict[str, RegistrySnapshot] = {}
    for kind in SNAPSHOT_KINDS:
        snapshot = latest(db, company_id, kind)
        if snapshot is not None:
            found[kind] = snapshot
    return found


def fetch_and_record(db: Session, company: Company, kind: str) -> RegistrySnapshot | None:
    """Ask the configured registry and store the answer. None when unreachable.

    Returning None rather than raising is the degradation invariant: a registry
    we cannot reach must leave the manual verification path completely intact.
    """
    if kind not in SNAPSHOT_KINDS:
        raise UnknownSnapshotKind(kind)

    try:
        client = gov_registry.get_gov_registry_client(db)
        payload, raw_status = _lookup(client, kind, company.tax_id)
    except gov_registry.ProviderUnavailable as exc:
        logger.info(
            "registry_service.unavailable",
            extra={"company_id": company.id, "kind": kind, "reason": str(exc)},
        )
        return None

    return record_snapshot(
        db,
        company,
        kind=kind,
        source=SNAPSHOT_SOURCE_REGISTRY,
        provider=str(gov_registry.current_mode()),
        payload=payload,
        raw_status=raw_status,
    )


def _lookup(
    client: gov_registry.GovRegistryClient, kind: str, inn: str
) -> tuple[dict[str, object], str | None]:
    """Dispatch to the right lookup and normalize it into a payload."""
    if kind == SNAPSHOT_KIND_COMPANY:
        snapshot = client.lookup_company(inn)
        return snapshot.as_payload(), snapshot.raw_status
    if kind == SNAPSHOT_KIND_LICENSES:
        items = client.lookup_licenses(inn)
        return gov_registry.licenses_payload(items), None
    if kind == SNAPSHOT_KIND_VAT:
        vat = client.lookup_vat(inn)
        return vat.as_payload(), vat.raw_status
    raise UnknownSnapshotKind(kind)  # pragma: no cover — guarded by the caller


__all__ = [
    "PROVIDER_MANUAL",
    "SNAPSHOT_KIND_COMPANY",
    "SNAPSHOT_KIND_LICENSES",
    "SNAPSHOT_KIND_VAT",
    "SNAPSHOT_KINDS",
    "SNAPSHOT_SOURCE_MANUAL",
    "SNAPSHOT_SOURCE_REGISTRY",
    "UnknownSnapshotKind",
    "UnknownSnapshotSource",
    "all_latest",
    "fetch_and_record",
    "latest",
    "record_snapshot",
]
