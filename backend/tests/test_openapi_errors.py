"""The OpenAPI failure contract must match what the dependencies can actually raise.

`app/api/errors.py` declares the 401/403/404 sets and `app/main.py` attaches them per
router. Nothing about that arrangement is enforced by FastAPI: a router added without a
`responses=` argument documents only its success model and the generated 422, exactly as
the whole API did before, and the schema quietly goes back to being wrong. Since the
point of declaring the codes is that a generated client can trust them, "quietly wrong"
is the failure mode worth a test.

So this checks both directions:

- every route standing behind an auth guard DECLARES what that guard can raise, and
- no route claims a 401 or a 403 it has no way to produce.

The second half is why `_SELF_AUTHENTICATING` is an explicit list rather than a rule.
Those routes ARE the auth surface — login, OTP, refresh, the bot's shared-secret webhook —
so they raise 401/403 from the handler with no dependency to infer it from. Six routes,
each named, each cheap to re-check by eye when it changes.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.errors import ErrorDetail
from app.main import create_app

#: What each guard in `app/api/deps.py` can raise, and therefore what every route
#: standing behind it must document. Mirrors the docstrings there.
_GUARD_FAILURES: dict[str, set[int]] = {
    "get_current_staff_user": {401, 403},
    "get_current_staff_user_sse": {401, 403},
    "require_admin": {401, 403},
    "require_admin_sse": {401, 403},
    "get_current_account": {401, 403},
    # One generic 401 for every cause, and no 403 at all — T-03-03.
    "get_current_client": {401},
}

#: Routes that authenticate in the handler instead of behind a dependency, so their
#: 401/403 cannot be derived from the route's dependency tree. Adding to this list is
#: the deliberate act of declaring "this route IS an auth surface".
_SELF_AUTHENTICATING: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),  # wrong credentials → 401
    ("POST", "/api/v1/auth/refresh"),  # refresh cookie → 401
    ("POST", "/api/v1/portal/auth/otp/verify"),  # blocked account → 403
    ("POST", "/api/v1/portal/auth/refresh"),  # portal_session cookie → 401/403
    ("POST", "/api/v1/webapp/auth/telegram"),  # Login Widget HMAC → 401
    ("POST", "/api/v1/telegram/webhook/{secret}"),  # shared secret → 403
}

#: FastAPI generates this one from the request model; `errors.py` deliberately leaves it
#: alone, so it is the one documented failure without an `ErrorDetail` body.
_GENERATED = 422


class _Documented:
    """One route, with the failure codes that reach its OpenAPI operation.

    Router-level `responses=` do NOT land on `route.responses` — FastAPI 0.137 keeps an
    included router by reference and merges its context when the schema is built — so
    the effective set is the include context's codes plus the route's own.
    """

    def __init__(self, route: APIRoute, prefix: str, inherited: dict[Any, Any]) -> None:
        self.route = route
        self.path = prefix + route.path
        self.methods = sorted(route.methods or [])
        self.declared: dict[Any, Any] = {**inherited, **route.responses}
        self.codes = {int(code) for code in self.declared}

    @property
    def guards(self) -> set[str]:
        """Names of the auth dependencies anywhere in this route's dependency tree."""
        found: set[str] = set()
        stack = [self.route.dependant]
        seen: set[int] = set()
        while stack:
            dependant = stack.pop()
            if id(dependant) in seen:
                continue
            seen.add(id(dependant))
            call = getattr(dependant, "call", None)
            if call is not None and getattr(call, "__name__", "") in _GUARD_FAILURES:
                found.add(call.__name__)
            stack.extend(dependant.dependencies)
        return found

    @property
    def required(self) -> set[int]:
        return {code for guard in self.guards for code in _GUARD_FAILURES[guard]}

    def __str__(self) -> str:
        return f"{'/'.join(self.methods)} {self.path}"


def _walk(router: Any, prefix: str, inherited: dict[Any, Any]) -> list[_Documented]:
    """Collect every schema-visible APIRoute with the responses it inherits."""
    found: list[_Documented] = []
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute) and route.include_in_schema:
            found.append(_Documented(route, prefix, inherited))
        context = getattr(route, "include_context", None)
        if context is not None:
            found.extend(
                _walk(
                    context.included_router,
                    prefix + (context.prefix or ""),
                    {**inherited, **(context.responses or {})},
                )
            )
    return found


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


@pytest.fixture(scope="module")
def documented(app: FastAPI) -> list[_Documented]:
    routes = _walk(app.router, "", {})
    assert len(routes) > 300, "route walk missed most of the app — did routing change?"
    return routes


def test_every_guarded_route_documents_what_its_guard_raises(
    documented: list[_Documented],
) -> None:
    """A route behind an auth dependency declares that dependency's failures.

    The usual way to break this is to add a router to `create_app()` without a
    `responses=` argument: it works, it serves 401s, and it documents none of them.
    """
    missing = [
        f"{route} — guards {sorted(route.guards)} can raise "
        f"{sorted(route.required - route.codes)}, undeclared"
        for route in documented
        if route.required - route.codes
    ]
    assert not missing, "Undocumented auth failures:\n" + "\n".join(missing)


def test_no_route_claims_an_auth_failure_it_cannot_produce(
    documented: list[_Documented],
) -> None:
    """The other direction: an anonymous route must not advertise a 401 or a 403.

    Over-declaring is the cheaper mistake to make and the more expensive one to live
    with — a client that handles a code the server never sends writes dead branches, and
    a reader who finds one lie stops trusting the rest of the schema.
    """
    liars = [
        f"{route} — declares {sorted(route.codes & {401, 403})} with no auth dependency"
        for route in documented
        if route.codes & {401, 403}
        and not route.guards
        and not any((m, route.path) in _SELF_AUTHENTICATING for m in route.methods)
    ]
    assert not liars, "Undeliverable auth failures:\n" + "\n".join(liars)


def test_declared_failures_carry_the_shared_error_body(
    documented: list[_Documented],
) -> None:
    """Every declared failure answers with `ErrorDetail`, so a client has ONE type.

    `{"detail": ...}` is FastAPI's default body and no route overrides it, so a
    declaration that names no model — `{404: {"description": "..."}}` — documents an
    untyped body for a response whose shape we know exactly.
    """
    untyped = [
        f"{route} — {code} declares no ErrorDetail model"
        for route in documented
        for code, response in route.declared.items()
        if int(code) >= 400
        and int(code) != _GENERATED
        and response.get("model") is not ErrorDetail
    ]
    assert not untyped, "Failures with no body schema:\n" + "\n".join(untyped)


def test_the_schema_a_client_generator_reads_carries_the_codes(app: FastAPI) -> None:
    """End to end through `app.openapi()` — the artifact, not the route objects.

    The three examples here are the ones that prompted this work: they were returned by
    the API and absent from the spec.
    """
    schema = app.openapi()
    assert "ErrorDetail" in schema["components"]["schemas"]

    expected = {
        ("/api/v1/auth/login", "post"): 401,  # "Invalid credentials"
        ("/api/v1/portal/auth/otp/verify", "post"): 400,  # "Invalid or expired code"
        ("/api/v1/public/offers/{offer_id}", "get"): 404,  # "Offer not found"
    }
    for (path, method), code in expected.items():
        responses = schema["paths"][path][method]["responses"]
        assert str(code) in responses, f"{method.upper()} {path} does not document {code}"
        media = responses[str(code)]["content"]["application/json"]
        assert media["schema"]["$ref"].endswith("/ErrorDetail")
        # The example is the real `detail` string, copied from the handler.
        assert media["example"]["detail"]
