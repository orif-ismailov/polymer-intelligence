"""
/webapp/me — GET client profile, PATCH language/name update.

Authentication via get_current_client (initData HMAC from 03-01).

Language is restricted to 'ru' or 'uz' — validated in the ClientProfilePatch
schema (REQ-webapp-i18n).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.requests import Client
from app.schemas.webapp import ClientProfileOut, ClientProfilePatch

router = APIRouter(prefix="/webapp", tags=["webapp"])


@router.get(
    "/me",
    response_model=ClientProfileOut,
    summary="Get authenticated client profile",
)
def get_me(
    client: Client = Depends(get_current_client),
) -> ClientProfileOut:
    """GET /webapp/me — return the authenticated client's profile.

    Identity comes from verified initData (get_current_client dep).

    Raises:
        HTTP 401: missing or invalid X-Telegram-Init-Data.
    """
    return ClientProfileOut(
        id=client.id,
        language=client.language,
        company_name=client.company_name,
        contact_name=client.contact_name,
    )


@router.patch(
    "/me",
    response_model=ClientProfileOut,
    summary="Update authenticated client profile (language, name)",
)
def patch_me(
    body: ClientProfilePatch,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> ClientProfileOut:
    """PATCH /webapp/me — update language and/or name for the calling client.

    Only language (restricted to 'ru'|'uz'), company_name, and contact_name
    are updatable. REQ-webapp-i18n.

    Raises:
        HTTP 401: missing or invalid X-Telegram-Init-Data.
        HTTP 422: language not in {'ru', 'uz'} (validated by ClientProfilePatch).
    """
    if body.language is not None:
        client.language = body.language
    if body.company_name is not None:
        client.company_name = body.company_name
    if body.contact_name is not None:
        client.contact_name = body.contact_name

    db.commit()

    return ClientProfileOut(
        id=client.id,
        language=client.language,
        company_name=client.company_name,
        contact_name=client.contact_name,
    )
