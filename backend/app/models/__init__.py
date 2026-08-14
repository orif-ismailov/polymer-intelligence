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

That grouping is documentation, not a constraint: the import block is sorted by ruff's
isort and SQLAlchemy resolves foreign keys from `Base.metadata` once every model has
loaded, not in Python import order. What matters here is **completeness**, not
sequence — which is why models that move into `app/domains/<name>/` during the domain
reorg keep their line in this barrel rather than dropping out of it.

Nothing imports names from this module (`from app.models import X` has no call
sites), so `__all__` lists only what is still bound here; classes that moved into
a domain folder are imported from that folder directly.

This file must be imported by alembic/env.py so that
`target_metadata = Base.metadata` includes all 20 tables.
"""

# Models that have moved into app/domains/ are imported as MODULES, not by name.
#
# A domain model module starts with `from app.models.enums import ...`, which
# initializes this package and runs this barrel. If the barrel then asked that same
# module for a class by name, the name would not exist yet — the module is still on
# its first import line — and Python raises "cannot import name ... from partially
# initialized module". Importing the module only needs its sys.modules entry, which
# already exists by then, so the cycle resolves. The mapper classes still register
# themselves on Base.metadata as the module finishes executing, which is all this
# barrel exists to guarantee.
import app.domains.companies.models  # noqa: F401
import app.domains.marketplace.models  # noqa: F401
import app.domains.verification.models  # noqa: F401
import app.domains.verification.registry_models  # noqa: F401
from app.domains.compliance.models import (  # noqa: F401
    CompanyLicense,
    Substance,
    SubstanceSuggestion,
)
from app.domains.contracts.eimzo_models import CompanyPersonData, SignatureEvidence  # noqa: F401
from app.domains.contracts.models import (  # noqa: F401
    Contract,
    ContractSignature,
    ContractTemplate,
)
from app.domains.deals.models import (  # noqa: F401
    Deal,
    DealDocument,
    DealMessage,
    DealStatusHistory,
    RfqResponse,
)
from app.domains.deals.payment_models import EscrowPayment, ProviderEvent  # noqa: F401
from app.domains.lab_orders.models import LabOrder, LabPartner, SampleRequest  # noqa: F401
from app.domains.laboratory.models import (  # noqa: F401
    LabRequest,
    LabRequestMessage,
    LabRequestThread,
)
from app.domains.logistics.models import (  # noqa: F401
    LogisticsRequest,
    LogisticsRequestMessage,
    LogisticsRequestThread,
)
from app.domains.manufacturers.models import (  # noqa: F401
    FactoryRfq,
    FactoryRfqDocument,
    ManufacturerMessage,
    ManufacturerThread,
)
from app.models.accounts import SmsSendLog, UserAccount  # noqa: F401
from app.models.alerts import Alert, AlertRule, Delivery  # noqa: F401
from app.models.app_settings import AppSetting  # noqa: F401
from app.models.counterparties import Counterparty, CounterpartyAlias  # noqa: F401
from app.models.enums import (  # noqa: F401
    AccountStatus,
    AlertKind,
    BankAccountStatus,
    BankVerificationMethod,
    BusinessRoleStatus,
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyReviewStatus,
    CompanyStatus,
    CounterpartyRole,
    DealActorKind,
    DealDocumentKind,
    DealStatus,
    DeliveryChannel,
    DeliveryStatus,
    DocumentReviewStatus,
    EscrowStatus,
    FactoryRfqDocumentKind,
    FactoryRfqStatus,
    LabOrderStatus,
    LabRequestStatus,
    LicenseStatus,
    LogisticsRequestStatus,
    OfferFileKind,
    OfferRequestStatus,
    OfferSaleMode,
    ParseStatus,
    PriceBasis,
    PricePointKind,
    RegulationLevel,
    RegulationRegime,
    ReportKind,
    ReportStatus,
    RequestStatus,
    RfqResponseStatus,
    RfqVisibility,
    SampleRequestStatus,
    SellerOfferStatus,
    SignalKind,
    SourceKind,
    StaffRole,
    Urgency,
    VerificationCaseStatus,
    VerificationCaseType,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationDocumentKind,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.models.events import DomainEvent  # noqa: F401
from app.models.integration import IntegrationCallLog  # noqa: F401
from app.models.media import CompanyMedia  # noqa: F401
from app.models.notifications import PortalNotification  # noqa: F401
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
from app.models.reviews import CompanyReview  # noqa: F401
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
    # Company verification & portal (R1)
    "AccountStatus",
    "CompanyStatus",
    "CompanyMemberRole",
    "CompanyMemberStatus",
    "CompanyBusinessRoleEnum",
    "BusinessRoleStatus",
    "BankAccountStatus",
    "BankVerificationMethod",
    "VerificationCaseType",
    "VerificationCaseStatus",
    "VerificationCheckType",
    "VerificationCheckStatus",
    "VerificationDocumentKind",
    "DocumentReviewStatus",
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
    "OfferSaleMode",
    # Sourcing (Phase 4)
    "InventoryItem",
    "PartnerSupplier",
    "SourcingRun",
    # Company verification & portal (R1)
    "UserAccount",
    "SmsSendLog",
    "DomainEvent",
    # Portal notifications (R2)
    "PortalNotification",
    # E-IMZO evidence + integration gateway (R3)
    "SignatureEvidence",
    "CompanyPersonData",
    "IntegrationCallLog",
    # Contracts (R3 Stage B)
    "ContractTemplate",
    "Contract",
    "ContractSignature",
    # Deals (R4 / P2 — Deal Lifecycle core)
    "DealStatus",
    "DealActorKind",
    "DealDocumentKind",
    "RfqResponseStatus",
    "RfqVisibility",
    "Deal",
    "DealStatusHistory",
    "DealMessage",
    "DealDocument",
    "RfqResponse",
    # Payments / escrow (R4 / P3)
    "EscrowStatus",
    "EscrowPayment",
    "ProviderEvent",
    # Chemical compliance (R5 / P5)
    "RegulationLevel",
    "RegulationRegime",
    "LicenseStatus",
    "Substance",
    "CompanyLicense",
    "SubstanceSuggestion",
    # Labs and samples (R5 / P6)
    "LabOrderStatus",
    "SampleRequestStatus",
    "LabPartner",
    "LabOrder",
    "SampleRequest",
    # Manufacturers directory + factory RFQ
    "FactoryRfqStatus",
    "FactoryRfqDocumentKind",
    "FactoryRfq",
    "FactoryRfqDocument",
    "ManufacturerThread",
    "ManufacturerMessage",
    # Logistics directory + service requests
    "LogisticsRequestStatus",
    "LogisticsRequest",
    "LogisticsRequestThread",
    "LogisticsRequestMessage",
    # Laboratory analysis requests
    "LabRequestStatus",
    "LabRequest",
    "LabRequestThread",
    "LabRequestMessage",
    # Company reviews
    "CompanyReviewStatus",
    "CompanyReview",
    "CompanyMedia",
    # State-registry evidence (R6 / P7.c)
]
