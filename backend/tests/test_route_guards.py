"""Every route is authenticated unless it is on the public list.

Auth in this app is opt-in per *function*: each of ~290 path operations declares
its own `Depends(get_current_...)` / `Depends(require_role(...))` parameter. There
is no router-level default, so a new endpoint that simply omits the parameter is
served to anonymous callers — and nothing about the diff looks wrong. This suite
is the control for that: it walks the real route tree and fails on any route that
resolves to no auth dependency and is not in `PUBLIC_ROUTES` below.

Adding a genuinely public endpoint therefore becomes a one-line edit to a list
called PUBLIC_ROUTES, which is a reviewable act. Forgetting a guard becomes a
test failure. That asymmetry is the whole point — the list is not a nuisance to
be topped up, it is the sign-off.

At the time of writing all 31 unguarded routes were deliberately public, so this
suite is regression prevention rather than a fix for a live hole.

TRAVERSAL: FastAPI 0.137 does NOT flatten included routers into `app.routes` —
it inserts `_IncludedRouter` wrappers. A naive `for r in app.routes` sees 2 of
~290 routes and passes vacuously, which is the failure mode this file most needs
to avoid. `_iter_api_routes` recurses through `.original_router.routes`,
accumulating the prefix from `.include_context`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

# Callables that establish an authenticated identity. `_check_role` is the inner
# closure built by `require_role(...)`, so it covers require_admin /
# require_analyst_or_admin and every ad-hoc role guard built from the factory.
AUTH_DEPENDENCIES = frozenset(
    {
        "get_current_staff_user",
        "get_current_staff_user_sse",
        "get_current_account",
        "get_current_client",
        "_check_role",
    }
)

#: Routes served to anonymous callers ON PURPOSE. Each entry is a deliberate
#: product decision, not an oversight — grouped by why it is public.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        # Liveness probe. Returns status enums + the alembic revision, nothing else.
        ("GET", "/api/v1/health"),
        # Staff auth bootstrap. `login` IS the credential check; `refresh`/`logout`
        # authenticate from the httpOnly cookie, which a Depends() cannot express.
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        # Portal (client cabinet) auth bootstrap — same argument, phone-OTP instead
        # of a password. `otp/peek` is an e2e hook double-gated to DEBUG + the
        # console SMS driver, so it 404s anywhere it could matter.
        ("POST", "/api/v1/portal/auth/otp/request"),
        ("POST", "/api/v1/portal/auth/otp/verify"),
        ("POST", "/api/v1/portal/auth/refresh"),
        ("POST", "/api/v1/portal/auth/logout"),
        ("GET", "/api/v1/portal/auth/otp/peek"),
        # Telegram Web App auth bootstrap (Login Widget / initData exchange).
        ("GET", "/api/v1/webapp/auth/config"),
        ("POST", "/api/v1/webapp/auth/telegram"),
        ("POST", "/api/v1/webapp/auth/logout"),
        # The anonymous storefront. Server-rendered for search engines, so every
        # fetch must answer a stranger; visibility is enforced inside the services
        # (approved-only catalog, verified-only directory) and the response models
        # drop seller contact details.
        ("GET", "/api/v1/public/offers"),
        ("GET", "/api/v1/public/offers/{offer_id}"),
        ("GET", "/api/v1/public/categories"),
        ("GET", "/api/v1/public/directories/{slug}"),
        ("GET", "/api/v1/public/directories/{slug}/{company_id}"),
        ("GET", "/api/v1/public/news"),
        ("GET", "/api/v1/public/news/articles"),
        ("GET", "/api/v1/public/news/articles/filters"),
        ("GET", "/api/v1/public/news/articles/{signal_id}"),
        ("GET", "/api/v1/public/prices"),
        ("GET", "/api/v1/public/stats"),
        ("GET", "/api/v1/public/sitemap"),
        # Public marketplace media. These are <img> targets on public catalog
        # pages, so a browser must fetch them with no Authorization header. The
        # handlers resolve only approved offers / verified companies.
        ("GET", "/api/v1/webapp/market/featured"),
        ("GET", "/api/v1/webapp/market/offers/{offer_id}/images/{file_id}"),
        ("GET", "/api/v1/webapp/market/companies/{company_id}/logo"),
        ("GET", "/api/v1/webapp/market/companies/{company_id}/cover"),
        ("GET", "/api/v1/webapp/market/companies/{company_id}/media/{media_id}"),
        # Machine callers that authenticate on a shared secret rather than a JWT,
        # so the credential is checked in the body of the handler, not a Depends().
        # Both 404 (not 401) when unconfigured, so they do not advertise themselves.
        ("POST", "/api/v1/telegram/webhook/{secret}"),
        ("POST", "/api/v1/webhooks/escrow/{provider}"),
    }
)


def _dependency_names(dependant: Any, seen: set[str]) -> set[str]:
    """Every callable name in a route's dependency tree, recursively."""
    call = getattr(dependant, "call", None)
    if call is not None:
        seen.add(getattr(call, "__name__", ""))
    for sub in getattr(dependant, "dependencies", ()):
        _dependency_names(sub, seen)
    return seen


