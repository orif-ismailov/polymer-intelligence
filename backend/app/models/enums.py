"""
PostgreSQL ENUM type definitions for the Polymer Intelligence schema.

All 14 ENUM types are declared here and imported by the model modules.
Values are verbatim from the locked DDL (docs/polymer-intelligence-db-architecture.md v1.1).

IMPORTANT: ENUM values must not be changed without a schema migration.
Schema changes only via Alembic migration + DB-doc edit in the same PR (dev-spec §8).
"""

from __future__ import annotations

import enum


class SourceKind(enum.StrEnum):
    """Type of data source."""

    exchange = "exchange"
    telegram_channel = "telegram_channel"
    website = "website"
    webapp = "webapp"
    manual = "manual"
    external_index = "external_index"
    rss = "rss"


class ParseStatus(enum.StrEnum):
    """Processing status of a raw item."""

    pending = "pending"
    parsed = "parsed"
    failed = "failed"
    skipped = "skipped"
    irrelevant = "irrelevant"
    budget_deferred = "budget_deferred"  # Phase 5 G4: rule-based fallback ran, awaiting nightly LLM catch-up


class CounterpartyRole(enum.StrEnum):
    """Market role of a counterparty."""

    buyer = "buyer"
    seller = "seller"
    trader = "trader"
    producer = "producer"
    unknown = "unknown"


class SignalKind(enum.StrEnum):
    """Type of market signal."""

    buy_request = "buy_request"
    sell_offer = "sell_offer"
    deal = "deal"
    price_quote = "price_quote"
    news = "news"


class PriceBasis(enum.StrEnum):
    """Incoterms / delivery basis for price."""

    EXW = "EXW"
    FCA = "FCA"
    FOB = "FOB"
    CIF = "CIF"
    CPT = "CPT"
    DAP = "DAP"
    DDP = "DDP"
    unknown = "unknown"


class Urgency(enum.StrEnum):
    """Urgency / priority level."""

    low = "low"
    medium = "medium"
    high = "high"


class RequestStatus(enum.StrEnum):
    """Client request lifecycle status."""

    new = "new"
    viewed = "viewed"
    in_progress = "in_progress"
    offer_sent = "offer_sent"
    matched = "matched"
    closed = "closed"
    cancelled = "cancelled"


class PricePointKind(enum.StrEnum):
    """Type of derived price point."""

    deal_avg = "deal_avg"
    offer_avg = "offer_avg"
    index = "index"  # type: ignore[assignment]  # "index" shadows str.index() method; DB ENUM value must stay "index"
    futures = "futures"


class AlertKind(enum.StrEnum):
    """Type of alert rule / alert event."""

    new_hot_request = "new_hot_request"
    large_volume = "large_volume"
    price_spike = "price_spike"
    below_market_offer = "below_market_offer"
    new_buyer = "new_buyer"
    source_failure = "source_failure"
    custom = "custom"


class DeliveryChannel(enum.StrEnum):
    """Delivery channel for notifications."""

    telegram_dm = "telegram_dm"
    telegram_channel = "telegram_channel"
    webapp = "webapp"
    dashboard = "dashboard"


class DeliveryStatus(enum.StrEnum):
    """Delivery status for a notification."""

    queued = "queued"
    sent = "sent"
    failed = "failed"


class ReportKind(enum.StrEnum):
    """Type of market report."""

    morning = "morning"
    evening = "evening"
    intraday = "intraday"
    weekly = "weekly"
    custom = "custom"


