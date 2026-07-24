"""R1 security pass (W8 — T8.2): PII/secrets never leave via schemas, presign TTL
is bounded, and internal storage paths aren't exposed. Complements the behavioural
tests (bank number never in a company response — test_portal_companies_api; OTP code
never logged — test_otp_service / test_verification_notify; JWT audience isolation —
test_portal_auth_api).
"""

from __future__ import annotations

import inspect

# Fields that must never appear in a RESPONSE (Out) schema. `account_number` is a
# legitimate INPUT (BankAccountIn) — the user submits it and it's encrypted
# server-side — so the check below only scans `*Out` models.
_FORBIDDEN_FIELDS = {
    "account_number",
    "account_number_enc",
    "password",
    "password_hash",
    "storage_path",
}


def _pydantic_models(module) -> list[type]:  # noqa: ANN001
    from pydantic import BaseModel  # noqa: PLC0415

    out: list[type] = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            out.append(obj)
    return out


def test_portal_response_schemas_expose_no_secret_fields() -> None:
    import app.schemas.portal as portal  # noqa: PLC0415
    import app.schemas.portal_company as portal_company  # noqa: PLC0415

    for module in (portal, portal_company):
        for model in _pydantic_models(module):
            if not model.__name__.endswith("Out"):
                continue  # response models only — inputs legitimately carry account_number
            leaked = set(model.model_fields) & _FORBIDDEN_FIELDS
            assert not leaked, f"{model.__name__} exposes secret field(s): {leaked}"


def test_bank_account_out_masks_the_number() -> None:
    from app.schemas.portal_company import BankAccountOut  # noqa: PLC0415

    fields = set(BankAccountOut.model_fields)
    assert "account_masked" in fields
    assert not (fields & {"account_number", "account_number_enc"})


def test_document_out_hides_internal_storage_path() -> None:
    from app.schemas.portal_company import DocumentOut  # noqa: PLC0415

    assert "storage_path" not in DocumentOut.model_fields


def test_presign_ttl_default_bounded_to_600s() -> None:
    from app.services import storage_service  # noqa: PLC0415

    ttl = inspect.signature(storage_service.presign_verification_document).parameters["ttl"].default
    assert ttl <= 600


def test_account_out_never_exposes_telegram_bridge() -> None:
    # telegram_user_id is a dormant bridge column — never surface it to the client.
    from app.schemas.portal import AccountOut  # noqa: PLC0415

    assert "telegram_user_id" not in AccountOut.model_fields
