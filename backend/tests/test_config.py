"""
Unit tests for app.core.config — Settings class.

Verifies that Settings reads the full documented env contract and that
TZ_DISPLAY defaults to Asia/Tashkent.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest

# Minimum required env vars — secrets that have no defaults
_REQUIRED_SECRETS = {
    "DATABASE_URL": "postgresql+psycopg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "BOT_TOKEN": "123:test",
    "WEBHOOK_SECRET": "test_webhook_secret_12345678901234",
    "TG_API_ID": "12345678",
    "TG_API_HASH": "abcdef1234567890",
    "JWT_SECRET": "test_jwt_secret_64_chars_at_least_here_more_padding_to_fill",
    "S3_ACCESS_KEY": "minio_access",
    "S3_SECRET_KEY": "minio_secret",
}


def _make_settings(**overrides: str):
    """Import a fresh Settings instance with monkeypatched env vars."""
    # Unset any real .env so the test environment is fully controlled.
    env = {**_REQUIRED_SECRETS, **overrides}
    # Prevent pydantic-settings from reading a real .env file
    env["PYDANTIC_SETTINGS_ENV_FILE"] = ""

    with patch.dict(os.environ, env, clear=False):
        # Force re-import to pick up the patched env (Settings reads env at instantiation)
        import app.core.config as cfg_module  # noqa: PLC0415

        return cfg_module.Settings(_env_file=None)


class TestSettingsDefaults:
    def test_tz_display_defaults_to_asia_tashkent(self) -> None:
        """TZ_DISPLAY must default to 'Asia/Tashkent' when not set in env."""
        settings = _make_settings()
        assert settings.TZ_DISPLAY == "Asia/Tashkent"

    def test_llm_extract_model_default(self) -> None:
        settings = _make_settings()
        assert settings.LLM_EXTRACT_MODEL == "claude-haiku-4-5"

    def test_llm_report_model_default(self) -> None:
        settings = _make_settings()
        assert settings.LLM_REPORT_MODEL == "claude-sonnet-4-5"

    def test_llm_daily_token_limit_default(self) -> None:
        settings = _make_settings()
        assert settings.LLM_DAILY_TOKEN_LIMIT == 500_000

    def test_s3_bucket_default(self) -> None:
        settings = _make_settings()
        assert settings.S3_BUCKET == "polymer-files"

    def test_sentry_dsn_default_empty(self) -> None:
        """SENTRY_DSN defaults to empty string (Sentry disabled)."""
        settings = _make_settings()
        assert settings.SENTRY_DSN == ""


class TestSettingsReadsEnv:
    def test_reads_database_url(self) -> None:
        url = "postgresql+psycopg://user:pass@host/db"
        settings = _make_settings(DATABASE_URL=url)
        assert settings.DATABASE_URL == url

    def test_reads_redis_url(self) -> None:
        url = "redis://redis-host:6379/1"
        settings = _make_settings(REDIS_URL=url)
        assert settings.REDIS_URL == url

    def test_reads_tg_api_id_as_int(self) -> None:
        """TG_API_ID is declared as int, so it must be coerced from env string."""
        settings = _make_settings(TG_API_ID="99887766")
        assert settings.TG_API_ID == 99887766
        assert isinstance(settings.TG_API_ID, int)

    def test_reads_custom_tz_display(self) -> None:
        settings = _make_settings(TZ_DISPLAY="UTC")
        assert settings.TZ_DISPLAY == "UTC"

    def test_reads_llm_daily_token_limit_as_int(self) -> None:
        settings = _make_settings(LLM_DAILY_TOKEN_LIMIT="100000")
        assert settings.LLM_DAILY_TOKEN_LIMIT == 100_000

    def test_invalid_tz_display_raises(self) -> None:
        """Invalid timezone name must raise a validation error at instantiation."""
        with pytest.raises(Exception):  # pydantic ValidationError
            _make_settings(TZ_DISPLAY="Not/ATimezone")


class TestRequiredSecrets:
    """Each required secret, when absent, should cause Settings() to raise."""

    @pytest.mark.parametrize("secret_key", [
        "DATABASE_URL",
        "REDIS_URL",
        "ANTHROPIC_API_KEY",
        "BOT_TOKEN",
        "WEBHOOK_SECRET",
        "TG_API_ID",
        "TG_API_HASH",
        "JWT_SECRET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
    ])
    def test_missing_required_raises(self, secret_key: str) -> None:
        """A missing required secret must cause Settings() to raise ValidationError."""
        env_without_secret = {k: v for k, v in _REQUIRED_SECRETS.items() if k != secret_key}
        env_without_secret["PYDANTIC_SETTINGS_ENV_FILE"] = ""

        with patch.dict(os.environ, env_without_secret, clear=True):
            import app.core.config as cfg_module  # noqa: PLC0415
            with pytest.raises(Exception):  # pydantic ValidationError
                cfg_module.Settings(_env_file=None)
