"""Domain event type constants — the vocabulary of the transactional outbox.

These strings are the contract between producers (`event_service.emit`) and the
dispatcher's consumer routing (`app/tasks/events.py::CONSUMERS`). They are stored
verbatim in `domain_events.event_type`. Values are STABLE — renaming a value is a
data-migration concern, so append new events, never rename existing ones.

R1 set below; R2/R3 extend (add new constants here + register consumers in the
dispatcher).
"""

from __future__ import annotations

# ── Company registry / lifecycle ─────────────────────────────────────────────
COMPANY_REGISTERED = "company.registered"
COMPANY_PROFILE_UPDATED = "company.profile_updated"
COMPANY_VERIFIED = "company.verified"
COMPANY_SUSPENDED = "company.suspended"
COMPANY_REINSTATED = "company.reinstated"

# ── Verification cases ────────────────────────────────────────────────────────
VERIFICATION_CASE_SUBMITTED = "verification.case_submitted"
VERIFICATION_CHECK_COMPLETED = "verification.check_completed"
VERIFICATION_CASE_NEEDS_INFO = "verification.case_needs_info"
VERIFICATION_CASE_APPROVED = "verification.case_approved"
VERIFICATION_CASE_REJECTED = "verification.case_rejected"

# ── E-IMZO identity confirmation (R3) ─────────────────────────────────────────
COMPANY_EIMZO_CONFIRMED = "company.eimzo_confirmed"

# ── Contracts (R3 Stage B) ────────────────────────────────────────────────────
CONTRACT_CREATED = "contract.created"
CONTRACT_SENT = "contract.sent"
CONTRACT_SIGNED = "contract.signed"
CONTRACT_ACTIVATED = "contract.activated"
CONTRACT_DECLINED = "contract.declined"
CONTRACT_CANCELLED = "contract.cancelled"

# ── Deals (R4 / P2) ───────────────────────────────────────────────────────────
DEAL_OPENED = "deal.opened"
DEAL_STATUS_CHANGED = "deal.status_changed"
DEAL_MESSAGE_POSTED = "deal.message_posted"
DEAL_DOCUMENT_ADDED = "deal.document_added"
RFQ_RESPONSE_SUBMITTED = "rfq_response.submitted"
RFQ_RESPONSE_ACCEPTED = "rfq_response.accepted"
RFQ_RESPONSE_NOT_SELECTED = "rfq_response.not_selected"

# ── Marketplace bridge ────────────────────────────────────────────────────────
OFFER_PUBLISHED_BY_COMPANY = "offer.published_by_company"

# Every event_type the R1 system may emit. The dispatcher treats any type absent
# from this set (and therefore from CONSUMERS) as "unroutable" — logged and
# skipped, never crashing the poll loop.
ALL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        COMPANY_REGISTERED,
        COMPANY_PROFILE_UPDATED,
        COMPANY_VERIFIED,
        COMPANY_SUSPENDED,
        COMPANY_REINSTATED,
        VERIFICATION_CASE_SUBMITTED,
        VERIFICATION_CHECK_COMPLETED,
        VERIFICATION_CASE_NEEDS_INFO,
        VERIFICATION_CASE_APPROVED,
        VERIFICATION_CASE_REJECTED,
        COMPANY_EIMZO_CONFIRMED,
        CONTRACT_CREATED,
        CONTRACT_SENT,
        CONTRACT_SIGNED,
        CONTRACT_ACTIVATED,
        CONTRACT_DECLINED,
        CONTRACT_CANCELLED,
        DEAL_OPENED,
        DEAL_STATUS_CHANGED,
        DEAL_MESSAGE_POSTED,
        DEAL_DOCUMENT_ADDED,
        RFQ_RESPONSE_SUBMITTED,
        RFQ_RESPONSE_ACCEPTED,
        RFQ_RESPONSE_NOT_SELECTED,
        OFFER_PUBLISHED_BY_COMPANY,
    }
)
