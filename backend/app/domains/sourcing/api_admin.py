"""
/admin/* AI broker endpoints (Phase 4): inventory + partner CRUD, per-request
sourcing waterfall, and the market-intelligence board. Analyst/admin only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.requests.models import Request
from app.domains.sourcing import service as sourcing_service
from app.domains.sourcing.models import InventoryItem, PartnerSupplier
from app.domains.sourcing.schemas import (
    InventoryItemIn,
    InventoryItemOut,
    InventoryItemPatch,
    MarketIntelRow,
    PartnerSupplierIn,
    PartnerSupplierOut,
    PartnerSupplierPatch,
    SourcingRunOut,
)

# No router-level gate: these eleven routes serve FOUR different dashboard
# pages (inventory, partners, sourcing, intel), so each declares its own.
router = APIRouter(prefix="/admin", tags=["sourcing"])


# ── Inventory CRUD ───────────────────────────────────────────────────────────────

@router.get("/inventory", dependencies=[Depends(require_page("inventory", "read"))], response_model=list[InventoryItemOut])
def list_inventory(
    db: Session = Depends(get_db),
) -> list[InventoryItemOut]:
    return db.query(InventoryItem).order_by(InventoryItem.product_id).all()  # type: ignore[return-value]


@router.post("/inventory", dependencies=[Depends(require_page("inventory", "write"))], response_model=InventoryItemOut, status_code=status.HTTP_201_CREATED)
def create_inventory(
    body: InventoryItemIn,
    db: Session = Depends(get_db),
) -> InventoryItemOut:
    item = InventoryItem(**body.model_dump())
    db.add(item)
    db.commit()
    return item  # type: ignore[return-value]


@router.patch("/inventory/{item_id}", dependencies=[Depends(require_page("inventory", "write"))], response_model=InventoryItemOut)
def update_inventory(
    item_id: int,
    body: InventoryItemPatch,
    db: Session = Depends(get_db),
) -> InventoryItemOut:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    return item  # type: ignore[return-value]


@router.delete("/inventory/{item_id}", dependencies=[Depends(require_page("inventory", "write"))], status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory(
    item_id: int,
    db: Session = Depends(get_db),
) -> None:
    item = db.get(InventoryItem, item_id)
    if item is not None:
        db.delete(item)
        db.commit()


# ── Partner suppliers CRUD ───────────────────────────────────────────────────────

@router.get("/partners", dependencies=[Depends(require_page("partners", "read"))], response_model=list[PartnerSupplierOut])
def list_partners(
    db: Session = Depends(get_db),
) -> list[PartnerSupplierOut]:
    return db.query(PartnerSupplier).order_by(PartnerSupplier.name).all()  # type: ignore[return-value]


@router.post("/partners", dependencies=[Depends(require_page("partners", "write"))], response_model=PartnerSupplierOut, status_code=status.HTTP_201_CREATED)
def create_partner(
    body: PartnerSupplierIn,
    db: Session = Depends(get_db),
) -> PartnerSupplierOut:
    partner = PartnerSupplier(**body.model_dump())
    db.add(partner)
    db.commit()
    return partner  # type: ignore[return-value]


@router.patch("/partners/{partner_id}", dependencies=[Depends(require_page("partners", "write"))], response_model=PartnerSupplierOut)
def update_partner(
    partner_id: int,
    body: PartnerSupplierPatch,
    db: Session = Depends(get_db),
) -> PartnerSupplierOut:
    partner = db.get(PartnerSupplier, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(partner, k, v)
    db.commit()
    return partner  # type: ignore[return-value]


@router.delete("/partners/{partner_id}", dependencies=[Depends(require_page("partners", "write"))], status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(
    partner_id: int,
    db: Session = Depends(get_db),
) -> None:
    partner = db.get(PartnerSupplier, partner_id)
    if partner is not None:
        db.delete(partner)
        db.commit()


# ── Sourcing ─────────────────────────────────────────────────────────────────────

@router.post("/requests/{request_id}/source", dependencies=[Depends(require_page("sourcing", "write"))], response_model=SourcingRunOut, status_code=status.HTTP_201_CREATED)
def source_request(
    request_id: int,
    db: Session = Depends(get_db),
) -> SourcingRunOut:
    request = db.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    run = sourcing_service.source_request(db, request)
    db.commit()
    return run  # type: ignore[return-value]


@router.get("/requests/{request_id}/sourcing", dependencies=[Depends(require_page("sourcing", "read"))], response_model=SourcingRunOut)
def get_sourcing(
    request_id: int,
    db: Session = Depends(get_db),
) -> SourcingRunOut:
    run = sourcing_service.latest_sourcing_run(db, request_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sourcing run yet")
    return run  # type: ignore[return-value]


# ── Market intelligence ──────────────────────────────────────────────────────────

@router.get("/intel/market", dependencies=[Depends(require_page("intel", "read"))], response_model=list[MarketIntelRow])
def market_intel(
    db: Session = Depends(get_db),
) -> list[MarketIntelRow]:
    return sourcing_service.market_overview(db)
