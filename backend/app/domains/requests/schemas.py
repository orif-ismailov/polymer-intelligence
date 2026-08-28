"""Portal purchase-request schemas (R2 W3 T3.3).

The wizard payload is the Mini App's ``RequestCreate`` plus the acting company. The
read side extends the webapp ``RequestOut`` / ``RequestDetailOut`` (raw status; the
portal frontend maps it to client-facing labels via CLIENT_STATUS_MAP), so a
portal-origin request serializes like a TG-origin one **plus** the two tender
fields the cabinet owns.

Those two live here rather than on the webapp schemas because the Mini App wire
shape is a frozen contract, pinned byte-for-byte by
``tests/fixtures/request_detail_tg_origin.golden.json``.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from app.domains.deals.models import normalize_required_docs
from app.domains.requests.webapp_schemas import RequestCreate, RequestDetailOut
from app.models.enums import RfqVisibility


class PortalRequestCreate(RequestCreate):
    """Body for POST /portal/requests — the wizard payload + acting company.

    Two fields the Mini App path does not have. A portal request IS a tender:
    the cabinet announces it to suppliers, so the buyer decides who may see it
    and which documents a quote must come with. Both live on the portal schema
    only — the Mini App is a brokered flow and keeps the column defaults.
    """

    company_id: int
    visibility: RfqVisibility = RfqVisibility.verified_only
    required_docs: list[str] = Field(default_factory=list)

    @field_validator("required_docs")
    @classmethod
    def _known_codes_only(cls, v: list[str]) -> list[str]:
        """Drop anything outside ``REQUIRED_DOC_CODES`` — the same rule the
        column is normalized by, applied at the edge so a typo in the client
        cannot reach the row."""
        return normalize_required_docs(v) or []

    @field_validator("visibility")
    @classmethod
    def _no_selected_without_a_list(cls, v: RfqVisibility) -> RfqVisibility:
        """``selected`` needs ``visible_company_ids``, which this body cannot
        carry — and an empty list means the tender is visible to NOBODY. Refuse
        it rather than publish something no supplier can answer."""
        if v == RfqVisibility.selected:
            raise ValueError("visibility 'selected' is not supported from the portal yet")
        return v


class PortalRequestDetailOut(RequestDetailOut):
    """Detail view for the cabinet — the webapp shape plus the tender fields.

    Read back deliberately: a screen that can SET a field and not SEE it is how
    the value quietly disappears on the next save (the ИКПУ lesson, P7.a).
    """

    visibility: RfqVisibility
    required_docs: list[str] = Field(default_factory=list)

    @field_validator("required_docs", mode="before")
    @classmethod
    def _docs_never_null(cls, v: list[str] | None) -> list[str]:
        """The column is nullable ("asks for nothing"); the API says ``[]``."""
        return v or []
