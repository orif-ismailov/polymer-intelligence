"""
ORM model registry — importing all modules ensures Base.metadata is complete.

Import order respects FK dependency:
1. enums (no deps)
2. reference (no FK deps)
3. sources (no FK deps)
4. counterparties (depends on source_kind enum)
5. staff (no FK deps on other models, reports has FK to staff_users)
6. signals (depends on sources, products, counterparties)
7. requests (depends on products, counterparties)
8. prices (depends on sources, products)
9. alerts (depends on signals, requests)
10. reports (depends on staff)

This file must be imported by alembic/env.py so that
`target_metadata = Base.metadata` includes all 20 tables.
"""

from app.models.alerts import Alert, AlertRule, Delivery  # noqa: F401
from app.models.app_settings import AppSetting  # noqa: F401
from app.models.counterparties import Counterparty, CounterpartyAlias  # noqa: F401
from app.models.enums import (  # noqa: F401
    AlertKind,
    CounterpartyRole,
    DeliveryChannel,
    DeliveryStatus,
    OfferFileKind,
    OfferRequestStatus,
    ParseStatus,
    PriceBasis,
    PricePointKind,
    ReportKind,
    ReportStatus,
    RequestStatus,
    SellerOfferStatus,
    SignalKind,
    SourceKind,
    StaffRole,
    Urgency,
)
from app.models.marketplace import (  # noqa: F401
    OfferRequest,
    Seller,
    SellerOffer,
    SellerOfferFile,
)
from app.models.prices import PricePoint  # noqa: F401
from app.models.reference import (  # noqa: F401
    FxRate,
    ManualClassificationItem,
    Product,
    ProductGrade,
    ProductSynonym,
)
from app.models.reports import Report  # noqa: F401
from app.models.requests import Client, Request, RequestFile, RequestStatusHistory  # noqa: F401
from app.models.signals import Signal  # noqa: F401
from app.models.sources import ParseRun, RawItem, Source  # noqa: F401
from app.models.sourcing import InventoryItem, PartnerSupplier, SourcingRun  # noqa: F401
from app.models.staff import AuditLog, StaffUser  # noqa: F401

__all__ = [
    # Enums
    "SourceKind",
    "ParseStatus",
    "CounterpartyRole",
    "SignalKind",
    "PriceBasis",
    "Urgency",
    "RequestStatus",
    "PricePointKind",
    "AlertKind",
    "DeliveryChannel",
    "DeliveryStatus",
    "ReportKind",
    "ReportStatus",
    "StaffRole",
    "SellerOfferStatus",
    "OfferFileKind",
    "OfferRequestStatus",
    # Reference
    "Product",
    "ProductGrade",
    "FxRate",
    "ProductSynonym",
    "ManualClassificationItem",
    # Sources / raw
    "Source",
    "RawItem",
    "ParseRun",
    # Counterparties
    "Counterparty",
    "CounterpartyAlias",
    # Staff / audit
    "StaffUser",
    "AuditLog",
    # Signals
    "Signal",
    # Clients / requests
    "Client",
    "Request",
    "RequestFile",
    "RequestStatusHistory",
    # Prices
    "PricePoint",
    # Alerts
    "AlertRule",
    "Alert",
    "Delivery",
    # Reports
    "Report",
    # Runtime settings (Phase 8d)
    "AppSetting",
    # Marketplace (Phase 2)
    "Seller",
    "SellerOffer",
    "SellerOfferFile",
    "OfferRequest",
    # Sourcing (Phase 4)
    "InventoryItem",
    "PartnerSupplier",
    "SourcingRun",
]
