"""`.env` is the only source of a runtime switch (R6 / env-consolidation).

These switches used to be rows in `app_settings` with their defaults written as
Python literals in `settings_service.SPECS`. A fresh database therefore ran on
values nobody had chosen or could see, which is how a healthy, fully-credentialed
Didox integration spent a day answering 503: `gov_registry_mode` had never been
set anywhere, so it resolved to a default buried in a service module.

What these tests pin is the property that replaced it — `settings_service.get`
reads `app.core.config.settings` and nothing else — plus the startup validators
that refuse the two configurations which would reproduce the original symptom
from the other direction (a rail switched on without its credentials).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import settings_service


def _settings(**overrides: object) -> Settings:
    """A fully-populated Settings, so a test can vary exactly one field.

    Mirrors the CI placeholder env: every required secret present and every
    switch at its shipped default.
    """
    base: dict[str, object] = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "ANTHROPIC_API_KEY": "sk-ant-placeholder",
        "BOT_TOKEN": "1:placeholder",
        "WEBHOOK_SECRET": "placeholder",
        "TG_API_ID": 1,
        "TG_API_HASH": "placeholder",
        "JWT_SECRET": "x" * 32,
        "VERIFICATION_ENC_KEY": "y" * 44,
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
    }
    base.update(overrides)
    # `_env_file=None` keeps this hermetic: `Settings` normally layers the repo's
    # `.env` and `backend/.env`, and a developer whose `.env` enables a Didox rail
    # would otherwise see the credential-guard tests pass for the wrong reason.
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


class TestReadsFromEnvOnly:
    def test_get_resolves_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The switch the incident was about, read straight off `settings`."""
        monkeypatch.setattr(settings_service._config, "GOV_REGISTRY_MODE", "didox")
        assert settings_service.get("gov_registry_mode") == "didox"

        monkeypatch.setattr(settings_service._config, "GOV_REGISTRY_MODE", "stub")
        assert settings_service.get("gov_registry_mode") == "stub"

    def test_every_spec_maps_to_a_real_settings_field(self) -> None:
        """No spec may name an env var that does not exist.

        A typo here would resolve to `None` at runtime and read as "switched
        off" — the same class of silent wrongness this whole change removes.
        """
        for spec in settings_service.SPECS.values():
            assert hasattr(settings_service._config, spec.env_var), (
                f"{spec.key} points at Settings.{spec.env_var}, which does not exist"
            )

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError):
            settings_service.get("no_such_setting")

    def test_no_override_means_the_env_value_exactly(self) -> None:
        """The property the whole design rests on.

        This replaced `assert not hasattr(settings_service, "set_many")`, which
        was written when there was no write path at all. That assertion survived
        the arrival of one — the writer is called `set_override` — so it went on
        passing while guarding nothing. What actually has to hold now is not that
        writing is impossible, but that NOT writing leaves `.env` in charge: an
        empty override table has to behave exactly like the build before it.
        """
        settings_service.clear_snapshot()
        for spec in settings_service.SPECS.values():
            assert settings_service.get(spec.key) == getattr(
                settings_service._config, spec.env_var
            ), spec.key

    def test_an_override_wins_and_reset_gives_the_env_value_back(self) -> None:
        """Precedence, in both directions. A one-way override would be a trap."""
        from tests.conftest import set_switch  # noqa: PLC0415

        assert settings_service.get("gov_registry_mode") == "stub"
        set_switch(gov_registry_mode="didox")
        assert settings_service.get("gov_registry_mode") == "didox"
        assert settings_service.env_value("gov_registry_mode") == "stub"
        settings_service.clear_snapshot()
        assert settings_service.get("gov_registry_mode") == "stub"

    def test_a_write_never_mutates_the_settings_singleton(self) -> None:
        """`Settings` sets no `validate_assignment`, so `setattr` would bypass
        every validator in `config.py`. Overrides live in the snapshot; this is
        the assertion that keeps them there."""
        before = settings_service._config.GOV_REGISTRY_MODE
        settings_service.validate("gov_registry_mode", "stub")
        assert before == settings_service._config.GOV_REGISTRY_MODE

    def test_get_opens_no_database_connection(self) -> None:
        """`get()` is called inside open transactions — `verification/service.py`
        holds a `SELECT … FOR UPDATE` across one. With `DB_POOL_SIZE=5` against
        uvicorn's 40-thread pool, a second checkout per call is a deadlock, not a
        slow path, so this is a correctness test rather than a performance one."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch("app.core.db.SessionLocal") as session_local:
            for key in settings_service.SPECS:
                settings_service.get(key)
        session_local.assert_not_called()

    def test_get_all_reports_the_env_var_behind_each_switch(self) -> None:
        """The admin listing has to say WHERE a value comes from.

        Showing an operator `didox_mode = stub` without naming `DIDOX_MODE` just
        moves the hunt somewhere else.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        db = MagicMock()
        db.execute.return_value.all.return_value = []
        by_key = {item["key"]: item for item in settings_service.get_all(db)}
        assert by_key["didox_mode"]["env_var"] == "DIDOX_MODE"
        assert by_key["gov_registry_mode"]["env_var"] == "GOV_REGISTRY_MODE"

    def test_secrets_are_masked_in_the_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A credential's VALUE must not leave the server, in either column.

        The env layer is what is set here, not an override: `get_all` reads the
        TABLE rather than this process's snapshot (so the panel shows stored
        truth rather than a cache), which makes the env value the one a mocked,
        row-less session will render.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        secret = "super-secret-partner-token"
        monkeypatch.setattr(settings_service._config, "DIDOX_PARTNER_TOKEN", secret)
        db = MagicMock()
        db.execute.return_value.all.return_value = []
        by_key = {item["key"]: item for item in settings_service.get_all(db)}
        rendered = str(by_key["didox_partner_token"])
        assert secret not in rendered
        assert "••••" in rendered

    def test_masking_distinguishes_unset_from_hidden(self) -> None:
        """"not set" and "set to something I cannot show you" are different
        facts about a deployment, and this panel exists to tell them apart."""
        assert settings_service.mask("") == ""
        assert settings_service.mask(None) == ""
        assert settings_service.mask("abcdefgh") == "••••efgh"

    def test_every_overridable_key_is_read_through_the_service(self) -> None:
        """A control that silently does nothing is worse than no control.

        Every overridable spec must be reachable through `settings_service`, so
        no call site is left reading the env field directly and ignoring the
        panel. The names below are the accessors the notification call sites use.
        """
        assert settings_service.notify_chat_id() == settings_service.get(
            "request_notify_chat_id"
        )
        assert settings_service.news_channel_id() == str(
            settings_service.get("news_channel_id") or ""
        )


