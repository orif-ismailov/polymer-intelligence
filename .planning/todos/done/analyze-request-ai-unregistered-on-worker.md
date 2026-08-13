---
created: 2026-08-13
resolved: 2026-08-13
status: FIXED — see "Resolution" at the bottom
title: analyze_request_ai is missing from _TASK_MODULES — worker cannot resolve it
area: backend/celery
severity: live bug (silent), user-visible feature likely dead in prod
fix-when: fixed ahead of P9 on request; the reorg plan no longer carries it
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

## Resolution

Fixed ahead of P9. `"app.tasks.request_analysis"` added to `_TASK_MODULES`, plus three tests in
`backend/tests/test_celery_app.py`.

**Confirmed empirically before and after.** `celery_app.loader.import_default_modules()` is what
the worker calls at boot to import the `include=` list; against the unfixed tree it built a
registry containing every task **except** `analyze_request_ai`, with that name still present in
`task_routes`. Both new assertions failed on the unfixed tree and pass after the one-line change.

Note for anyone reading the original diagnosis: accessing `celery_app.tasks` alone does **not**
import the include list, so a naive registry check finds *nothing* registered and proves nothing.
That is why the pre-existing `test_real_tasks_registered` imports its modules by hand.

The tests added:

- `test_every_task_declaring_module_is_listed_in_task_modules` — the real guard. Parses
  `app/tasks/*.py` with `ast` rather than importing them, because importing would register the
  tasks as a side effect and mask the very state being checked. Also immune to import pollution
  from other tests in a full-suite run (`test_request_analysis.py` patches the task module, which
  imports it).
- `test_task_modules_all_declare_tasks` — the reverse, catching a stale entry.
- `test_routed_task_names_are_registered` — cross-checks literal `task_routes` keys against a
  worker-faithful registry via `import_default_modules()`.

The static scan also answered a question the original write-up left open: **exactly one** module
was missing. 20 modules under `app/tasks/` declare a task, 19 were listed, and the diff is
`app.tasks.request_analysis` alone. No stale entries either.

**Still unverified: that the feature works.** This makes the task deliverable; it does not prove
`analyze_request_ai` produces sensible output. The feature has very likely never executed in
production, so its first real run is unproven. Exercise it on staging — confirm a `requests.ai`
block is written and that the budget-exceeded and LLM-error paths degrade as
`request_analysis_service` claims — before treating the AI panel as working.
