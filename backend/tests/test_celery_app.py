"""
Tests for the Celery application configuration.

Verifies:
- The app imports cleanly (no ModuleNotFoundError, no live-broker requirement)
- Queue names exactly match the compose -Q flag: {ingest, parse, notify, default}
- Timezone is Asia/Tashkent with UTC enabled
- Reliability settings: task_acks_late=True, worker_prefetch_multiplier=1
- Serialization: json-only (T-02-01)
"""

from __future__ import annotations


def test_celery_app_imports_cleanly() -> None:
    """app.tasks.celery_app resolves without ModuleNotFoundError or live-broker."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app is not None


def test_queue_names_match_compose_flag() -> None:
    """Queue names must exactly match the compose -Q flag.

    R1 W2 adds the isolated `verify` queue (company verification checks +
    external-provider calls) → -Q ingest,parse,notify,default,verify.
    """
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert queue_names == {"ingest", "parse", "notify", "default", "verify"}, (
        f"Queue names mismatch: {queue_names!r}"
    )


def test_verify_queue_present() -> None:
    """The R1 verify queue must exist so a dead provider can't starve other queues."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert "verify" in {q.name for q in celery_app.conf.task_queues}


def test_verification_tasks_route_to_verify_queue() -> None:
    """app.tasks.verification.* must route onto the verify queue."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_routes["app.tasks.verification.*"] == {"queue": "verify"}


def test_default_queue_is_default() -> None:
    """Default queue must be 'default' to catch unrouted tasks."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_default_queue == "default"


def test_timezone_is_asia_tashkent() -> None:
    """Celery must use Asia/Tashkent for beat schedule evaluation."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.timezone == "Asia/Tashkent"


def test_utc_enabled() -> None:
    """enable_utc must be True so internal timestamps use UTC."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.enable_utc is True


def test_task_acks_late() -> None:
    """task_acks_late must be True (T-02-02 / REQ-nfr-reliability)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_acks_late is True


def test_worker_prefetch_multiplier_is_one() -> None:
    """worker_prefetch_multiplier must be 1 (T-02-02 / REQ-nfr-reliability)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_json_only_serialization() -> None:
    """Serialization must be json-only to refuse pickle (T-02-01)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert list(celery_app.conf.accept_content) == ["json"]


def test_real_tasks_registered() -> None:
    """All five scheduled task names must be registered by the real implementation modules.

    CR-03: placeholders.py was deleted because it registered the same Celery task
    names as the real implementations (ingest.py, ingest_cbu.py, notify.py).
    The real tasks must now be present in the registry on their own.
    """
    import app.tasks.ingest  # noqa: F401, PLC0415 — registers uzex_fetch_* tasks
    import app.tasks.ingest_cbu  # noqa: F401, PLC0415 — registers fetch_cbu_rates
    import app.tasks.notify  # noqa: F401, PLC0415 — registers check_source_health
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    required_names = {
        "uzex_fetch_offers",
        "uzex_fetch_contracts",
        "uzex_fetch_deals",
        "fetch_cbu_rates",
        "check_source_health",
    }
    registered = set(celery_app.tasks.keys())
    missing = required_names - registered
    assert not missing, f"Task names not registered: {missing!r}"


def test_task_track_started() -> None:
    """task_track_started must be True for observability."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_track_started is True


def _declared_task_modules() -> dict[str, list[str]]:
    """Statically find every `app/tasks/*.py` that declares an @celery_app.task.

    Deliberately parses the source with `ast` instead of importing the modules:
    importing them would register their tasks as a side effect, which is exactly
    the state this check exists to detect the absence of.
    """
    import ast  # noqa: PLC0415
    import pathlib  # noqa: PLC0415

    import app.tasks  # noqa: PLC0415

    tasks_dir = pathlib.Path(app.tasks.__file__).parent
    declared: dict[str, list[str]] = {}
    for path in sorted(tasks_dir.glob("*.py")):
        names: list[str] = []
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if not ast.unparse(dec.func).endswith("celery_app.task"):
                    continue
                explicit = next(
                    (
                        kw.value.value
                        for kw in dec.keywords
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant)
                    ),
                    None,
                )
                names.append(explicit or f"app.tasks.{path.stem}.{node.name}")
        if names:
            declared[f"app.tasks.{path.stem}"] = names
    return declared


def test_every_task_declaring_module_is_listed_in_task_modules() -> None:
    """Every module defining an @celery_app.task must appear in _TASK_MODULES.

    autodiscover_tasks() is a no-op in this project (see the comment above
    _TASK_MODULES), so the include list is the *only* thing that makes a task
    resolvable on the worker. An unlisted module still dispatches fine from the
    producer — `apply_async` just publishes a name — and then dies on the worker
    as "Received unregistered task", which no other test in this suite can see.

    Regression: `app.tasks.request_analysis` was routed in task_routes but absent
    from this list, so `analyze_request_ai` was undeliverable.
    """
    from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

    missing = sorted(set(_declared_task_modules()) - set(_TASK_MODULES))
    assert not missing, (
        f"Task modules missing from _TASK_MODULES: {missing!r}. "
        "Their tasks dispatch from the API but are unregistered on the worker."
    )


def test_task_modules_all_declare_tasks() -> None:
    """The reverse: no stale entry naming a module that no longer defines tasks."""
    from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

    stale = sorted(set(_TASK_MODULES) - set(_declared_task_modules()))
    assert not stale, f"_TASK_MODULES entries declaring no task: {stale!r}"


def test_routed_task_names_are_registered() -> None:
    """Every literal task_routes key must resolve to a task the worker registers.

    `import_default_modules()` is what the worker itself calls at boot to import
    the `include=` list, so this asserts against the same registry a real worker
    would build. A routed name with no registered task is the signature of the
    bug above: routing was configured, registration was not.

    Glob keys (`app.tasks.parse.*`) are skipped — they match by prefix and have
    no single task to resolve to.
    """
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    celery_app.loader.import_default_modules()
    registered = set(celery_app.tasks.keys())
    routed = {key for key in celery_app.conf.task_routes if "*" not in key}
    assert not routed - registered, (
        f"Routed but unregistered task names: {sorted(routed - registered)!r}"
    )
