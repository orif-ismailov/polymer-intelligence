"""
Celery task package for Polymer Intelligence.

Imports and re-exports `celery_app` so that both of these resolve:
  - `app.tasks.celery_app:celery_app`   (direct module import)
  - `app.tasks:celery_app`              (package-level import)

The autodiscovery in celery_app.py (`autodiscover_tasks(["app.tasks"])`) will
pick up all task modules placed in this package. The real implementation modules
(ingest.py, ingest_cbu.py, notify.py) register all five scheduled task names
so placeholders.py is no longer needed (CR-03: deleted to remove the task-name
collision hazard).
"""

from __future__ import annotations

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
