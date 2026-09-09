"""`seed_staff`'s password guard must gate CREATION, not every run.

The guard refuses to build the bootstrap administrator from the public literal in
`seed/data/staff_users.json` whenever `APP_ENV != "development"`. That is right, and
these tests pin it. What they also pin is where it fires: it used to sit ABOVE the
already-exists check, so a deployment whose admin had been created months earlier
raised on every single start once `SEED_ADMIN_PASSWORD` fell out of its `.env` — and
since the seeder runs inside the api container's pre-start `&&` chain, the raise
aborted the chain and uvicorn never started. A missing variable took the whole API
down to protect a row that was never going to be written.

No database: `_do_seed` only needs a session that can answer the existence query, so
these run everywhere rather than behind the real-Postgres skip.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.models.staff import StaffUser
from app.seed.seed_staff import _do_seed


class _Query:
    def __init__(self, result: object) -> None:
        self._result = result

    def filter(self, *args: object, **kwargs: object) -> _Query:
        return self

    def first(self) -> object:
        return self._result


class _FakeSession:
    """The two calls `_do_seed` makes: the existence query, and add/commit/refresh."""

    def __init__(self, existing: object) -> None:
        self._existing = existing
        self.added: list[Any] = []
        self.committed = False

    def query(self, *args: object) -> _Query:
        return _Query(self._existing)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _no_seed_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test here runs with the env var absent — that is the whole subject."""
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)


def test_existing_admin_does_not_need_the_password_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression: a seeded admin + no env var must be a no-op, not a RuntimeError.

    Above the exists-check this raised, and the raise reached the operator as an api
    container that would not boot.
    """
    monkeypatch.setattr(settings, "APP_ENV", "production")
    session = _FakeSession(existing=object())

    created = _do_seed(session)  # type: ignore[arg-type]

    assert created == []
    assert session.added == []
    assert session.committed is False


def test_creating_an_admin_still_refuses_the_public_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property the guard exists for, unchanged: no admin from a repo literal."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    session = _FakeSession(existing=None)

    with pytest.raises(RuntimeError, match="SEED_ADMIN_PASSWORD is required"):
        _do_seed(session)  # type: ignore[arg-type]

    assert session.added == []


def test_development_still_falls_back_to_the_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local development keeps working with no env var set."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    session = _FakeSession(existing=None)

    created = _do_seed(session)  # type: ignore[arg-type]

    assert len(created) == 1
    user = created[0]
    assert isinstance(user, StaffUser)
    assert user.is_admin is True
    # Hashed, never the literal — argon2 output, not the JSON default.
    assert user.password_hash.startswith("$argon2")
    assert session.committed is True
