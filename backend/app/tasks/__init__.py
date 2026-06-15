"""
Celery task package for Polymer Intelligence.

Imports and re-exports `celery_app` so that both of these resolve:
  - `app.tasks.celery_app:celery_app`   (direct module import)
  - `app.tasks:celery_app`              (package-level import)

The autodiscovery in celery_app.py (`autodiscover_tasks(["app.tasks"])`) will
pick up all task modules placed in this package. The placeholders import here
ensures the five scheduled task names are registered when the package is loaded,
even before the implementing plans (02-04/02-05/02-06) land.
"""

from __future__ import annotations

import app.tasks.placeholders as _placeholders  # noqa: F401 — side-effect: registers tasks
from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
