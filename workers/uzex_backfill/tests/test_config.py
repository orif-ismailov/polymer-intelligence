"""Config loading, safety rails, and helpers."""

from __future__ import annotations

import pytest
from uzex_backfill.config import ConfigError, load_config
from uzex_backfill.db import normalize_dsn

_DSN = "postgresql://u:p@localhost/db"


def _base_env(monkeypatch, **overrides):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env = {"DATABASE_URL": _DSN}
    env.update(overrides)
    for key, val in env.items():
        monkeypatch.setenv(key, str(val))
    # Clear any inherited knobs that would perturb assertions.
    for key in ("MIN_ID", "MAX_ID", "DEV_MAX_ID_CAP", "ENV", "RATE_LIMIT_RPS"):
        if key not in env:
            monkeypatch.delenv(key, raising=False)


def test_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_dev_caps_effective_max_id(monkeypatch):
    _base_env(monkeypatch, ENV="dev", MAX_ID=400000, DEV_MAX_ID_CAP=1000)
    config = load_config()
    assert config.is_dev
    assert config.effective_max_id == 1000  # hard cap, cannot start a full walk


def test_prod_uses_full_max_id(monkeypatch):
    _base_env(monkeypatch, ENV="prod", MAX_ID=400000)
    config = load_config()
    assert config.effective_max_id == 400000


def test_detail_url_substitution(monkeypatch):
    _base_env(monkeypatch, UZEX_DETAIL_URL="https://uzex.uz/trade/offer/{id}")
    config = load_config()
    assert config.detail_url_for(432367) == "https://uzex.uz/trade/offer/432367"


def test_rate_limit_interval(monkeypatch):
    _base_env(monkeypatch, RATE_LIMIT_RPS=2.0)
    assert load_config().min_request_interval() == pytest.approx(0.5)
    _base_env(monkeypatch, RATE_LIMIT_RPS=0)
    assert load_config().min_request_interval() == 0.0


def test_invalid_range_raises(monkeypatch):
    _base_env(monkeypatch, MIN_ID=100, MAX_ID=10)
    with pytest.raises(ConfigError):
        load_config()


def test_normalize_dsn_strips_driver():
    assert normalize_dsn("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"
    assert normalize_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
