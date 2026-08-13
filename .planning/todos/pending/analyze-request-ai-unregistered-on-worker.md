---
created: 2026-08-13
title: analyze_request_ai is missing from _TASK_MODULES — worker cannot resolve it
area: backend/celery
severity: live bug (silent), user-visible feature likely dead in prod
fix-when: P9 (Requests/Pricing) of the backend domain-reorg track — see
  .planning/backend-domain-reorg/00-CONTEXT.md phase roadmap item 9
files:
  - backend/app/tasks/celery_app.py:42       # _TASK_MODULES — the omission
  - backend/app/tasks/request_analysis.py:22 # @celery_app.task(name="analyze_request_ai")
  - backend/app/services/request_service.py:123
  - backend/tests/test_request_analysis.py:211
---

## Problem

`app/tasks/request_analysis.py` defines `analyze_request_ai`:

```python
@celery_app.task(name="analyze_request_ai", queue="parse")
def analyze_request_ai(request_id: int) -> dict[str, Any]:
```

The task name **is** routed — `celery_app.py:134` has `"analyze_request_ai": {"queue": "parse"}`
— but `"app.tasks.request_analysis"` is **not** in `_TASK_MODULES` (`celery_app.py:42`), the
explicit `include=` list on the Celery constructor.

`celery_app.py:37-41` documents why that list is the only registration mechanism here:
`autodiscover_tasks(["app.tasks"])` is a deliberate no-op in this project. So the worker never
imports the module, and `analyze_request_ai` is absent from its task registry.

Verified — nothing registers it transitively:

- The only importer is `request_service.py:123`, and it is **function-local**
  (`# noqa: PLC0415`), inside the producer path.
- No module in `_TASK_MODULES` imports `request_service` at module level.

## Why it is silent

Three layers hide it:

1. The producer's function-local import registers the task in the **API** process, so
   `apply_async(...)` succeeds and returns normally — it just publishes a message by name.
2. The `try/except` at `request_service.py:124-131` wraps **only the enqueue**, and its comment
   scopes it to "broker unavailable". Worker-side rejection happens after that boundary.
3. `REQUEST_AI_ANALYSIS_ENABLED` defaults `True` (`config.py:57`), so this is on by default.

Expected runtime symptom: the message lands on the `parse` queue and the worker logs
`Received unregistered task of type 'analyze_request_ai'` and rejects it. Requests still commit —
`request_service`'s docstring promises analysis "must never break request creation", and it
doesn't — but the AI panel keeps its placeholders forever.

## Why CI is green

`tests/test_request_analysis.py:211/220/228` patch `app.tasks.request_analysis.analyze_request_ai`
and assert the **producer** dispatches. Patching imports the module into the test process, which
is exactly the registration the worker lacks. Nothing anywhere asserts the worker's registry.

## Fix

1. Add `"app.tasks.request_analysis"` to `_TASK_MODULES` in `app/tasks/celery_app.py`.
2. Add a regression test that asserts registry membership rather than dispatch — walk
   `_TASK_MODULES`, import each, and check every `@celery_app.task(name=...)` name found under
   `app/tasks/*.py` appears in `celery_app.tasks`. That generalizes: the same omission can recur
   for any future task module, and `task_routes` already lists names the registry does not have.
3. While there, cross-check `task_routes` keys against the registry — a routed name with no
   registered task is the exact signature of this bug and worth failing on.

## Notes

- Found incidentally while inventorying `app/tasks/` for the domain-reorg track (P4 research).
- Deliberately **not** bundled into any migration commit: reorg phases are behavior-free by rule,
  and this changes behavior (a dead feature starts running). It wants its own commit, and ideally
  a check on staging that the analysis actually produces output once registered — the feature has
  probably never executed, so its first real run is unproven.
- Scheduled for P9 by decision, not by dependency. Nothing about the fix requires the reorg; it
  could ship today if the AI panel matters sooner.
