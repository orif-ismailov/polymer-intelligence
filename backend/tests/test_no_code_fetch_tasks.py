"""
Tests for the no-code adapter fetch tasks (html_table / rss / llm_page).

Each fetch task loads enabled sources of one adapter type and delegates to the
shared isolation helper run_source_fetch_isolated, passing the parse task that
matches the adapter's data shape:

  - html_table → parse_raw_item      (structured rows, rule-based matching)
  - rss        → parse_telegram_item (unstructured text, LLM extraction)
  - llm_page   → parse_telegram_item (unstructured page text, LLM extraction)

These tests mock the DB/session and the isolation helper and assert the routing
decision — the one thing that distinguishes the rule path from the LLM path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _run_task_and_capture_route(task_callable, task_module: str, adapter_name: str) -> str:
    """Invoke a fetch task with all DB/helpers mocked; return the routed parse task."""
    from app.tasks import ingest as ingest_mod  # noqa: PLC0415

    fake_source = SimpleNamespace(id=1, adapter=adapter_name)

    with (
        patch(f"{task_module}.Session") as mock_session_cls,
        patch("app.ingest.registry.get_adapter", return_value=MagicMock()),
        patch.object(ingest_mod, "_load_enabled_sources", return_value=[fake_source]),
        patch.object(
            ingest_mod, "run_source_fetch_isolated", return_value=0
        ) as mock_run,
    ):
        mock_session_cls.return_value.__enter__.return_value = MagicMock()
        mock_session_cls.return_value.__exit__.return_value = False
        task_callable()

    assert mock_run.call_count == 1, "expected exactly one per-source fetch call"
    return str(mock_run.call_args.kwargs.get("parse_task_name"))


def test_html_table_fetch_routes_to_rule_parser():
    """html_table_fetch dispatches structured rows to the rule-based parser."""
    from app.tasks.ingest_html_table import html_table_fetch  # noqa: PLC0415

    route = _run_task_and_capture_route(
        html_table_fetch, "app.tasks.ingest_html_table", "html_table"
    )
    assert route == "parse_raw_item"


def test_rss_fetch_routes_to_llm_parser():
    """rss_fetch dispatches unstructured entries to the LLM extractor."""
    from app.tasks.ingest_rss import rss_fetch  # noqa: PLC0415

    route = _run_task_and_capture_route(rss_fetch, "app.tasks.ingest_rss", "rss")
    assert route == "parse_telegram_item"


def test_llm_page_fetch_routes_to_llm_parser():
    """llm_page_fetch dispatches page text to the LLM extractor."""
    from app.tasks.ingest_llm_page import llm_page_fetch  # noqa: PLC0415

    route = _run_task_and_capture_route(
        llm_page_fetch, "app.tasks.ingest_llm_page", "llm_page"
    )
    assert route == "parse_telegram_item"


@pytest.mark.parametrize(
    ("module_path", "task_name"),
    [
        ("app.tasks.ingest_html_table", "html_table_fetch"),
        ("app.tasks.ingest_rss", "rss_fetch"),
        ("app.tasks.ingest_llm_page", "llm_page_fetch"),
    ],
)
def test_fetch_tasks_registered(module_path: str, task_name: str):
    """Each fetch task is registered on the Celery app under its contract name."""
    __import__(module_path)
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert task_name in celery_app.tasks
