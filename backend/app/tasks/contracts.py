"""Contract hardening beat tasks (R3 Stage B — TB4.1/TB4.2).

`verify_contract_integrity` (nightly) recomputes the sha256 of every active
contract's stored PDF and alerts the admin channel on any mismatch (tamper
detection). `expire_stale_contracts` (nightly) expires contracts that have sat in
`pending_counterparty`/`pending_signatures` longer than `contract_pending_ttl_days`
and notifies both parties. Both run on the `default` queue and never raise.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="verify_contract_integrity")  # type: ignore[untyped-decorator]
def verify_contract_integrity() -> dict[str, Any]:
    """Recompute stored-PDF sha256 vs document_sha256 for active contracts; alert on drift."""
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.services import audit_service, storage_service  # noqa: PLC0415

    checked = 0
    mismatches: list[int] = []
    with SessionLocal() as db:
        contracts = (
            db.query(Contract)
            .filter(
                Contract.status == ContractStatus.active,
                Contract.generated_document_path.isnot(None),
                Contract.document_sha256.isnot(None),
            )
            .all()
        )
        for contract in contracts:
            checked += 1
            try:
                pdf = storage_service.get_object_bytes(contract.generated_document_path)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001 — a missing/unreadable object is itself a finding
                mismatches.append(contract.id)
                logger.error(
                    "contract.integrity.unreadable",
                    extra={"contract_id": contract.id, "error": str(exc)},
                )
                continue
            if not contract_service.document_matches_hash(contract, pdf):
                mismatches.append(contract.id)
                audit_service.write_audit(
                    db, None, "contract.integrity_mismatch", "contracts", str(contract.id),
                    {"expected_sha256": contract.document_sha256},
                )
                logger.error("contract.integrity.mismatch", extra={"contract_id": contract.id})
        if mismatches:
            db.commit()

    if mismatches:
        _alert_integrity(mismatches)
    logger.info("contract.integrity.done", extra={"checked": checked, "mismatches": len(mismatches)})
    return {"checked": checked, "mismatches": mismatches}


def _alert_integrity(contract_ids: list[int]) -> None:
    """Best-effort admin-channel alert on integrity drift (never raises)."""
    from app.core.config import settings  # noqa: PLC0415

    chat_id = settings.VERIFICATION_NOTIFY_CHAT_ID or settings.REQUEST_NOTIFY_CHAT_ID
    if chat_id is None:
        return
    try:
        import asyncio  # noqa: PLC0415

        from telegram.bot import bot  # noqa: PLC0415

        text = "⚠️ Нарушена целостность договоров (sha256 mismatch): " + ", ".join(
            str(i) for i in contract_ids
        )
        asyncio.run(bot.send_message(chat_id=chat_id, text=text[:4096]))
    except Exception as exc:  # noqa: BLE001
        logger.error("contract.integrity.alert_failed", extra={"error": str(exc)})


@celery_app.task(name="expire_stale_contracts")  # type: ignore[untyped-decorator]
def expire_stale_contracts() -> dict[str, Any]:
    """Expire pending contracts inactive longer than contract_pending_ttl_days."""
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.services import settings_service  # noqa: PLC0415

    expired: list[int] = []
    with SessionLocal() as db:
        ttl_days = int(settings_service.get(db, "contract_pending_ttl_days"))  # type: ignore[arg-type]
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=ttl_days)
        stale = (
            db.query(Contract)
            .filter(
                Contract.status.in_(
                    [ContractStatus.pending_counterparty, ContractStatus.pending_signatures]
                ),
                Contract.updated_at < cutoff,
            )
            .all()
        )
        for contract in stale:
            contract_service.expire(db, contract)
            expired.append(contract.id)
        if expired:
            db.commit()

    logger.info("contract.expire.done", extra={"expired": len(expired)})
    return {"expired": expired}
