"""
R2 W1 T1.2 — enum/status audit + TG-origin request serialization golden.

Two guards for the dual-origin relaxation shipped in 0018 (client_id → NULLABLE,
new origin columns):

1. **Machine/status audit** — the RequestStatus / OfferRequestStatus state machines
   and CLIENT_STATUS_MAP are unchanged and complete, so the portal can *reuse*
   CLIENT_STATUS_MAP for its client-facing labels rather than forking it (R2-PLAN
   T1.2: "reuse, don't fork").

2. **Byte-identical serialization golden** — a fully-populated TG-origin request,
   serialized through the frozen Mini App contract (`webapp.RequestDetailOut`,
   exactly as `GET /webapp/requests/{id}` builds it), must match the committed
   golden fixture. Relaxing client_id / adding origin columns must not shift a
   single byte of the wire shape the frozen webapp depends on.

App imports are lazy (inside functions) per the suite convention: the session
``patch_env`` fixture runs after collection, so top-level ``app.*`` imports would
fail Settings() validation at import time.
"""

from __future__ import annotations

import datetime
import decimal
import json
from pathlib import Path
from typing import Any

_GOLDEN = Path(__file__).parent / "fixtures" / "request_detail_tg_origin.golden.json"

_UTC = datetime.UTC


def _build_canonical_tg_request() -> Any:
    """A deterministic, fully-populated TG-origin request (client_id set).

    Fixed ids / datetimes / decimals so the serialization is reproducible; the
    frozen shape is pinned by the golden fixture.
    """
    from app.models.enums import PriceBasis, RequestStatus, Urgency  # noqa: PLC0415
    from app.models.requests import (  # noqa: PLC0415
        Client,
        Request,
        RequestFile,
        RequestStatusHistory,
    )

    client = Client(
        id=42,
        telegram_user_id=777001,
        phone="+998901234567",
        company_name="OOO BuyerCo",
        contact_name="Ivan",
        language="ru",
    )
    req = Request(
        id=125,
        number="REQ-2026-06-12-00125",
        client_id=42,
        # Dual-origin columns present but NULL for a TG-origin request.
        company_id=None,
        created_by_user_account_id=None,
        status=RequestStatus.viewed,
        product_id=3,
        product_text=None,
        grade_text="H030SG",
        polymer_type="HDPE",
        volume=decimal.Decimal("25.000"),
        volume_unit="MT",
        target_price=decimal.Decimal("1150.00"),
        currency="USD",
        incoterms=PriceBasis.CIF,
        destination_country="UZ",
        port_or_city="Tashkent",
        desired_date=datetime.date(2026, 7, 1),
        validity_days=30,
        urgency=Urgency.high,
        comment="Need TDS.",
        company_name="OOO BuyerCo",
        contact_name="Ivan",
        phone="+998901234567",
        legal_address="Tashkent, Uzbekistan",
        created_at=datetime.datetime(2026, 6, 12, 8, 30, tzinfo=_UTC),
        updated_at=datetime.datetime(2026, 6, 12, 9, 0, tzinfo=_UTC),
    )
    req.client = client
    req.files = [
        RequestFile(
            id=9,
            request_id=125,
            file_name="spec.pdf",
            mime_type="application/pdf",
            size_bytes=20480,
            storage_path="requests/125/spec.pdf",
        )
    ]
    req.status_history = [
        RequestStatusHistory(
            id=1,
            request_id=125,
            from_status=None,
            to_status=RequestStatus.new,
            created_at=datetime.datetime(2026, 6, 12, 8, 30, tzinfo=_UTC),
        ),
        RequestStatusHistory(
            id=2,
            request_id=125,
            from_status=RequestStatus.new,
            to_status=RequestStatus.viewed,
            created_at=datetime.datetime(2026, 6, 12, 9, 0, tzinfo=_UTC),
        ),
    ]
    return req


def _serialize_like_get_request(req: Any) -> dict:
    """Reproduce exactly what GET /webapp/requests/{id} builds + returns."""
    from app.schemas.webapp import RequestDetailOut  # noqa: PLC0415

    history = sorted(req.status_history, key=lambda h: h.created_at)
    detail = RequestDetailOut(
        id=req.id,
        number=req.number,
        status=req.status,
        created_at=req.created_at,
        product_id=req.product_id,
        product_text=req.product_text,
        grade_text=req.grade_text,
        polymer_type=req.polymer_type,
        volume=req.volume,
        volume_unit=req.volume_unit,
        target_price=req.target_price,
        currency=req.currency,
        incoterms=req.incoterms,
        destination_country=req.destination_country,
        port_or_city=req.port_or_city,
        desired_date=req.desired_date,
        validity_days=req.validity_days,
        urgency=req.urgency,
        comment=req.comment,
        company_name=req.company_name,
        contact_name=req.contact_name,
        phone=req.phone,
        legal_address=req.legal_address,
        files=req.files,
        history=history,
    )
    return detail.model_dump(mode="json")


class TestStatusMachineAudit:
    """T1.2: the machines/maps are unchanged and reusable by the portal."""

    def test_client_status_map_covers_every_request_status(self) -> None:
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import CLIENT_STATUS_MAP  # noqa: PLC0415

        # Reuse (don't fork) requires CLIENT_STATUS_MAP be total over RequestStatus.
        assert set(CLIENT_STATUS_MAP) == set(RequestStatus)

    def test_valid_transitions_declared_for_every_status(self) -> None:
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert set(VALID_TRANSITIONS) == set(RequestStatus)

    def test_client_facing_status_resolves_every_status(self) -> None:
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import (  # noqa: PLC0415
            CLIENT_STATUS_MAP,
            client_facing_status,
        )

        for status in RequestStatus:
            assert client_facing_status(status) == CLIENT_STATUS_MAP[status]

    def test_request_status_values_frozen(self) -> None:
        from app.models.enums import RequestStatus  # noqa: PLC0415

        assert [s.value for s in RequestStatus] == [
            "new",
            "viewed",
            "in_progress",
            "offer_sent",
            "matched",
            "closed",
            "cancelled",
        ]

    def test_offer_request_status_values_frozen(self) -> None:
        from app.models.enums import OfferRequestStatus  # noqa: PLC0415

        # Inquiry machine unchanged by 0018 (only origin columns were added).
        assert {s.value for s in OfferRequestStatus} == {
            "pending",
            "approved",
            "rejected",
        }


class TestTgRequestSerializationGolden:
    def test_tg_origin_detail_matches_golden(self) -> None:
        actual = _serialize_like_get_request(_build_canonical_tg_request())
        golden = json.loads(_GOLDEN.read_text())
        assert actual == golden, (
            "TG-origin request serialization drifted from the frozen golden. "
            "The webapp is a frozen contract — if this change is intentional, "
            "regenerate tests/fixtures/request_detail_tg_origin.golden.json."
        )