def _iter_api_routes(routes: Any, prefix: str = "") -> list[tuple[str, APIRoute]]:
    """Flatten FastAPI 0.137's `_IncludedRouter` tree into (full_path, route)."""
    found: list[tuple[str, APIRoute]] = []
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            context = getattr(route, "include_context", None)
            found += _iter_api_routes(
                route.original_router.routes, prefix + getattr(context, "prefix", "")
            )
        elif isinstance(route, APIRoute):
            found.append((prefix + route.path, route))
    return found


@pytest.fixture(scope="module")
def api_routes() -> list[tuple[str, str, APIRoute]]:
    from app.main import create_app  # noqa: PLC0415

    app: FastAPI = create_app()
    out: list[tuple[str, str, APIRoute]] = []
    for path, route in _iter_api_routes(app.routes):
        for method in sorted(route.methods or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.append((method, path, route))
    return out


def test_traversal_actually_finds_the_routes(api_routes) -> None:  # noqa: ANN001
    """Guard the guard: a broken walk would make every other test here vacuous.

    If `_iter_api_routes` stops recursing (a FastAPI upgrade renaming
    `_IncludedRouter`, say), it returns the 2 inline routes declared in
    `create_app` and every assertion below trivially passes. The floor is
    deliberately far under the real count so it survives ordinary route churn
    while still catching a traversal that has collapsed.
    """
    assert len(api_routes) > 200, (
        f"only {len(api_routes)} routes found — the router walk is probably broken, "
        "which would make the auth assertions below meaningless"
    )


def test_every_route_is_guarded_or_explicitly_public(api_routes) -> None:  # noqa: ANN001
    """No route may reach an anonymous caller unless PUBLIC_ROUTES says so."""
    unguarded = {
        (method, path)
        for method, path, route in api_routes
        if not (_dependency_names(route.dependant, set()) & AUTH_DEPENDENCIES)
    }
    leaked = unguarded - PUBLIC_ROUTES
    assert not leaked, (
        "These routes have no authentication dependency and are not on the public "
        "list. Either add a guard, or — if the route is meant to be anonymous — add "
        "it to PUBLIC_ROUTES with a comment saying why:\n  "
        + "\n  ".join(f"{m:6} {p}" for m, p in sorted(leaked, key=lambda x: x[1]))
    )


def test_public_list_has_no_stale_entries(api_routes) -> None:
    """PUBLIC_ROUTES must not outlive the routes it exempts.

    A stale entry is a live hazard, not clutter: it silently pre-authorises the
    next route to be given that path, so a future `/api/v1/public/offers` that
    is meant to be guarded would be waved through by a line nobody re-read.
    """
    unguarded = {
        (method, path)
        for method, path, route in api_routes
        if not (_dependency_names(route.dependant, set()) & AUTH_DEPENDENCIES)
    }
    stale = PUBLIC_ROUTES - unguarded
    assert not stale, (
        "PUBLIC_ROUTES entries that no longer match an unguarded route — the route "
        "was removed, renamed, or has since been guarded. Delete them:\n  "
        + "\n  ".join(f"{m:6} {p}" for m, p in sorted(stale, key=lambda x: x[1]))
    )
