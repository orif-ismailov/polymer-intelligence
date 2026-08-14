"""Sentry initialisation.

`SENTRY_DSN` has been in the env contract since Phase 1 and was read by nothing:
`config.py` declared it and no module referenced it. Production therefore had no
error tracking — an unhandled 500 produced a JSON log line on stdout and nothing
tying it to a user, a request, or the Celery task it spawned.

Called from `create_app()` (api) and from the Celery worker's startup, because
they are separate processes and each needs its own init.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry(component: str) -> bool:
    """Initialise Sentry when a DSN is configured. Returns True if it was.

    Args:
        component: "api" or "worker" — reported as the `component` tag so the two
            processes are distinguishable in the issue stream.

    No DSN (dev, CI, and any deployment that has not opted in) is a silent no-op,
    which is what keeps the test suite and a bare `docker compose up` free of
    network calls. A BAD dsn is not silent: the SDK raises at init, and that is
    the right outcome — a typo in the one variable that decides whether errors
    are visible should fail loudly at startup rather than look like a quiet
    system.
    """
    if not settings.SENTRY_DSN:
        return False

    import sentry_sdk  # noqa: PLC0415 — import cost only when actually enabled

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        # `send_default_pii` stays OFF. This app handles phone numbers, PINFL,
        # bank accounts and company documents; shipping request bodies and
        # headers to a third party by default is not a decision to make silently
        # in a helper function.
        send_default_pii=False,
        environment="development" if settings.DEBUG else "production",
        # Errors are the point; tracing is opt-in and off by default so enabling
        # error reporting does not quietly start sampling every request.
        traces_sample_rate=0.0,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("sentry.initialised", extra={"component": component})
    return True
