"""A route that answers 409 must say so in the schema (IMEX-10).

The ИКПУ endpoints refuse with `409 didox_session_required` when the acting company
holds no live Didox `user-key`. The behaviour is right — the picker has nothing to
search without a session, and a named refusal is better than an empty list. What was
wrong is that the schema declared only 200/401/403/422, so a generated client had no
branch for *the single most likely answer* on that screen and handled the normal case
as an unexpected error.

This is the same class of defect as the missing 404 in IMEX-9, and it recurs the same
way: `responses=` is per-route hand-work, and a new route simply omits it. So rather
than pinning today's list, the check DERIVES the expectation — any handler whose body
can raise `HTTP_409_CONFLICT`, directly or through a helper in its own module, must
declare 409. A twelfth Didox route lands here rather than in a QA report.

Deliberately NOT asserting the reverse (declared-but-unreachable): `errors.py` says a
router-level set may legitimately over-declare for uniformity, and the ИКПУ router
declares 409 router-wide because all three of its routes really do open with the same
guard.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.core.paths import BACKEND_ROOT

#: The two routers on the Didox rail. Both are portal-facing and both refuse with a
#: 409 carrying a stable code rather than prose.
_MODULES = [
    pathlib.Path("app/domains/marketplace/api_portal_ikpu.py"),
    pathlib.Path("app/domains/edi/api_portal.py"),
]


def _module_helpers_that_409(tree: ast.Module, source: str) -> set[str]:
    """Module-level functions that can raise 409 — the guards routes delegate to.

    `_session_or_409` and `_guard` are exactly why the raise is invisible at the
    route: the handler's own body contains no 409 at all.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and "HTTP_409_CONFLICT" in (ast.get_source_segment(source, node) or "")
    }


def _handlers_that_can_409(path: pathlib.Path) -> set[str]:
    """Handler names in this module whose body can answer 409.

    Directly, or via a module-level guard — `_session_or_409` and `_guard` are
    exactly why the raise is invisible at the route.
    """
    source = (BACKEND_ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    helpers = _module_helpers_that_409(tree, source)

    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not [d for d in node.decorator_list if isinstance(d, ast.Call)]:
            continue
        body = ast.get_source_segment(source, node) or ""
        # Drop the decorator, so a `responses=` argument is not read as a raise site.
        body_only = body[body.index("def ") :] if "def " in body else body
        if "HTTP_409_CONFLICT" in body_only or any(f"{h}(" in body_only for h in helpers):
            found.add(node.name)
    return found


@pytest.mark.parametrize("module", _MODULES, ids=lambda p: p.stem)
def test_every_route_that_can_409_declares_it(module: pathlib.Path) -> None:
    """Asserted against the GENERATED SCHEMA, not the decorator.

    The declaration can legitimately be made in two places — per-route, or once at
    `include_router` for a router where every route shares the guard (the ИКПУ one).
    Reading the decorator would call the second form a failure, which is how the
    first draft of this test managed to fail on correct code.
    """
    from app.main import create_app  # noqa: PLC0415

    can_409 = _handlers_that_can_409(module)
    assert can_409, f"no 409-capable route found in {module} — did the guards move?"

    app = create_app()
    spec = app.openapi()
    module_name = str(module.with_suffix("")).replace("/", ".")

    undeclared = sorted(
        f"{method} {route.path} ({route.endpoint.__name__})"
        for route in app.routes
        if getattr(route, "endpoint", None) is not None
        and getattr(route.endpoint, "__module__", "") == module_name
        and route.endpoint.__name__ in can_409
        for method in sorted(route.methods - {"HEAD", "OPTIONS"})
        if "409" not in spec["paths"][route.path][method.lower()]["responses"]
    )

    assert undeclared == [], (
        f"{module}: these routes can answer 409 but the schema does not say so: "
        f"{undeclared}. Add `responses=errors.DIDOX_CONFLICT` to the decorator, or "
        "`**errors.DIDOX_CONFLICT` at the router's `include_router` (IMEX-10)."
    )


def test_the_declared_example_is_the_code_clients_branch_on() -> None:
    """`detail` is a stable code here, so the documented example must be one.

    A prose example would teach a client to match on a sentence.
    """
    from app.api import errors  # noqa: PLC0415

    example = errors.DIDOX_CONFLICT[409]["content"]["application/json"]["example"]
    assert example == {"detail": "didox_session_required"}


def test_the_ikpu_routes_from_the_ticket_declare_409() -> None:
    """The two endpoints QA named, checked through the generated schema itself."""
    from app.main import create_app  # noqa: PLC0415

    spec = create_app().openapi()
    for path in (
        "/api/v1/portal/ikpu/search",
        "/api/v1/portal/companies/{company_id}/ikpu/{class_code}/packages",
    ):
        assert "409" in spec["paths"][path]["get"]["responses"], path
