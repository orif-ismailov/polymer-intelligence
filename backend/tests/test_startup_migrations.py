"""Tests for the startup migration lifespan hook (SC#2).

The FastAPI lifespan applies the locked schema on startup only when
settings.RUN_MIGRATIONS_ON_STARTUP is true. The flag defaults false so the
TestClient-built app never reaches for a database during the suite/CI.

Imports of app.core.config / app.main are deferred into the test bodies so
Settings() is constructed under the session-autouse patch_env fixture (matching
the conftest pattern) rather than at collection time.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_lifespan_skips_migrations_when_flag_false() -> None:
    """Default RUN_MIGRATIONS_ON_STARTUP=False: run_migrations is never called."""
    from app.core.config import settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    with (
        patch.object(settings, "RUN_MIGRATIONS_ON_STARTUP", False),
        patch("app.entrypoint.run_migrations") as mock_run,
    ):
        app = create_app()
        with TestClient(app):
            pass
        mock_run.assert_not_called()


def test_lifespan_runs_migrations_when_flag_true() -> None:
    """RUN_MIGRATIONS_ON_STARTUP=True: lifespan invokes the advisory-locked runner once."""
    from app.core.config import settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    with (
        patch.object(settings, "RUN_MIGRATIONS_ON_STARTUP", True),
        patch("app.entrypoint.run_migrations", return_value="0001") as mock_run,
    ):
        app = create_app()
        with TestClient(app):
            pass
        mock_run.assert_called_once()
