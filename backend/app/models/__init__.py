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
from app.models.counterparties import Counterparty, CounterpartyAlias  # noqa: F401
from app.models.enums import (  # noqa: F401
    AlertKind,
    CounterpartyRole,
    DeliveryChannel,
    DeliveryStatus,
    ParseStatus,
    PriceBasis,
    PricePointKind,
    ReportKind,
    ReportStatus,
    RequestStatus,
    SignalKind,
    SourceKind,
    StaffRole,
    Urgency,
)
from app.models.prices import PricePoint  # noqa: F401
from app.models.reference import FxRate, Product, ProductGrade  # noqa: F401
from app.models.reports import Report  # noqa: F401
from app.models.requests import Client, Request, RequestFile, RequestStatusHistory  # noqa: F401
from app.models.signals import Signal  # noqa: F401
from app.models.sources import ParseRun, RawItem, Source  # noqa: F401
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
    # Reference
    "Product",
    "ProductGrade",
    "FxRate",
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
]
