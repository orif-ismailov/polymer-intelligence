"""The API's failure contract, as reusable OpenAPI response declarations.

FastAPI documents two things per route on its own: the success model, and the 422 it
generates for request-body validation. Everything else this API actually answers — the
401 from `deps.get_current_staff_user`, the 403 from `require_page`, the 404 a
non-member gets on a company-scoped path — was absent from `/openapi.json`, so a
generated client had no type for the failure branch and a reader could not learn the
codes without opening the handlers.

The sets below are attached at `include_router()` time in `app/main.py`, where the auth
surface of every router is visible in one table, and per-route in the handful of routers
that mix authenticated and anonymous routes (attaching a router-level 401 there would
document a code those anonymous routes cannot return). Route-level entries win over
router-level ones, so the two compose.

**They describe what a route CAN answer, not what one handler happens to raise today** —
which is why they are assigned by the dependencies in the route's tree. A guard that can
raise 403 makes 403 part of the contract of every route standing behind it.

Two deliberate omissions, so the next reader does not take the schema for more than it is:

- **422 is left as FastAPI generated it.** Around a hundred handlers raise
  `HTTPException(422, detail="…")` — a STRING where the auto-documented
  `HTTPValidationError` says a list of field errors. Overriding 422 here would replace
  the validation-error schema, which is the more common of the two shapes, so the
  narrower one stays undocumented rather than the broader one becoming wrong.
- **404/409/400/503 are declared only where they hold for every route in the router.**
  A collection route that cannot 404 must not say it can. The per-route remainder is
  named in `docs/API.md`.

`tests/test_openapi_errors.py` fails when a route's auth dependencies and its declared
codes disagree, in either direction — so this cannot drift as routers are added.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

#: What FastAPI accepts as a `responses=` mapping.
Responses = dict[int | str, dict[str, Any]]


class ErrorDetail(BaseModel):
    """The body of every `HTTPException` this API raises.

    There is no project-specific error envelope: FastAPI's default handler emits
    `{"detail": ...}` and no route installs its own. Naming it as a model gives a
    generated client ONE type for every failure branch instead of an untyped body.
    """

    detail: str = Field(
        description=(
            "Human-readable reason, for a log or a support ticket. It is not a machine "
            "code and its wording is not a contract — branch on the status code."
        ),
        examples=["Offer not found"],
    )


def error(
    status_code: int,
    description: str,
    example: str,
    *,
    headers: dict[str, Any] | None = None,
) -> Responses:
    """One documented failure, ready to merge into a `responses=` mapping.

    `example` is the real `detail` string the code raises — copied from the handler,
    not invented, so the rendered docs show what a client will actually receive.
    """
    response: dict[str, Any] = {
        "model": ErrorDetail,
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }
    if headers is not None:
        response["headers"] = headers
    return {status_code: response}


# ── Single codes, for per-route use ───────────────────────────────────────────

NOT_FOUND: Responses = error(
    404,
    "No such resource — or it exists and is not the caller's, which is deliberately "
    "indistinguishable from absent so that ownership is never leaked by a 403.",
    "Offer not found",
)

CONFLICT: Responses = error(
    409,
    "The resource is not in a state that allows this transition.",
    "Deal is not in a state that can be cancelled",
)

#: The Didox rail refusing a call because of its own state, not the request's.
#:
#: `detail` is a bare STABLE CODE here, not prose — branch on it. The common one by
#: far is `didox_session_required`: the acting company holds no live `user-key`, which
#: the person can fix in one click, so it is the normal answer for a company that has
#: not opened a session yet rather than an exceptional one. `didox_disabled` means this
#: deployment has no document rail configured at all.
#:
#: Undeclared, a generated client had no branch for the single most likely response on
#: the ИКПУ picker and handled it as an unexpected error (IMEX-10). Attached where the
#: rail can actually refuse — never router-wide on a router that also serves routes
#: reaching no provider.
DIDOX_CONFLICT: Responses = error(
    409,
    "The Didox rail is not in a state that allows this call. `detail` is a stable "
    "code: `didox_session_required` (no live `user-key` for the acting company — "
    "recoverable by opening a session), `didox_disabled` (no document rail on this "
    "deployment), or a per-route code such as `didox_offer_required`, "
    "`didox_not_registered`, `document_not_created`, `wrong_rail`, `not_ready`, "
    "`not_seller`, `counterparty_unknown`, `ikpu_missing` or `empty_body`.",
    "didox_session_required",
)

RETRY_AFTER_HEADER: dict[str, Any] = {
    "Retry-After": {
        "description": "Seconds to wait before retrying.",
        "schema": {"type": "integer"},
    }
}


# ── Per surface — assigned by what the route's dependencies can raise ─────────

#: Staff JWT + dashboard-page or admin grant (`app/api/deps.py`).
STAFF: Responses = {
    **error(
        401,
        "Missing, malformed, expired, or wrong-type staff Bearer token, or the staff "
        "row no longer exists. Sent with `WWW-Authenticate: Bearer`.",
        "Authentication required",
    ),
    **error(
        403,
        "Authenticated, but not permitted: the account is deactivated, is not an "
        "administrator where the route demands one, or lacks the dashboard-page grant "
        "this route is gated on. The body never enumerates what the caller may not reach.",
        "Access denied: requires write access to deals",
    ),
}

#: A staff route whose every path identifies a resource that may not exist.
STAFF_RESOURCE: Responses = {**STAFF, **NOT_FOUND}

#: Portal cabinet account — Bearer `portal_access` token (`deps.get_current_account`).
PORTAL: Responses = {
    **error(
        401,
        "Missing, malformed, or expired `portal_access` token, or the account no longer "
        "exists. A staff or webapp token fails here too: the token `type` claim isolates "
        "the three audiences.",
        "Authentication required",
    ),
    **error(
        403,
        "The account authenticated but is not `active`.",
        "Account is blocked",
    ),
}

#: A portal route whose every path identifies a resource. Non-membership answers 404
#: rather than 403 — see `company_service.get_company_for`.
PORTAL_RESOURCE: Responses = {**PORTAL, **NOT_FOUND}

#: Telegram Web App client — initData HMAC or the `client_session` cookie.
#: One generic 401 for every failure, on purpose (`T-03-03`): saying WHICH check failed
#: tells an attacker which half of the pair to work on. There is no 403 on this surface.
WEBAPP: Responses = {
    **error(
        401,
        "Neither the `X-Telegram-Init-Data` header nor the `client_session` cookie "
        "authenticated. Deliberately identical for every cause — absent, malformed, bad "
        "HMAC, or past its TTL.",
        "Authentication required",
    ),
}

#: A Telegram Web App route whose every path identifies a resource.
WEBAPP_RESOURCE: Responses = {**WEBAPP, **NOT_FOUND}
