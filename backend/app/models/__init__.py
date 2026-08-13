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

from app.domains.marketplace.models import (  # noqa: F401
    OfferFavorite,
    OfferRequest,
    RfqPushLog,
    Seller,
    SellerOffer,
    SellerOfferFile,
)
from app.models.accounts import SmsSendLog, UserAccount  # noqa: F401
from app.models.alerts import Alert, AlertRule, Delivery  # noqa: F401
from app.models.app_settings import AppSetting  # noqa: F401
from app.models.companies import (  # noqa: F401
    Company,
    CompanyBankAccount,
    CompanyBusinessRole,
    CompanyMember,
)
from app.models.compliance import (  # noqa: F401
    CompanyLicense,
    Substance,
    SubstanceSuggestion,
)
from app.models.contracts import (  # noqa: F401
    Contract,
    ContractSignature,
    ContractTemplate,
)
from app.models.counterparties import Counterparty, CounterpartyAlias  # noqa: F401
from app.models.deals import (  # noqa: F401
    Deal,
    DealDocument,
    DealMessage,
    DealStatusHistory,
    RfqResponse,
)
from app.models.eimzo import CompanyPersonData, SignatureEvidence  # noqa: F401
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
from app.models.lab import LabOrder, LabPartner, SampleRequest  # noqa: F401
from app.models.laboratory import (  # noqa: F401
    LabRequest,
    LabRequestMessage,
    LabRequestThread,
)
from app.models.logistics import (  # noqa: F401
    LogisticsRequest,
    LogisticsRequestMessage,
    LogisticsRequestThread,
)
from app.models.manufacturers import (  # noqa: F401
    FactoryRfq,
    FactoryRfqDocument,
    ManufacturerMessage,
    ManufacturerThread,
)
from app.models.media import CompanyMedia  # noqa: F401
from app.models.notifications import PortalNotification  # noqa: F401
from app.models.payments import EscrowPayment, ProviderEvent  # noqa: F401
from app.models.prices import PricePoint  # noqa: F401
from app.models.reference import (  # noqa: F401
    FxRate,
    ManualClassificationItem,
    Product,
    ProductGrade,
    ProductSynonym,
)
from app.models.registry import RegistrySnapshot  # noqa: F401
from app.models.reports import Report  # noqa: F401
from app.models.requests import Client, Request, RequestFile, RequestStatusHistory  # noqa: F401
from app.models.reviews import CompanyReview  # noqa: F401
from app.models.signals import Signal  # noqa: F401
from app.models.sources import ParseRun, RawItem, Source  # noqa: F401
from app.models.sourcing import InventoryItem, PartnerSupplier, SourcingRun  # noqa: F401
from app.models.staff import AuditLog, StaffUser  # noqa: F401
from app.models.verification import (  # noqa: F401
    VerificationCase,
    VerificationCheck,
    VerificationDocument,
)

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
    "Seller",
    "SellerOffer",
    "SellerOfferFile",
    "OfferRequest",
    "OfferFavorite",
    "OfferSaleMode",
    "RfqPushLog",
    # Sourcing (Phase 4)
    "InventoryItem",
    "PartnerSupplier",
    "SourcingRun",
    # Company verification & portal (R1)
    "UserAccount",
    "SmsSendLog",
    "Company",
    "CompanyMember",
    "CompanyBusinessRole",
    "CompanyBankAccount",
    "VerificationCase",
    "VerificationCheck",
    "VerificationDocument",
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
    "RegistrySnapshot",
]