class TestOneEnvFile:
    """There is exactly one `.env`, at the repo root, found by path not by CWD.

    The repo used to carry `./.env` AND `./backend/.env`, and `env_file=".env"`
    resolves against the working directory — so `make dev` (which starts uvicorn
    from `backend/`) and compose (which passes the root file) configured the app
    differently. They disagreed on ten keys including `JWT_SECRET` and the S3
    credentials. `backend/.env` has been merged into the root file and deleted.
    """

    def test_settings_reads_only_the_repo_root_env(self) -> None:
        from app.core.config import Settings
        from app.core.paths import REPO_ROOT

        configured = Settings.model_config["env_file"]
        # A single path, not a tuple/list of layered files.
        assert configured == REPO_ROOT / ".env", (
            "Settings must read exactly one env file, the repo-root one"
        )

    def test_the_env_path_is_absolute(self) -> None:
        """A relative path would resolve against the CWD again, which is the bug."""
        from app.core.config import Settings

        assert Path(str(Settings.model_config["env_file"])).is_absolute()

    def test_no_backend_env_file_has_reappeared(self) -> None:
        """Nothing reads it any more, so one lying around is a trap: an operator
        would edit it and see no effect."""
        from app.core.paths import BACKEND_ROOT

        stray = BACKEND_ROOT / ".env"
        assert not stray.exists(), (
            f"{stray} is back. It is NOT read — everything lives in the repo-root "
            ".env now. Merge it there and delete it."
        )


class TestClosedSetsAndBounds:
    def test_a_typo_in_a_mode_fails_at_startup(self) -> None:
        with pytest.raises(ValidationError):
            _settings(GOV_REGISTRY_MODE="didoks")

    def test_out_of_range_int_is_refused_not_clamped(self) -> None:
        """The old `_coerce` clamped silently; a month on an unchosen number is
        worse than a boot failure."""
        with pytest.raises(ValidationError):
            _settings(NEWS_REFRESH_INTERVAL_MINUTES=1)
        with pytest.raises(ValidationError):
            _settings(RFQ_SUPPLIER_PUSH_TOP_N=0)

    def test_app_env_typo_is_refused(self) -> None:
        """`APP_ENV=prod` used to silently mean "not production", which dropped
        `Secure` from the staff refresh cookie."""
        with pytest.raises(ValidationError):
            _settings(APP_ENV="prod")


class TestRailsRequireTheirCredentials:
    @pytest.mark.parametrize(
        "rail",
        [{"GOV_REGISTRY_MODE": "didox"}, {"DIDOX_MODE": "live"}],
    )
    def test_didox_rail_without_a_token_fails_fast(self, rail: dict[str, str]) -> None:
        with pytest.raises(ValidationError, match="DIDOX_PARTNER_TOKEN"):
            _settings(**rail)

    def test_didox_rail_with_a_token_boots(self) -> None:
        cfg = _settings(GOV_REGISTRY_MODE="didox", DIDOX_PARTNER_TOKEN="tok")
        assert cfg.GOV_REGISTRY_MODE == "didox"

    def test_defaults_need_no_didox_credentials(self) -> None:
        """A deployment that never enables Didox must not be asked for a token."""
        cfg = _settings()
        assert cfg.GOV_REGISTRY_MODE == "stub"
        assert cfg.DIDOX_MODE == "stub"

    def test_live_escrow_without_a_callback_secret_fails_fast(self) -> None:
        with pytest.raises(ValidationError, match="ESCROW_WEBHOOK_SECRET"):
            _settings(ESCROW_MODE="live")

    def test_live_escrow_with_a_secret_boots(self) -> None:
        assert _settings(ESCROW_MODE="live", ESCROW_WEBHOOK_SECRET="s").ESCROW_MODE == "live"
