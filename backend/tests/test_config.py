"""
Unit tests for app.core.config — Settings class.

Verifies that Settings reads the full documented env contract and that
TZ_DISPLAY defaults to Asia/Tashkent.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

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
    "VERIFICATION_ENC_KEY": "cG9seW1lcl92ZXJpZmljYXRpb25fdGVzdF9rZXlfMzI=",
}


def _make_settings(**overrides: str):
    """Import a fresh Settings instance with monkeypatched env vars."""
    # Fully control the env: clear=True so ambient/CI-injected vars (e.g. the
    # backend job exports S3_BUCKET=ci-bucket) cannot leak in and shadow the
    # declared defaults this helper exists to test. Only _REQUIRED_SECRETS plus
    # any explicit overrides are visible to Settings.
    env = {**_REQUIRED_SECRETS, **overrides}
    # Prevent pydantic-settings from reading a real .env file
    env["PYDANTIC_SETTINGS_ENV_FILE"] = ""

    with patch.dict(os.environ, env, clear=True):
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
        assert url == settings.DATABASE_URL

    def test_reads_redis_url(self) -> None:
        url = "redis://redis-host:6379/1"
        settings = _make_settings(REDIS_URL=url)
        assert url == settings.REDIS_URL

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
        with pytest.raises(ValidationError):
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
        "VERIFICATION_ENC_KEY",
    ])
    def test_missing_required_raises(self, secret_key: str) -> None:
        """A missing required secret must cause Settings() to raise ValidationError."""
        env_without_secret = {k: v for k, v in _REQUIRED_SECRETS.items() if k != secret_key}
        env_without_secret["PYDANTIC_SETTINGS_ENV_FILE"] = ""

        with patch.dict(os.environ, env_without_secret, clear=True):
            import app.core.config as cfg_module  # noqa: PLC0415
            with pytest.raises(ValidationError):
                cfg_module.Settings(_env_file=None)


class TestJwtSecretValidator:
    """JWT_SECRET field_validator rejects secrets shorter than 32 characters."""

    def test_short_jwt_secret_raises_validation_error(self) -> None:
        """Settings() with a JWT_SECRET shorter than 32 chars must raise a ValidationError."""
        short_secret = "short_secret_31_chars_xxxxxxxx!"  # exactly 31 chars
        assert len(short_secret) == 31, f"Test precondition failed: len={len(short_secret)}"
        with pytest.raises(ValidationError):
            _make_settings(JWT_SECRET=short_secret)

    def test_jwt_secret_exactly_32_chars_succeeds(self) -> None:
        """Settings() with a JWT_SECRET of exactly 32 chars must succeed."""
        secret_32 = "a" * 32
        assert len(secret_32) == 32
        settings = _make_settings(JWT_SECRET=secret_32)
        assert secret_32 == settings.JWT_SECRET

    def test_jwt_secret_longer_than_32_chars_succeeds(self) -> None:
        """Settings() with a JWT_SECRET longer than 32 chars must succeed."""
        secret_long = "ci-jwt-secret-placeholder-32chars!!"
        assert len(secret_long) >= 32
        settings = _make_settings(JWT_SECRET=secret_long)
        assert secret_long == settings.JWT_SECRET


class TestVerificationEncKeyValidator:
    """VERIFICATION_ENC_KEY (R1) is required and rejected below 32 chars."""

    def test_short_key_raises(self) -> None:
        short = "a" * 31
        assert len(short) == 31
        with pytest.raises(ValidationError):
            _make_settings(VERIFICATION_ENC_KEY=short)

    def test_exactly_32_chars_succeeds(self) -> None:
        key_32 = "a" * 32
        settings = _make_settings(VERIFICATION_ENC_KEY=key_32)
        assert key_32 == settings.VERIFICATION_ENC_KEY


class TestSmsProviderSettings:
    """SMS_PROVIDER default + Eskiz-credential model validator (R1)."""

    def test_sms_provider_defaults_to_console(self) -> None:
        settings = _make_settings()
        assert settings.SMS_PROVIDER == "console"

    def test_otp_tunables_have_baseline_defaults(self) -> None:
        settings = _make_settings()
        assert settings.OTP_TTL_SECONDS == 300
        assert settings.OTP_RESEND_COOLDOWN_SECONDS == 60
        assert settings.OTP_MAX_SENDS_PER_DAY == 5
        assert settings.OTP_MAX_VERIFY_ATTEMPTS == 5
        assert settings.PORTAL_SESSION_TTL_DAYS == 30

    def test_eskiz_without_credentials_raises(self) -> None:
        """SMS_PROVIDER=eskiz with no creds must fail fast at startup."""
        with pytest.raises(ValidationError):
            _make_settings(SMS_PROVIDER="eskiz")

    def test_eskiz_with_only_email_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(SMS_PROVIDER="eskiz", ESKIZ_EMAIL="a@b.uz")

    def test_eskiz_with_both_credentials_succeeds(self) -> None:
        settings = _make_settings(
            SMS_PROVIDER="eskiz", ESKIZ_EMAIL="a@b.uz", ESKIZ_PASSWORD="secret"
        )
        assert settings.SMS_PROVIDER == "eskiz"

    def test_console_ignores_missing_credentials(self) -> None:
        """The default console driver needs no Eskiz creds."""
        settings = _make_settings(SMS_PROVIDER="console")
        assert settings.ESKIZ_EMAIL == ""

    def test_blank_verification_notify_chat_id_is_none(self) -> None:
        settings = _make_settings(VERIFICATION_NOTIFY_CHAT_ID="")
        assert settings.VERIFICATION_NOTIFY_CHAT_ID is None


class TestCiEnvContract:
    """Regression tests asserting the CI workflow's S3 env key matches Settings.S3_ENDPOINT.

    Parses .github/workflows/ci.yml and verifies that the backend job's pytest
    step exports exactly the same env name that Settings.S3_ENDPOINT reads.
    Fails if either side is renamed without updating the other (REVIEW CR-01).
    """

    def _ci_yaml_text(self) -> str:
        """Return the raw text of .github/workflows/ci.yml, or skip if not found."""
        import pathlib

        ci_path = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip(f"ci.yml not found at {ci_path} — skipping CI contract test")
        return ci_path.read_text()

    def test_ci_s3_endpoint_key_present(self) -> None:
        """CI must export S3_ENDPOINT (the exact Settings field name) in the pytest env block.

        Uses text-based parsing (no PyYAML dependency) to locate the env key in the
        backend job's pytest step. Checks that the key 'S3_ENDPOINT:' appears in the
        workflow file and that the value is non-empty (http://localhost:9000).
        """
        text = self._ci_yaml_text()
        assert "S3_ENDPOINT:" in text, (
            "CI backend pytest step is missing 'S3_ENDPOINT' env key; "
            "settings.S3_ENDPOINT will silently fall back to '' in CI"
        )
        # Verify the key is followed by a non-empty URL value
        import re
        match = re.search(r"S3_ENDPOINT:\s*(\S+)", text)
        assert match and match.group(1), (
            "S3_ENDPOINT key found in ci.yml but has no value; "
            "settings.S3_ENDPOINT needs a non-empty endpoint URL"
        )

    def test_ci_s3_endpoint_url_absent(self) -> None:
        """CI must NOT export the old mismatched name S3_ENDPOINT_URL (CR-01 regression guard)."""
        text = self._ci_yaml_text()
        assert "S3_ENDPOINT_URL" not in text, (
            "CI backend pytest step exports 'S3_ENDPOINT_URL' (the old drifted name); "
            "rename it to 'S3_ENDPOINT' to match the Settings field"
        )

    def test_ci_s3_endpoint_name_matches_settings_field(self) -> None:
        """The CI env name S3_ENDPOINT must be a declared field on Settings.

        This is the link that makes env-name drift impossible to reintroduce
        silently: renaming the Settings field without updating ci.yml (or vice
        versa) will fail this test.
        """
        from app.core.config import Settings

        assert "S3_ENDPOINT" in Settings.model_fields, (
            "'S3_ENDPOINT' is not a declared field on Settings; "
            "either ci.yml or config.py was renamed without updating the other"
        )


class TestCorsAllowedOriginsValidator:
    """CORS_ALLOWED_ORIGINS setting: non-wildcard default, comma-separated env parsing."""

    def test_cors_allowed_origins_default_is_non_wildcard(self) -> None:
        """CORS_ALLOWED_ORIGINS must default to a non-empty list that does NOT contain '*'."""
        settings = _make_settings()
        origins = settings.CORS_ALLOWED_ORIGINS
        assert isinstance(origins, list), "CORS_ALLOWED_ORIGINS must be a list"
        assert len(origins) > 0, "CORS_ALLOWED_ORIGINS must have at least one entry"
        assert "*" not in origins, (
            f"CORS_ALLOWED_ORIGINS must not contain '*', got: {origins}"
        )

    def test_cors_allowed_origins_parses_comma_separated_env(self) -> None:
        """CORS_ALLOWED_ORIGINS parses a comma-separated env value into a list of origins."""
        env_value = "http://localhost:3000,https://dashboard.example.com"
        settings = _make_settings(CORS_ALLOWED_ORIGINS=env_value)
        origins = settings.CORS_ALLOWED_ORIGINS
        assert isinstance(origins, list), "CORS_ALLOWED_ORIGINS must be a list"
        assert len(origins) == 2, f"Expected 2 origins, got: {origins}"
        assert "http://localhost:3000" in origins
        assert "https://dashboard.example.com" in origins
