"""Portal E-IMZO challenge + verify endpoints (R3 Stage A — TA1.4). Under /api/v1.

Company-scoped (membership resolved via `company_service.get_company_for` → 404 for
non-members). `challenge` mints a single-use nonce; `verify` consumes it, verifies
the PKCS#7 through the gateway sidecar, and applies the identity effects. Typed
error mapping keeps the frontend able to offer the manual path on a sidecar outage
(503) and clear guidance on mismatch (422) / expiry (400).
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.contracts import eimzo as eimzo_service
from app.domains.contracts.eimzo_schemas import ChallengeOut, VerifyIn, VerifyOut
from app.domains.verification.api_portal import case_out
from app.integrations.eimzo import ProviderUnavailable

router = APIRouter(prefix="/portal/companies", tags=["portal-eimzo"])


@router.post("/{company_id}/eimzo/challenge", response_model=ChallengeOut)
def eimzo_challenge(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> ChallengeOut:
    company = company_or_404(db, account, company_id)
    challenge = eimzo_service.issue_challenge(redis_client, company.id, account.id)
    return ChallengeOut(challenge=challenge)


@router.post("/{company_id}/eimzo/verify", response_model=VerifyOut)
def eimzo_verify(
    company_id: int,
    body: VerifyIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> VerifyOut:
    company = company_or_404(db, account, company_id)
    try:
        outcome = eimzo_service.verify(db, redis_client, company, account, body.pkcs7)
    except eimzo_service.ChallengeExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="challenge_expired"
        ) from exc
    except eimzo_service.CertCompanyMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "cert_company_mismatch",
                "cert_inn": exc.cert_inn_masked,
                "company_inn": exc.company_inn_masked,
            },
        ) from exc
    except company_service.CompanyAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="company_already_registered"
        ) from exc
    except ProviderUnavailable as exc:
        # Sidecar down → 503; the frontend falls back to the manual verification path.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="eimzo_unavailable"
        ) from exc
    db.commit()
    case_payload = case_out(db, outcome.case)
    if case_payload is None:  # pragma: no cover — outcome.case is always present here
        raise RuntimeError("case_out returned None for a verified case")
    return VerifyOut(
        ok=outcome.ok,
        reason=outcome.reason,
        holder_masked=outcome.holder_masked,
        case=case_payload,
    )
