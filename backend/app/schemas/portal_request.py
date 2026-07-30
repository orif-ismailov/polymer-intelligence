"""Portal purchase-request schemas (R2 W3 T3.3).

The wizard payload is the Mini App's ``RequestCreate`` plus the acting company. The
read side reuses the webapp ``RequestOut`` / ``RequestDetailOut`` verbatim (raw
status; the portal frontend maps it to client-facing labels via CLIENT_STATUS_MAP),
so a portal-origin request serializes exactly like a TG-origin one.
"""

from __future__ import annotations

from app.schemas.webapp import RequestCreate


class PortalRequestCreate(RequestCreate):
    """Body for POST /portal/requests — the wizard payload + acting company."""

    company_id: int
