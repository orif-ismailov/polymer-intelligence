"""R1 security pass (W8 — T8.2): PII/secrets never leave via schemas, presign TTL
is bounded, and internal storage paths aren't exposed. Complements the behavioural
tests (bank number never in a company response — test_portal_companies_api; an issued
password never logged or audited — test_portal_admin_accounts_api; JWT audience
isolation — test_portal_auth_api).
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

#: The ONE response that may carry a plaintext password, and the reason it must.
#:
#: `IssuedCredentialsOut` answers the staff call that MINTED the password. We store an
#: argon2 hash and nothing else, so this response is the only moment the plaintext
#: exists — there is no read route that could return it later, which is exactly the
#: property that makes it safe to send here and nowhere else.
#:
#: Named rather than pattern-matched (`*Credentials*` would wave through anything
#: somebody calls a credential) and asserted below to still be admin-only.
_ONE_TIME_SECRET_RESPONSES = {"IssuedCredentialsOut"}


def _pydantic_models(module) -> list[type]:  # noqa: ANN001
    from pydantic import BaseModel  # noqa: PLC0415

    out: list[type] = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            out.append(obj)
    return out


def test_portal_response_schemas_expose_no_secret_fields() -> None:
    import app.domains.accounts.schemas as portal  # noqa: PLC0415
    import app.domains.companies.schemas as portal_company  # noqa: PLC0415

    for module in (portal, portal_company):
        for model in _pydantic_models(module):
            if not model.__name__.endswith("Out"):
                continue  # response models only — inputs legitimately carry account_number
            if model.__name__ in _ONE_TIME_SECRET_RESPONSES:
                continue
            leaked = set(model.model_fields) & _FORBIDDEN_FIELDS
            assert not leaked, f"{model.__name__} exposes secret field(s): {leaked}"


def test_the_one_time_credentials_response_is_admin_only() -> None:
    """The exemption above is only tolerable while nothing but an admin can ask.

    If `IssuedCredentialsOut` ever became reachable by a page grant — or worse, by a
    cabinet account — a plaintext password would be one ordinary request away.
    """
    from fastapi.routing import APIRoute  # noqa: PLC0415

    from app.domains.accounts.api_admin import router  # noqa: PLC0415
    from app.domains.accounts.schemas import IssuedCredentialsOut  # noqa: PLC0415

    returning = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.response_model is IssuedCredentialsOut
    ]
    assert returning, "no route returns IssuedCredentialsOut — has it been renamed?"

    for route in returning:
        guards = {
            getattr(dependency.call, "__name__", "")
            for dependency in route.dependant.dependencies
        }
        assert "require_admin" in guards, f"{route.path} is not administrator-only"


def test_bank_account_out_masks_the_number() -> None:
    from app.domains.companies.schemas import BankAccountOut  # noqa: PLC0415

    fields = set(BankAccountOut.model_fields)
    assert "account_masked" in fields
    assert not (fields & {"account_number", "account_number_enc"})


def test_document_out_hides_internal_storage_path() -> None:
    from app.domains.companies.schemas import DocumentOut  # noqa: PLC0415

    assert "storage_path" not in DocumentOut.model_fields


def test_presign_ttl_default_bounded_to_600s() -> None:
    from app.services import storage_service  # noqa: PLC0415

    ttl = inspect.signature(storage_service.presign_verification_document).parameters["ttl"].default
    assert ttl <= 600


def test_account_out_never_exposes_telegram_bridge() -> None:
    # telegram_user_id is a dormant bridge column — never surface it to the client.
    from app.domains.accounts.schemas import AccountOut  # noqa: PLC0415

    assert "telegram_user_id" not in AccountOut.model_fields
