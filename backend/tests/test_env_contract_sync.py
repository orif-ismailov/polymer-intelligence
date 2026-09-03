"""`deploy/.env.example` is the env contract — keep it honest.

The file calls itself authoritative and CLAUDE.md points operators at it, but
nothing enforced that, so it drifted: at the time this test was written ten
`Settings` fields were absent from it — every `DIDOX_*`, every `EIMZO_*`,
`ESCROW_WEBHOOK_SECRET`, `OTP_DEV_CODE` and `REPORT_PROMPT_VERSION`.

An undocumented setting is a setting nobody knows they can set, which is how
`gov_registry_mode` came to be discoverable only by reading Python. A documented
key that maps to nothing is the mirror failure: someone sets it and believes it
took effect.

Not every documented key is a `Settings` field, though — `_NON_SETTINGS_KEYS`
below is the deliberate exception list, and it is short on purpose. Anything
added to it must be consumed by something OTHER than the Python app, with the
consumer named.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings

#: Repo root — this file is backend/tests/, so up three.
_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / "deploy" / ".env.example"

#: Documented keys with no `Settings` field because something else consumes
#: them. Each names its consumer; nothing goes in here without one.
_NON_SETTINGS_KEYS = frozenset(
    {
        # docker-compose interpolates these directly into service definitions.
        "API_WORKERS",  # deploy/docker-compose.yml — uvicorn --workers
        "CELERY_CONCURRENCY",  # both compose files — celery --concurrency
        "POSTGRES_MAX_CONNECTIONS",  # deploy/docker-compose.yml — postgres -c
        # The Postgres image's own bootstrap variables.
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        # Read by app/seed/seed_staff.py through os.environ, because the name is
        # data: it comes from the `password_env` field of each record in
        # seed/data/staff_users.json, so it cannot be a fixed Settings field.
        "SEED_ADMIN_PASSWORD",
    }
)


def _documented_keys() -> set[str]:
    """Every `KEY=` in the example, including commented-out optional ones.

    A `# OPTIONAL_KEY=` line still documents the key, which is the point of the
    file; only prose comments are skipped.
    """
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))


def _settings_fields() -> set[str]:
    return set(Settings.model_fields)


def _panel_managed() -> set[str]:
    """Settings the panel owns, deliberately absent from the contract file.

    Their defaults live on `Settings`, where the type, bounds and `Literal` sets
    are declared too, and their values are edited at `/admin/settings` — the
    credentials among them stored Fernet-encrypted rather than in plaintext here.

    `ANTHROPIC_API_KEY` is the one exception and is NOT in this set: see
    `test_the_required_key_is_still_documented`.
    """
    from app.services import settings_service  # noqa: PLC0415

    return {
        spec.env_var
        for spec in settings_service.SPECS.values()
        if spec.overridable and spec.env_var != "ANTHROPIC_API_KEY"
    }


def test_every_setting_is_documented() -> None:
    """A field you cannot find in the contract is a field nobody will set —
    unless the panel is where it is meant to be found."""
    missing = sorted(_settings_fields() - _documented_keys() - _panel_managed())
    assert not missing, (
        "these Settings fields are missing from deploy/.env.example: "
        + ", ".join(missing)
    )


def test_no_documented_key_is_dead() -> None:
    """A key in the contract that maps to nothing reads as configuration and is not."""
    dead = sorted(_documented_keys() - _settings_fields() - _NON_SETTINGS_KEYS)
    assert not dead, (
        "deploy/.env.example documents keys that are not Settings fields "
        "(and not in the compose-only allowlist): " + ", ".join(dead)
    )


def test_no_runtime_switch_is_listed_in_the_contract() -> None:
    """The inverse of what this test used to assert, and deliberately so.

    The switches were enumerated here with their defaults, which meant the default
    existed in two places: the `Settings` field that supplies it and validates it,
    and a line in this file that only restated it. They are edited at
    `/admin/settings` now and the file points there instead.

    A reintroduced line is not harmless: it is a second copy of a default that
    something else owns, which is the drift this repo already paid for once when
    `.env` and `backend/.env` disagreed on ten keys. `make env-sync` removes it.
    """
    listed = sorted(_panel_managed() & _documented_keys())
    assert not listed, (
        "these switches are edited at /admin/settings and should not be listed in "
        "deploy/.env.example — run `make env-sync`: " + ", ".join(listed)
    )


def test_the_required_key_is_still_documented() -> None:
    """The counterweight to the rule above, and the one with teeth.

    Every other panel-managed setting can live only in the panel, because
    `settings_service` falls back to the `Settings` default when no override
    exists. `ANTHROPIC_API_KEY` cannot: it is REQUIRED, and `Settings` validates
    at import — before anything has connected to the database the override would
    live in. Drop it from the contract and a deployment that copied this file
    fails to boot, with nothing in the file to say why and a panel it cannot
    reach to find out.
    """
    assert "ANTHROPIC_API_KEY" in _documented_keys(), (
        "ANTHROPIC_API_KEY must stay in deploy/.env.example — it is required at "
        "startup and no admin-panel override can precede validation"
    )


def test_only_the_required_credential_is_listed() -> None:
    """The other three are set in the panel, encrypted at rest rather than
    sitting in plaintext in a file that gets copied around."""
    from app.services import settings_service  # noqa: PLC0415

    optional_credentials = {
        spec.env_var
        for spec in settings_service.SPECS.values()
        if spec.overridable and spec.sensitive and spec.env_var != "ANTHROPIC_API_KEY"
    }
    listed = sorted(optional_credentials & _documented_keys())
    assert not listed, (
        "these credentials are set at /admin/settings and should not be listed in "
        "deploy/.env.example: " + ", ".join(listed)
    )


# ── The mechanical half, kept in sync by a tool ───────────────────────────────
#
# The tests above check PRESENCE. These check the parts a human maintains by hand
# and therefore gets wrong: the `[panel: X]` markers, and whether a documented
# value is one `Settings` would actually accept.


def _sync_module():  # type: ignore[no-untyped-def]
    """`scripts/sync_env_example.py`, imported by path — it is a repo script, not
    a package, and importing it here is what makes the guard runnable in CI."""
    import importlib.util  # noqa: PLC0415

    path = Path(__file__).resolve().parents[2] / "scripts" / "sync_env_example.py"
    spec = importlib.util.spec_from_file_location("sync_env_example", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_panel_markers_are_in_sync() -> None:
    """`[panel: X]` says where a variable is editable, and the answer changes
    whenever a spec is added or regrouped.

    A stale marker is worse than none: it sends an operator to a page the setting
    is not on, and reading the file cannot reveal that. `make env-sync` fixes it.
    """
    assert _sync_module().sync(check=True) == 0, (
        "deploy/.env.example has stale [panel: X] markers — run `make env-sync`"
    )


def test_the_marker_guard_can_actually_fail(tmp_path: Path) -> None:
    """A check that always passes is a check nobody should trust.

    Feeds the tool a copy with one marker removed and asserts it notices.
    """
    module = _sync_module()
    doctored = tmp_path / ".env.example"

    # An ASSIGNMENT line, not the legend — the header explains the `[panel: X]`
    # notation and contains the literal too. Stripping that one changes nothing
    # the tool looks at, and the first version of this test did exactly that and
    # passed for the wrong reason.
    lines = _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    victim = next(
        i for i, line in enumerate(lines)
        if re.match(r"^[A-Z0-9_]+=", line) and "[panel:" in line
    )
    lines[victim] = re.sub(r"\[panel: \w+\] ?", "", lines[victim])
    doctored.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert module.sync(check=True, path=doctored) == 1, (
        "the sync tool did not notice a removed marker — the guard has no teeth"
    )


def test_every_documented_value_is_one_settings_would_accept() -> None:
    """The file says «copy this to .env», so a value here that fails validation
    is a boot failure handed to whoever followed the instruction.

    NOT an equality check against the code default: `S3_ENDPOINT` deliberately
    documents the compose address where the field defaults to empty, and
    `CORS_ALLOWED_ORIGINS` documents the comma-separated form a `mode="before"`
    validator splits into a list. Both are correct and neither equals its default,
    so a mirror test would fail on two entries that are doing their job.

    Secrets are skipped — their values are `replace_me` placeholders on purpose,
    and several are shorter than the minimum length they document.
    """
    from pydantic import ValidationError  # noqa: PLC0415

    lines = _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    secret_lines = {
        m.group(1)
        for line in lines
        if "[SECRET]" in line and (m := re.match(r"^([A-Z0-9_]+)=", line))
    }
    documented = {
        m.group(1): m.group(2).split("#")[0].strip()
        for line in lines
        if (m := re.match(r"^([A-Z0-9_]+)=(.*)$", line))
    }

    # A complete, valid baseline so only the field under test can be at fault.
    baseline: dict[str, object] = {
        n: f.default for n, f in Settings.model_fields.items() if not f.is_required()
    }
    baseline |= {n: "x" * 64 for n, f in Settings.model_fields.items() if f.is_required()}

    rejected = []
    for name, value in documented.items():
        if name not in Settings.model_fields or name in secret_lines or value == "":
            continue
        try:
            Settings.model_validate({**baseline, name: value})
        except ValidationError as exc:
            reasons = [e["msg"] for e in exc.errors() if e["loc"] and e["loc"][0] == name]
            if reasons:
                rejected.append(f"{name}={value!r} ({reasons[0]})")

    assert not rejected, (
        "deploy/.env.example documents values Settings would refuse at boot: "
        + "; ".join(rejected)
    )