class ReportStatus(enum.StrEnum):
    """Publication status of a report (human-in-the-loop)."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    published = "published"
    rejected = "rejected"


class StaffRole(enum.StrEnum):
    """Internal staff access role (REQ-roles, enforced in plan 01-03)."""

    admin = "admin"
    analyst = "analyst"
    trader = "trader"
    viewer = "viewer"


class SellerOfferStatus(enum.StrEnum):
    """Moderation lifecycle of a seller-published marketplace offer (Phase 2).

    draft → pending_moderation → {approved, rejected}; approved → archived.
    Only `approved` offers appear in the public catalog (per-offer moderation).
    """

    draft = "draft"
    pending_moderation = "pending_moderation"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class OfferFileKind(enum.StrEnum):
    """Type of file attached to a seller offer (Phase 2)."""

    image = "image"
    tds = "tds"
    certificate = "certificate"
    other = "other"


class OfferAvailability(enum.StrEnum):
    """Whether a seller offer is on hand or produced/sourced on demand (Phase 2).

    in_stock — «в наличии» (ready to ship); on_order — «под заказ» (made/sourced on demand).
    """

    in_stock = "in_stock"
    on_order = "on_order"


class OfferRequestStatus(enum.StrEnum):
    """Moderation lifecycle of a buyer's inquiry against a seller offer.

    A buyer taps "Request an offer" → `pending` (admin review gate). The admin
    approves → `approved` (the inquiry is forwarded to the seller by bot DM) or
    rejects → `rejected`. The buyer sees this status on their inquiry.
    """

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── Company Verification & Portal (R1) ────────────────────────────────────────
# Identity model v2 (ARCHITECTURE Amendment A1): person = user_accounts (phone
# OTP), company membership via company_members.user_account_id. All ENUM values
# below are verbatim from R1-PLAN §T1.1 and mapped to native PG ENUM types in
# migration 0017. Do not change a value without a migration + DB-doc edit.


class AccountStatus(enum.StrEnum):
    """Portal user-account lifecycle (PG type: account_status)."""

    active = "active"
    blocked = "blocked"


class CompanyStatus(enum.StrEnum):
    """Company verification lifecycle (PG type: company_status).

    draft → pending_verification → {verified, rejected}; verified → suspended →
    verified (reinstate); liquidated is terminal (gov-driven, P2).
    """

    draft = "draft"
    pending_verification = "pending_verification"
    verified = "verified"
    rejected = "rejected"
    suspended = "suspended"
    liquidated = "liquidated"


class CompanyMemberRole(enum.StrEnum):
    """Membership role within a company (PG type: company_member_role)."""

    owner = "owner"
    manager = "manager"
    member = "member"


class CompanyMemberStatus(enum.StrEnum):
    """Membership status within a company (PG type: company_member_status)."""

    active = "active"
    invited = "invited"
    removed = "removed"


class CompanyBusinessRole(enum.StrEnum):
    """Declared business role of a company (PG type: company_business_role)."""

    manufacturer = "manufacturer"
    importer = "importer"
    trader = "trader"
    logistics_provider = "logistics_provider"
    distributor = "distributor"
    laboratory = "laboratory"
    insurance_provider = "insurance_provider"


class BusinessRoleStatus(enum.StrEnum):
    """Confirmation state of a declared business role (PG type: business_role_status)."""

    declared = "declared"
    confirmed = "confirmed"
    revoked = "revoked"


class BankAccountStatus(enum.StrEnum):
    """Company bank-account verification state (PG type: bank_account_status)."""

    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    failed = "failed"
    archived = "archived"


class BankVerificationMethod(enum.StrEnum):
    """How a bank account was verified (PG type: bank_verification_method)."""

    document = "document"
    e_invoice_crosscheck = "e_invoice_crosscheck"
    bank_api = "bank_api"
    manual = "manual"


class VerificationCaseType(enum.StrEnum):
    """Type of a verification case (PG type: verification_case_type)."""

    onboarding = "onboarding"
    reverification = "reverification"
    targeted = "targeted"


class VerificationCaseStatus(enum.StrEnum):
    """Verification-case lifecycle (PG type: verification_case_status).

    draft → submitted → checks_running → {needs_info, pending_review} →
    {approved, rejected}; cancelled is terminal.
    """

    draft = "draft"
    submitted = "submitted"
    checks_running = "checks_running"
    needs_info = "needs_info"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class VerificationCheckType(enum.StrEnum):
    """Individual check within a case (PG type: verification_check_type).

    R1 ships the four manual/format checks. R3 adds eimzo_signature and P2 adds
    gov_registry/tax_status/vat_status via ALTER TYPE ADD VALUE.
    """

    tax_id_format = "tax_id_format"
    bank_requisites = "bank_requisites"
    documents_complete = "documents_complete"
    manual_kyb = "manual_kyb"
    eimzo_signature = "eimzo_signature"  # R3 — E-IMZO digital-signature identity confirmation


class VerificationCheckStatus(enum.StrEnum):
    """Result state of a check (PG type: verification_check_status)."""

    pending = "pending"
    running = "running"
    passed = "passed"
    warning = "warning"
    failed = "failed"
    unavailable = "unavailable"
    waived = "waived"


class VerificationDocumentKind(enum.StrEnum):
    """Kind of uploaded verification document (PG type: verification_document_kind)."""

    registration_certificate = "registration_certificate"
    director_id = "director_id"
    bank_letter = "bank_letter"
    license = "license"
    permit = "permit"
    certificate = "certificate"
    power_of_attorney = "power_of_attorney"
    other = "other"


class DocumentReviewStatus(enum.StrEnum):
    """Staff review state of a verification document (PG type: document_review_status)."""

    pending_review = "pending_review"
    accepted = "accepted"
    rejected = "rejected"


# ── Contracts (R3 Stage B — Deal Lifecycle seed) ──────────────────────────────


class ContractStatus(enum.StrEnum):
    """Contract lifecycle (PG type: contract_status).

    draft → pending_counterparty → pending_signatures → active; declined /
    cancelled / expired are terminal.
    """

    draft = "draft"
    pending_counterparty = "pending_counterparty"
    pending_signatures = "pending_signatures"
    active = "active"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


# ── Deals (R4 / P2 — Deal Lifecycle core) ─────────────────────────────────────


class DealStatus(enum.StrEnum):
    """Deal lifecycle (PG type: deal_status).

    negotiation → contract_pending → contract_signed → payment_pending →
    paid_escrow → shipped → delivered → completed. `disputed` is reachable from
    every in-flight state and only staff can leave it; `completed`/`cancelled`
    are terminal. The transition table itself lives in
    `app/services/deal_service.py::VALID_TRANSITIONS` — declaration order here is
    the happy path, not the rule.
    """

    negotiation = "negotiation"
    contract_pending = "contract_pending"
    contract_signed = "contract_signed"
    payment_pending = "payment_pending"
    paid_escrow = "paid_escrow"
    shipped = "shipped"
    delivered = "delivered"
    completed = "completed"
    cancelled = "cancelled"
    disputed = "disputed"


class DealActorKind(enum.StrEnum):
    """Who drove a deal transition (PG type: deal_actor_kind).

    `system` is reserved for event-driven transitions (contract activation, and
    later the escrow callbacks) — no HTTP handler may pass it.
    """

    buyer = "buyer"
    seller = "seller"
    staff = "staff"
    system = "system"


class DealDocumentKind(enum.StrEnum):
    """Kind of document attached to a deal (PG type: deal_document_kind)."""

    contract = "contract"
    invoice = "invoice"
    lab_passport = "lab_passport"
    transport = "transport"
    other = "other"


class RfqResponseStatus(enum.StrEnum):
    """Supplier response to a buyer RFQ (PG type: rfq_response_status).

    Accepting one response moves the rest of that RFQ's submitted responses to
    `not_selected`. `withdrawn` frees the slot so the supplier may respond again.
    """

    submitted = "submitted"
    accepted = "accepted"
    not_selected = "not_selected"
    withdrawn = "withdrawn"


class RfqVisibility(enum.StrEnum):
    """Who may see a buyer's RFQ (PG type: rfq_visibility).

    Default `verified_only` — an RFQ carries commercial intent, so it is never
    widened to unverified companies unless the buyer chooses to.
    """

    verified_only = "verified_only"
    all = "all"
    selected = "selected"


class EscrowStatus(enum.StrEnum):
    """Escrow payment state (PG type: escrow_status).

    Deliberately shorter than the deal's own machine: escrow only answers "where
    is the money". `pending` — the buyer has been given an invoice; `funded` —
    the bank confirms the money arrived; `released` — it was paid out to the
    seller; `refunded` — it went back to the buyer. The last two are terminal.

    Each state change drags the deal with it (`escrow_service.mark`), which is
    why a deal can never reach `paid_escrow` or `completed` by hand.
    """

    pending = "pending"
    funded = "funded"
    released = "released"
    refunded = "refunded"
