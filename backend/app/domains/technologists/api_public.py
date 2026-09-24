"""Anonymous technologist catalog (/api/v1/public/technologists).

Server-rendered on the storefront, so every route answers a stranger — no
`get_current_account` anywhere, by design. What keeps that safe is that every
response is built by `profiles.public_card` from the APPROVED snapshot: an
unlisted expert 404s, a pending edit is invisible, and contacts are not in the
model at all.

Literal `/facets` is declared before `/{profile_id}` (FastAPI resolves
first-registered); `test_portal_technologists_api` pins the order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api import errors
from app.core.db import get_db
from app.domains.technologists import catalog, profiles
from app.domains.technologists.models import TechnologistProfile
from app.domains.technologists.schemas import (
    FacetsOut,
    TechnologistCardListOut,
    TechnologistCardOut,
)

router = APIRouter(prefix="/public/technologists", tags=["public-technologists"])


@router.get("", response_model=TechnologistCardListOut, summary="The technologist catalog")
def list_technologists(
    process: str | None = Query(default=None, max_length=40),
    material: str | None = Query(default=None, max_length=20),
    language: str | None = Query(default=None, max_length=5),
    country: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TechnologistCardListOut:
    rows, total = profiles.list_published(
        db,
        process=process,
        material=material,
        language=language,
        country=country,
        q=q,
        limit=limit,
        offset=offset,
    )
    return TechnologistCardListOut(items=[profiles.public_card(p) for p in rows], total=total)


@router.get("/facets", response_model=FacetsOut, summary="The closed vocabularies")
def get_facets() -> FacetsOut:
    return FacetsOut(**catalog.facets())


def _listed_or_404(db: Session, profile_id: int) -> TechnologistProfile:
    try:
        return profiles.get_listed(db, profile_id)
    except profiles.ProfileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc


@router.get(
    "/{profile_id}",
    response_model=TechnologistCardOut,
    summary="One technologist's public card",
    responses=errors.NOT_FOUND,
)
def get_technologist(profile_id: int, db: Session = Depends(get_db)) -> TechnologistCardOut:
    return profiles.public_card(_listed_or_404(db, profile_id))


@router.get(
    "/{profile_id}/photo",
    summary="Stream the approved portrait (public — for <img> tags)",
    responses=errors.NOT_FOUND,
)
def get_photo(profile_id: int, db: Session = Depends(get_db)) -> Response:
    """Byte-proxied like company logos: a presigned S3 URL names the INTERNAL
    endpoint no browser can resolve. The key comes from the approved snapshot,
    never from the caller, so this cannot be walked to other objects."""
    profile = _listed_or_404(db, profile_id)
    key = (profile.published_snapshot or {}).get("photo_key")
    if not isinstance(key, str) or not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _stream(key)


def _stream(key: str) -> Response:
    from app.services import storage_service  # noqa: PLC0415

    body = storage_service.get_object_bytes(key)
    media_type = "image/png" if key.endswith(".png") else "image/jpeg"
    return Response(content=body, media_type=media_type, headers={"Cache-Control": "public, max-age=300"})
