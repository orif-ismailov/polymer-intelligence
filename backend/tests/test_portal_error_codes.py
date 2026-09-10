"""One business rule must refuse in one shape, wherever it is enforced (IMEX-7).

`company_not_verified` is raised from five routers across four bounded contexts —
publishing an offer, quoting on a tender, accepting a quote, drawing up a contract,
turning a sample into a deal. Four of them answered `422 {"detail": "company_not_verified"}`
and one answered `403 {"detail": {"code": "company_not_verified"}}`, so a client could
not read the code without a branch per endpoint, and 422 told it the request body was
wrong when the body was fine and the company was not.

The fix is a single helper (`app/api/portal/deps.py::company_not_verified`), and the
half worth a test is that it STAYS single. Nothing in Python stops the sixth site from
typing the string itself, and the drift is silent: every endpoint keeps working, only
the client's error handling rots. So the guard is a source scan — the literal lives in
exactly one module, and a new call site either imports the helper or fails here.

The end-to-end checks (an unverified company actually getting a 403 from each route)
need a database and live beside the other route tests in `test_portal_offers_api.py`,
`test_portal_deals_api.py`, `test_contracts_api.py` and `test_samples_api.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from app.api.portal.deps import company_not_verified
from app.core.paths import BACKEND_ROOT

#: The one module allowed to spell the code out.
_HOME = Path("app/api/portal/deps.py")

#: A quoted occurrence of the code — the helper's name is an identifier, not a literal,
#: so importing and calling it does not trip this.
_LITERAL = re.compile(r"""['"]company_not_verified['"]""")


def test_helper_answers_403_with_a_typed_body() -> None:
    exc = company_not_verified()

    assert isinstance(exc, HTTPException)
    # 403, not 422: the caller authenticated, and the body they sent was fine.
    assert exc.status_code == 403
    assert exc.detail == {
        "code": "company_not_verified",
        "message": "Company is not verified",
    }


def test_the_code_is_written_out_in_exactly_one_module() -> None:
    """A second spelling of the literal is a second shape waiting to happen."""
    offenders = sorted(
        str(path.relative_to(BACKEND_ROOT))
        for path in (BACKEND_ROOT / "app").rglob("*.py")
        if path.relative_to(BACKEND_ROOT) != _HOME
        and _LITERAL.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == [], (
        "`company_not_verified` is spelled out outside "
        f"{_HOME} in {offenders} — raise `portal.deps.company_not_verified()` instead, "
        "so every endpoint refuses in the same shape (IMEX-7)."
    )


def test_every_router_that_catches_the_rule_raises_through_the_helper() -> None:
    """The other direction: a site that catches `CompanyNotVerified` must use the helper.

    The literal scan above cannot see a handler that invents a THIRD shape without
    naming the code (`detail="not verified"`), which is the same bug wearing different
    prose. Pairing every `except …CompanyNotVerified` with a `company_not_verified()`
    in the same file closes that.
    """
    catchers = sorted(
        path
        for path in (BACKEND_ROOT / "app").rglob("*.py")
        if "CompanyNotVerified as exc" in path.read_text(encoding="utf-8")
    )
    # Four routers today; the assert is about each one, not the count.
    assert catchers, "no router catches CompanyNotVerified — did the exception get renamed?"

    for path in catchers:
        source = path.read_text(encoding="utf-8")
        assert "company_not_verified() from exc" in source, (
            f"{path.relative_to(BACKEND_ROOT)} catches CompanyNotVerified but does not "
            "raise `company_not_verified()` — see IMEX-7."
        )
