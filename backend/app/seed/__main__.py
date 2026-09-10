"""Run every core seeder, in FK order, against the configured database.

    python -m app.seed

**This is the one list.** It used to exist in four places, and they had already
drifted: `deploy/docker-compose.yml` ran all five, `deploy/docker-compose.dev.yml`
ran four (no `seed_sources`), and `scripts/dev.sh` ran three — so `make dev` built a
database with no `contract_templates` and no `substances`, which is a database where
the contract chain and the compliance gate cannot be exercised at all. Nobody had
changed a policy; three copies of a list had simply fallen out of step.

Also the *only* way to reseed a running stack. The compose `command` is a pre-start
`&&` chain, so it fires when the api container is RECREATED and at no other time —
`docker compose up -d` on an unchanged image is a no-op. After a database wipe the
api keeps serving happily against empty reference tables, which is exactly what
happened on the dev stand (09.09.2026): every catalogue endpoint answered 200 with
zero rows, and `contract_templates` being empty took the whole signing chain with it.
`make seed` is this module.

Demo and showcase seeders are deliberately absent: they are fixtures, not reference
data, and they carry real passwords. Run those by hand:

    python -m app.seed.seed_showcase          # the full world — PURGES companies,
                                              # accounts, deals, contracts, offers
    python -m app.seed.seed_showcase_news     # classified articles only, additive
    python -m app.seed.seed_showcase_prices   # a weekly quote series only, additive

The distinction matters when choosing one. `seed_showcase` builds a coherent world and
truncates half the schema to do it, so it is for an environment nobody is mid-way
through testing. The satellites each own their rows — a marker in `ai.news`, a
dedicated `manual` source — delete only those on a re-run, and are safe to point at a
live dev stand. `seed_showcase_prices` exists because `price_points` is a DERIVED
table with no write endpoint, so an environment where the aggregation has never run
has no way to obtain prices at all (IMEX-11).

Each seeder owns its own session and commits its own work — `seed_substances` and
`seed_contract_templates` only commit `if own`, so handing them a shared session here
would silently roll their work back. `seed_reference` and `seed_sources` take a
session instead of opening one, so they get a short-lived one apiece.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from app.core.db import SessionLocal

logger = logging.getLogger("app.seed")


def _seed_reference() -> str:
    from app.seed.seed_reference import seed_all  # noqa: PLC0415

    with SessionLocal() as session:
        counts = seed_all(session)
    return ", ".join(f"{k}={v}" for k, v in counts.items())


def _seed_staff() -> str:
    from app.seed.seed_staff import seed_staff  # noqa: PLC0415

    created = seed_staff()
    return f"created={len(created)}"


def _seed_sources() -> str:
    from app.seed.seed_sources import seed_all_sources  # noqa: PLC0415

    with SessionLocal() as session:
        counts = seed_all_sources(session)
    return ", ".join(f"{k}={v}" for k, v in counts.items())


def _seed_contract_templates() -> str:
    from app.seed.seed_contract_templates import seed_contract_templates  # noqa: PLC0415

    created = seed_contract_templates()
    return f"created={len(created)}"


def _seed_substances() -> str:
    from app.seed.seed_substances import seed_substances  # noqa: PLC0415

    outcome = seed_substances()
    return (
        f"created={len(outcome.created)}, updated={len(outcome.updated)}, "
        f"skipped={len(outcome.skipped)}"
    )


#: Ordered by FK dependency. `seed_staff` is second because a database with no
#: administrator cannot be logged into, so it is the one whose failure must surface
#: before the slower seeders run.
SEEDERS: list[tuple[str, Callable[[], str]]] = [
    ("seed_reference", _seed_reference),
    ("seed_staff", _seed_staff),
    ("seed_sources", _seed_sources),
    ("seed_contract_templates", _seed_contract_templates),
    ("seed_substances", _seed_substances),
]


def run_all() -> None:
    """Run every core seeder in order, aborting on the first failure.

    Aborting is deliberate and matches the compose `&&` chain it replaces: a half-
    seeded database is the state that makes a working feature look broken. What is
    new is that the failure NAMES the seeder — in the `&&` chain it was a bare
    traceback between two unrelated log lines.
    """
    for name, seeder in SEEDERS:
        try:
            summary = seeder()
        except Exception:
            logger.exception("seed.failed", extra={"seeder": name})
            print(f"seed: {name} FAILED (see traceback above)", file=sys.stderr)  # noqa: T201
            raise
        print(f"seed: {name} ok — {summary}")  # noqa: T201


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all()
